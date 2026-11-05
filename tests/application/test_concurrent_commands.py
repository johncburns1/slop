"""Commands for one game are serialized, so none can overwrite another's snapshot.

In-memory storage never suspends and SQLite only sometimes does at a bad
moment, so ``InterleavingStorage`` yields to the event loop around every storage
call. Without the per-game lock that interleaves every load with every save.
"""

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.moderation import StandInModerationAdapter
from slop.adapters.storage import InMemoryStorage, SQLiteStorage
from slop.application.assign_personality import AssignPersonality, assign_personality
from slop.application.create_game import CreateGame, create_game
from slop.application.engine import GameDeps, commit, load_game
from slop.application.expire_games import expire_games
from slop.application.finish_or_continue import FinishOrContinue, finish_or_continue
from slop.application.form_teams import (
    CreateTeam,
    StartPersonalitySelection,
    create_team,
    start_personality_selection,
)
from slop.application.guess_and_score import SubmitGuess, submit_guess
from slop.application.guess_timers import GuessTimers
from slop.application.join_game import JoinGame, join_game
from slop.application.rejoin_game import RejoinGame, rejoin_game
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain import Game, GuessingEnded, GuessSubmitted
from slop.domain.ai_personality import AIPersonality
from slop.domain.award import Award
from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.domain.events import AwardsGiven, GameEvent, PlayerReconnected, ScriptGenerated
from slop.domain.expiry import ExpiryPolicy
from slop.domain.game import ContentTone
from slop.domain.personalities import PERSONALITIES
from slop.domain.projection import replay
from slop.domain.script import Script
from slop.ports.llm import GameSummary
from slop.ports.moderation import ModerationResult
from slop.ports.storage import StoragePort
from tests.builders import scored_after_last_round

GUESSES = 40
GUESSES_BEFORE_TIME_IS_UP = 10


class InterleavingStorage:
    """Storage that lets every other task run around each call, like a slow disk."""

    def __init__(self, inner: StoragePort, on_event: Callable[[GameEvent], None]) -> None:
        self._inner = inner
        self._on_event = on_event

    async def save_event(self, event: GameEvent) -> None:
        await asyncio.sleep(0)
        await self._inner.save_event(event)
        self._on_event(event)
        await asyncio.sleep(0)

    async def get_events(self, game_id: str) -> list[GameEvent]:
        return await self._inner.get_events(game_id)

    async def save_snapshot(self, game: Game) -> None:
        await asyncio.sleep(0)
        await self._inner.save_snapshot(game)
        await asyncio.sleep(0)

    async def get_snapshot(self, game_id: str) -> Game | None:
        await asyncio.sleep(0)
        game = await self._inner.get_snapshot(game_id)
        await asyncio.sleep(0)
        return game

    async def get_game_by_room_code(self, room_code: str) -> Game | None:
        await asyncio.sleep(0)
        game = await self._inner.get_game_by_room_code(room_code)
        await asyncio.sleep(0)
        return game

    async def list_games(self) -> list[Game]:
        return await self._inner.list_games()

    async def delete_game(self, game_id: str) -> None:
        await self._inner.delete_game(game_id)


@dataclass(frozen=True)
class Table:
    """A game in play, with guessing open: ``guesser`` is on the team that isn't acting."""

    game: Game
    guesser: str


async def _table_in_guessing_phase(deps: GameDeps) -> Table:
    """Play a real game up to guessing, so that its event log is complete."""
    game_id, actor, guesser = await _players_waiting_for_prompt(deps)
    game = await submit_prompt(deps, SubmitPrompt(game_id, actor, "a very slow disk"))
    return Table(game=game, guesser=guesser)


async def _waiting_for_prompt(deps: GameDeps) -> tuple[str, str]:
    """Return a game waiting for a prompt, and a player on its acting team."""
    game_id, actor, _ = await _players_waiting_for_prompt(deps)
    return game_id, actor


