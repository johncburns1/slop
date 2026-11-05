"""Tests for the host skipping a turn that stalled before the acting team got its script."""

from dataclasses import replace

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, load_game
from slop.application.skip_turn import SkipTurn, skip_turn
from slop.application.submit_prompt import SCRIPT_ATTEMPTS, SubmitPrompt, submit_prompt
from slop.domain import (
    AwardsGiven,
    Game,
    GameCompleted,
    GameSettings,
    GameStatus,
    RoundCompleted,
    RoundStarted,
    ScriptGenerationFailed,
    TiebreakerStarted,
    TurnSkipped,
)
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.application.test_restart_game import seated
from tests.application.test_submit_prompt import FakeLLM
from tests.builders import in_guessing_phase, selecting_personalities, waiting_for_prompt

ALL_SOCKETS = {"socket-1", "socket-2", "socket-3", "socket-4"}


def last_round(*, red_score: int) -> Game:
    """One round per team; team 1 has its turn and Red (team 1) has ``red_score`` points."""
    game = waiting_for_prompt()
    game.settings = GameSettings(rounds_per_team=1)
    game.teams[0].add_score(red_score)
    return game


async def new_events(storage: InMemoryStorage, game_id: str, before: int) -> list[type]:
    return [type(e) for e in (await storage.get_events(game_id))[before:]]


async def test_skipping_while_the_team_writes_its_prompt_passes_the_turn_with_no_points(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, waiting_for_prompt())

    after = await skip_turn(deps, SkipTurn(game.id, "player-1"))

    events = await storage.get_events(game.id)
    assert [type(e) for e in events] == [TurnSkipped, RoundCompleted, RoundStarted]
    skipped, completed, started = events
    assert isinstance(skipped, TurnSkipped)
    assert (skipped.round_number, skipped.team_id) == (0, "team-1")
    assert isinstance(completed, RoundCompleted)
    assert completed.final_scores == {"team-1": 0, "team-2": 0}
    assert isinstance(started, RoundStarted)
    assert (started.round_number, started.acting_team_id) == (1, "team-2")
    assert realtime.who_received(TurnSkipped) == ALL_SOCKETS
    assert [t.score for t in after.teams] == [0, 0]
    assert after.rounds[0].skipped
    assert (after.status, after.current_round) == (GameStatus.PLAYING, 1)
    assert await load_game(deps, game.id) == after


async def test_skipping_keeps_the_scores_already_earned(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = waiting_for_prompt()
    game.teams[0].add_score(2)
    game.teams[1].add_score(1)
    game = await seated(deps, realtime, game)

    after = await skip_turn(deps, SkipTurn(game.id, "player-1"))

    completed = (await storage.get_events(game.id))[1]
    assert isinstance(completed, RoundCompleted)
    assert completed.final_scores == {"team-1": 2, "team-2": 1}
    assert [t.score for t in after.teams] == [2, 1]


async def test_the_host_can_skip_after_the_script_failed_to_generate(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    deps = replace(deps, llm=FakeLLM(failures=SCRIPT_ATTEMPTS))
    game = await seated(deps, realtime, waiting_for_prompt())
    await submit_prompt(deps, SubmitPrompt(game.id, "player-1", "Cat steals the moon"))
    assert [type(e) for e in await storage.get_events(game.id)] == [ScriptGenerationFailed]

    after = await skip_turn(deps, SkipTurn(game.id, "player-1"))

    assert await new_events(storage, game.id, 1) == [TurnSkipped, RoundCompleted, RoundStarted]
    assert after.rounds[-1].acting_team_id == "team-2"


async def test_the_host_cannot_skip_once_the_script_exists(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, in_guessing_phase())

    with pytest.raises(GameRuleError, match="already have their script"):
        await skip_turn(deps, SkipTurn(game.id, "player-1"))
    assert await storage.get_events(game.id) == []


async def test_a_script_that_arrives_after_the_skip_is_thrown_away(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, waiting_for_prompt())
    llm = deps.llm

    class SkipsWhileWriting:
        async def generate_script(self, *args: object) -> object:
            await skip_turn(deps, SkipTurn(game.id, "player-3"))
            return await llm.generate_script(*args)  # type: ignore[arg-type]

        async def generate_awards(self, *args: object) -> object:
            return await llm.generate_awards(*args)  # type: ignore[arg-type]

    # Player 3 isn't the host: make them the host for this test.
    game.players[0].is_creator, game.players[2].is_creator = False, True
    await deps.storage.save_snapshot(game)
    writing = replace(deps, llm=SkipsWhileWriting())  # type: ignore[arg-type]

    with pytest.raises(GameRuleError, match="not waiting for a prompt|not on the acting team"):
        await submit_prompt(writing, SubmitPrompt(game.id, "player-1", "Cat steals the moon"))
    assert await new_events(storage, game.id, 0) == [TurnSkipped, RoundCompleted, RoundStarted]


async def test_skipping_the_last_round_ends_the_game(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, last_round(red_score=1))
    after = await skip_turn(deps, SkipTurn(game.id, "player-1"))
    assert after.current_round == 1

    after = await skip_turn(deps, SkipTurn(game.id, "player-1"))

    assert after.status == GameStatus.FINISHED
    assert await new_events(storage, game.id, 3) == [
        TurnSkipped,
        RoundCompleted,
        GameCompleted,
        AwardsGiven,
    ]
    completed = (await storage.get_events(game.id))[5]
    assert isinstance(completed, GameCompleted)
    assert completed.winner_team_id == "team-1"


async def test_skipping_the_last_round_into_a_tie_starts_a_tiebreaker(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, last_round(red_score=0))
    await skip_turn(deps, SkipTurn(game.id, "player-1"))

    after = await skip_turn(deps, SkipTurn(game.id, "player-1"))

    assert after.status == GameStatus.PLAYING
    assert after.tiebreaker is not None
    assert await new_events(storage, game.id, 3) == [
        TurnSkipped,
        RoundCompleted,
        TiebreakerStarted,
        RoundStarted,
    ]


async def test_only_the_host_can_skip_a_turn(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, waiting_for_prompt())

    with pytest.raises(GameRuleError, match="Only the host"):
        await skip_turn(deps, SkipTurn(game.id, "player-3"))
    with pytest.raises(GameRuleError, match="not in this game"):
        await skip_turn(deps, SkipTurn(game.id, "player-99"))
    assert await storage.get_events(game.id) == []


async def test_there_is_no_turn_to_skip_before_the_game_is_played(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, selecting_personalities())

    with pytest.raises(GameRuleError, match="No round is in progress"):
        await skip_turn(deps, SkipTurn(game.id, "player-1"))


async def test_an_unknown_game_is_not_found(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await skip_turn(deps, SkipTurn("no-such-game", "player-1"))