async def _players_waiting_for_prompt(deps: GameDeps) -> tuple[str, str, str]:
    """Return a game waiting for a prompt, a player acting, and a player guessing."""
    room = (await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))).room_code

    async def seat(name: str) -> tuple[str, str]:
        joined = await join_game(deps, JoinGame(room, name, f"socket-{name}"))
        return joined.game.id, joined.player_id

    game_id, actor = await seat("Ann")
    _, guesser = await seat("Bob")
    host_team = await create_team(deps, CreateTeam(game_id, actor, "Reds", "#f00"))
    other_team = await create_team(deps, CreateTeam(game_id, guesser, "Blues", "#00f"))
    assert host_team.team_id != other_team.team_id

    await start_personality_selection(deps, StartPersonalitySelection(game_id, actor))
    personality = next(iter(PERSONALITIES))
    await assign_personality(deps, AssignPersonality(game_id, actor, personality))
    await assign_personality(deps, AssignPersonality(game_id, guesser, personality))
    return game_id, actor, guesser


@pytest.fixture(params=["memory", "sqlite"])
def inner_storage(request: pytest.FixtureRequest, tmp_path: Path) -> StoragePort:
    if request.param == "memory":
        return InMemoryStorage()
    return SQLiteStorage(tmp_path / "slop.sqlite3")


def _texts(guesses: Iterable[str]) -> list[str]:
    return sorted(guesses)


async def _state(deps: GameDeps, game_id: str) -> tuple[Game, Game, list[GameEvent]]:
    """Return the stored snapshot, the game replayed from its log, and the log."""
    snapshot = await deps.storage.get_snapshot(game_id)
    assert snapshot is not None
    events = await deps.storage.get_events(game_id)
    return snapshot, replay(events), events


async def test_every_accepted_guess_survives_concurrent_guesses(
    deps: GameDeps, inner_storage: StoragePort
) -> None:
    deps = replace(deps, storage=InterleavingStorage(inner_storage, lambda _: None))
    table = await _table_in_guessing_phase(deps)

    await asyncio.gather(
        *(
            submit_guess(deps, SubmitGuess(table.game.id, table.guesser, f"guess {n}"))
            for n in range(GUESSES)
        )
    )

    snapshot, replayed, _ = await _state(deps, table.game.id)
    expected = _texts(f"guess {n}" for n in range(GUESSES))
    assert _texts(g.guess for g in snapshot.rounds[0].prompt_guesses) == expected
    assert _texts(g.guess for g in replayed.rounds[0].prompt_guesses) == expected
    assert replayed == snapshot


async def test_every_accepted_guess_survives_the_timer_closing_guessing_midway(
    deps: GameDeps, clock: FixedClock, inner_storage: StoragePort
) -> None:
    wake_timer = asyncio.Event()
    saved_guesses = 0

    def time_runs_out_midway(event: GameEvent) -> None:
        nonlocal saved_guesses
        if isinstance(event, GuessSubmitted):
            saved_guesses += 1
            if saved_guesses == GUESSES_BEFORE_TIME_IS_UP:
                clock.advance(timedelta(hours=1))
                wake_timer.set()

    async def sleep_until_woken(_: float) -> None:
        await wake_timer.wait()

    deps = replace(deps, storage=InterleavingStorage(inner_storage, time_runs_out_midway))
    table = await _table_in_guessing_phase(deps)
    timers = GuessTimers(deps, sleep=sleep_until_woken)
    timers.track(table.game)

    results = await asyncio.gather(
        *(
            submit_guess(deps, SubmitGuess(table.game.id, table.guesser, f"guess {n}"))
            for n in range(GUESSES)
        ),
        return_exceptions=True,
    )
    await timers.stop()

    accepted = _texts(f"guess {n}" for n, result in enumerate(results) if isinstance(result, Game))
    rejected = [result for result in results if not isinstance(result, Game)]
    snapshot, replayed, events = await _state(deps, table.game.id)
    assert _texts(g.guess for g in snapshot.rounds[0].prompt_guesses) == accepted
    assert _texts(g.guess for g in replayed.rounds[0].prompt_guesses) == accepted
    assert _texts(e.guess for e in events if isinstance(e, GuessSubmitted)) == accepted
    assert sum(isinstance(e, GuessingEnded) for e in events) == 1
    assert snapshot.rounds[0].guessing_ended
    assert replayed == snapshot
    # The timer really did close guessing midway: some guesses got in, the rest were turned away.
    assert accepted
    assert rejected
    assert all(isinstance(result, GameRuleError) for result in rejected)


class Gate:
    """Lets a slow call wait where the test can see it, until the test opens the gate."""

    def __init__(self) -> None:
        self.reached = asyncio.Event()
        self.opened = asyncio.Event()

    async def pass_through(self) -> None:
        self.reached.set()
        await self.opened.wait()


class GatedModeration(StandInModerationAdapter):
    """Moderation that waits at the gate for the first call only, or for every call."""

    def __init__(self, gate: Gate, *, every_call: bool = False) -> None:
        super().__init__()
        self._gate = gate
        self._every_call = every_call
        self._calls = 0

    async def check(self, text: str, tone: ContentTone) -> ModerationResult:
        self._calls += 1
        if self._every_call or self._calls == 1:
            await self._gate.pass_through()
        return await super().check(text, tone)


class GatedLLM(StandInLLMAdapter):
    def __init__(self, gate: Gate) -> None:
        super().__init__()
        self._gate = gate

    async def generate_script(
        self, prompt: str, personality: AIPersonality, num_roles: int, content_tone: ContentTone
    ) -> Script:
        await self._gate.pass_through()
        return await super().generate_script(prompt, personality, num_roles, content_tone)

    async def generate_awards(self, summary: GameSummary) -> list[Award]:
        await self._gate.pass_through()
        return await super().generate_awards(summary)


async def _lobby(deps: GameDeps) -> Game:
    game = await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))
    return (await join_game(deps, JoinGame(game.room_code, "Ann", "socket-ann"))).game


async def test_a_game_waiting_for_its_lock_does_not_hold_up_another_game(deps: GameDeps) -> None:
    busy = await _lobby(deps)
    free = await _lobby(deps)

    async with deps.locks.hold(busy.id):
        waiting = asyncio.create_task(join_game(deps, JoinGame(busy.room_code, "Bob", "socket-b")))
        await asyncio.sleep(0)
        joined = await asyncio.wait_for(
            join_game(deps, JoinGame(free.room_code, "Bob", "socket-b")), timeout=5
        )
        assert len(joined.game.players) == 2
        assert not waiting.done()

    assert len((await waiting).game.players) == 2
    assert len(deps.locks) == 0


async def test_slow_moderation_does_not_hold_up_the_room(deps: GameDeps) -> None:
    table = await _table_in_guessing_phase(deps)
    gate = Gate()
    slow = replace(deps, moderation=GatedModeration(gate))

    moderated = asyncio.create_task(
        submit_guess(slow, SubmitGuess(table.game.id, table.guesser, "slow guess"))
    )
    await asyncio.wait_for(gate.reached.wait(), timeout=5)
    assert len(deps.locks) == 0

    await asyncio.wait_for(
        submit_guess(deps, SubmitGuess(table.game.id, table.guesser, "quick guess")), timeout=5
    )
    gate.opened.set()
    game = await moderated

    assert [g.guess for g in game.rounds[0].prompt_guesses] == ["quick guess", "slow guess"]


async def test_a_guess_moderated_while_the_game_expired_does_not_bring_it_back(
    deps: GameDeps, clock: FixedClock
) -> None:
    table = await _table_in_guessing_phase(deps)
    gate = Gate()
    slow = replace(deps, moderation=GatedModeration(gate))

    moderated = asyncio.create_task(
        submit_guess(slow, SubmitGuess(table.game.id, table.guesser, "too late"))
    )
    await asyncio.wait_for(gate.reached.wait(), timeout=5)
    clock.advance(timedelta(days=1))
    assert await expire_games(deps, ExpiryPolicy()) == [table.game.id]
    gate.opened.set()

    with pytest.raises(GameNotFoundError):
        await moderated

    assert await deps.storage.get_snapshot(table.game.id) is None
    assert await deps.storage.get_events(table.game.id) == []
    assert len(deps.locks) == 0


async def test_an_event_that_arrives_just_in_time_saves_a_game_from_expiring(
    deps: GameDeps, clock: FixedClock
) -> None:
    game = await _lobby(deps)
    clock.advance(timedelta(days=1))

    async with deps.locks.hold(game.id):
        expiring = asyncio.create_task(expire_games(deps, ExpiryPolicy()))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await commit(
            deps,
            game,
            [PlayerReconnected(game_id=game.id, player_id=game.players[0].id, socket_id="new")],
        )

    assert await expiring == []
    assert await load_game(deps, game.id)
    assert len(deps.locks) == 0


async def test_a_second_prompt_written_at_the_same_time_loses_instead_of_replacing_the_first(
    deps: GameDeps,
) -> None:
    gate = Gate()
    slow = replace(deps, llm=GatedLLM(gate))
    game_id, actor = await _waiting_for_prompt(deps)

    first = asyncio.create_task(submit_prompt(slow, SubmitPrompt(game_id, actor, "first prompt")))
    second = asyncio.create_task(submit_prompt(slow, SubmitPrompt(game_id, actor, "second prompt")))
    await asyncio.wait_for(gate.reached.wait(), timeout=5)
    assert len(deps.locks) == 0
    gate.opened.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert sum(isinstance(result, Game) for result in results) == 1
    assert sum(isinstance(result, GameRuleError) for result in results) == 1
    events = await deps.storage.get_events(game_id)
    assert sum(isinstance(e, ScriptGenerated) for e in events) == 1
    assert replay(events) == await load_game(deps, game_id)


async def test_slow_awards_do_not_hold_up_the_room(deps: GameDeps) -> None:
    game = scored_after_last_round(scores=[2, 1])
    await deps.storage.save_snapshot(game)
    gate = Gate()
    slow = replace(deps, llm=GatedLLM(gate))
    player = game.players[0]

    finishing = asyncio.create_task(finish_or_continue(slow, FinishOrContinue(game.id)))
    await asyncio.wait_for(gate.reached.wait(), timeout=5)
    assert len(deps.locks) == 0

    await asyncio.wait_for(
        rejoin_game(deps, RejoinGame(game.room_code, player.id, "new-socket")), timeout=5
    )
    gate.opened.set()
    await finishing

    after = await load_game(deps, game.id)
    assert after.awards
    assert after.get_player(player.id).socket_id == "new-socket"
    assert any(isinstance(e, AwardsGiven) for e in await deps.storage.get_events(game.id))


async def test_the_same_name_moderated_at_the_same_time_is_given_to_only_one_player(
    deps: GameDeps,
) -> None:
    game = await _lobby(deps)
    gate = Gate()
    slow = replace(deps, moderation=GatedModeration(gate, every_call=True))

    joins = [
        asyncio.create_task(join_game(slow, JoinGame(game.room_code, "Bob", f"socket-{n}")))
        for n in range(2)
    ]
    await asyncio.wait_for(gate.reached.wait(), timeout=5)
    await asyncio.sleep(0)
    gate.opened.set()
    results = await asyncio.gather(*joins, return_exceptions=True)

    assert sum(isinstance(result, GameRuleError) for result in results) == 1
    names = [player.name for player in (await load_game(deps, game.id)).players]
    assert names == ["Ann", "Bob"]


async def test_the_same_team_name_moderated_at_the_same_time_is_given_to_only_one_team(
    deps: GameDeps,
) -> None:
    game = await _lobby(deps)
    second = await join_game(deps, JoinGame(game.room_code, "Bob", "socket-bob"))
    gate = Gate()
    slow = replace(deps, moderation=GatedModeration(gate, every_call=True))

    creates = [
        asyncio.create_task(create_team(slow, CreateTeam(game.id, player_id, "Reds", color)))
        for player_id, color in ((game.players[0].id, "#f00"), (second.player_id, "#00f"))
    ]
    await asyncio.wait_for(gate.reached.wait(), timeout=5)
    await asyncio.sleep(0)
    gate.opened.set()
    results = await asyncio.gather(*creates, return_exceptions=True)

    assert sum(isinstance(result, GameRuleError) for result in results) == 1
    assert [team.name for team in (await load_game(deps, game.id)).teams] == ["Reds"]
