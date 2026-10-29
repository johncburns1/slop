"""Tests for the submit prompt use case."""

import json
from dataclasses import dataclass, field, replace

import pytest

from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, load_game
from slop.application.submit_prompt import (
    MAX_PROMPT_WORDS,
    SCRIPT_ATTEMPTS,
    SubmitPrompt,
    submit_prompt,
)
from slop.domain import (
    AIPersonality,
    Game,
    PromptSubmitted,
    RoleAssigned,
    Script,
    ScriptGenerated,
    ScriptGenerationFailed,
    ScriptReady,
)
from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.ports.llm import LLMError
from tests.builders import in_guessing_phase, waiting_for_prompt
from tests.evidence import write_evidence

ACTING_SOCKETS = {"socket-1", "socket-2"}
OTHER_SOCKETS = {"socket-3", "socket-4"}
PROMPT = "Cat steals the moon"


@dataclass
class FakeLLM:
    """Fails the first ``failures`` calls, then defers to the stand-in. Records every call."""

    failures: int = 0
    extra_roles: int = 0
    calls: list[tuple[str, AIPersonality, int]] = field(default_factory=list)

    async def generate_script(
        self, prompt: str, personality: AIPersonality, num_roles: int
    ) -> Script:
        self.calls.append((prompt, personality, num_roles))
        if len(self.calls) <= self.failures:
            raise LLMError("provider unavailable")
        return await StandInLLMAdapter().generate_script(
            prompt, personality, num_roles + self.extra_roles
        )


async def start(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game and put every player's socket in its room."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return game


def with_llm(deps: GameDeps, llm: FakeLLM) -> GameDeps:
    return replace(deps, llm=llm)


async def test_the_acting_team_gets_the_script_and_roles_and_the_room_only_hears_it_is_ready(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, waiting_for_prompt())

    game = await submit_prompt(deps, SubmitPrompt(game.id, "player-2", PROMPT))

    (current,) = game.rounds
    assert (current.prompt, current.submitted_by) == (PROMPT, "player-2")
    assert current.script is not None
    assert current.script.personality == "noir"
    assert current.role_assignments == {"player-1": 0, "player-2": 1}
    assert await load_game(deps, game.id) == game

    events = await storage.get_events(game.id)
    assert [type(e) for e in events] == [
        PromptSubmitted,
        ScriptGenerated,
        RoleAssigned,
        RoleAssigned,
        ScriptReady,
    ]
    for socket_id in ACTING_SOCKETS:
        assert realtime.received_by(socket_id) == events
    for socket_id in OTHER_SOCKETS:
        assert realtime.received_by(socket_id) == [events[-1]]
    assert realtime.broadcasts_to(game.room_code) == [events[-1]]
    (ready,) = realtime.received_by("socket-3")
    assert isinstance(ready, ScriptReady)
    public = ready.model_dump_json()
    assert PROMPT.lower() not in public.lower()
    assert "noir" not in public
    assert current.script.content not in public
    assert ready.acting_team_id == "team-1"
    write_evidence(
        "submit-prompt/who-received-what.json",
        json.dumps(
            {
                socket_id: [e.event_type for e in realtime.received_by(socket_id)]
                for socket_id in sorted(ACTING_SOCKETS | OTHER_SOCKETS)
            },
            indent=2,
        ),
    )
    write_evidence(
        "submit-prompt/events.jsonl", "".join(e.model_dump_json() + "\n" for e in events)
    )


async def test_the_llm_gets_the_prompt_the_team_personality_and_one_role_per_player(
    deps: GameDeps, realtime: RecordingRealtime
):
    llm = FakeLLM()
    game = await start(deps, realtime, waiting_for_prompt(players_per_team=3))

    game = await submit_prompt(with_llm(deps, llm), SubmitPrompt(game.id, "player-1", PROMPT))

    ((prompt, personality, num_roles),) = llm.calls
    assert (prompt, personality.id, num_roles) == (PROMPT, "noir", 3)
    (current,) = game.rounds
    assert current.script is not None
    assert len(current.script.roles) == 3
    assert current.role_assignments == {"player-1": 0, "player-2": 1, "player-3": 2}
    assert realtime.who_received(RoleAssigned) == {"socket-1", "socket-2", "socket-3"}


async def test_the_prompt_is_trimmed(deps: GameDeps, realtime: RecordingRealtime):
    game = await start(deps, realtime, waiting_for_prompt())

    game = await submit_prompt(
        deps, SubmitPrompt(game.id, "player-1", "  Cat  steals\tthe moon \n")
    )

    assert game.rounds[0].prompt == PROMPT


async def test_a_six_word_prompt_is_accepted(deps: GameDeps, realtime: RecordingRealtime):
    six_words = "Superhero saves city from angry aliens"
    assert len(six_words.split()) == MAX_PROMPT_WORDS == 6
    game = await start(deps, realtime, waiting_for_prompt())

    game = await submit_prompt(deps, SubmitPrompt(game.id, "player-1", six_words))

    assert game.rounds[0].prompt == six_words


@pytest.mark.parametrize(
    "prompt",
    ["Superhero saves city from very angry aliens", "", "   \n "],
    ids=["seven-words", "empty", "blank"],
)
async def test_a_prompt_that_is_too_long_or_blank_is_rejected_before_calling_the_llm(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, prompt: str
):
    llm = FakeLLM()
    game = await start(deps, realtime, waiting_for_prompt())

    with pytest.raises(GameRuleError, match="1 to 6 words"):
        await submit_prompt(with_llm(deps, llm), SubmitPrompt(game.id, "player-1", prompt))

    assert llm.calls == []
    assert await storage.get_events(game.id) == []
    assert realtime.received_by("socket-1") == []


async def test_a_failed_generation_is_retried_once(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    llm = FakeLLM(failures=1)
    game = await start(deps, realtime, waiting_for_prompt())

    game = await submit_prompt(with_llm(deps, llm), SubmitPrompt(game.id, "player-1", PROMPT))

    assert len(llm.calls) == SCRIPT_ATTEMPTS == 2
    assert game.rounds[0].script is not None
    assert realtime.who_received(ScriptGenerationFailed) == frozenset()
    assert ScriptReady in {type(e) for e in await storage.get_events(game.id)}


async def test_two_failures_leave_the_round_waiting_and_tell_only_the_acting_team(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    llm = FakeLLM(failures=2)
    game = await start(deps, realtime, waiting_for_prompt())

    game = await submit_prompt(with_llm(deps, llm), SubmitPrompt(game.id, "player-1", PROMPT))

    assert len(llm.calls) == 2
    (current,) = game.rounds
    assert (current.prompt, current.script, current.role_assignments) == (None, None, {})
    (failed,) = await storage.get_events(game.id)
    assert isinstance(failed, ScriptGenerationFailed)
    assert (failed.round_number, failed.team_id) == (0, "team-1")
    for socket_id in ACTING_SOCKETS:
        assert realtime.received_by(socket_id) == [failed]
    for socket_id in OTHER_SOCKETS:
        assert realtime.received_by(socket_id) == []
    assert realtime.broadcasts_to(game.room_code) == []

    # The team can try again, and this time it works.
    game = await submit_prompt(with_llm(deps, llm), SubmitPrompt(game.id, "player-2", PROMPT))

    assert len(llm.calls) == 3
    assert game.rounds[0].script is not None


async def test_a_script_with_the_wrong_number_of_roles_counts_as_a_failure(
    deps: GameDeps, realtime: RecordingRealtime
):
    llm = FakeLLM(extra_roles=1)
    game = await start(deps, realtime, waiting_for_prompt())

    game = await submit_prompt(with_llm(deps, llm), SubmitPrompt(game.id, "player-1", PROMPT))

    assert len(llm.calls) == 2
    assert game.rounds[0].script is None
    assert realtime.who_received(ScriptGenerationFailed) == ACTING_SOCKETS


@pytest.mark.parametrize(
    ("player_id", "message"),
    [("player-3", "not on the acting team"), ("player-9", "not in this game")],
)
async def test_only_the_acting_team_can_submit(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, player_id, message
):
    llm = FakeLLM()
    game = await start(deps, realtime, waiting_for_prompt())

    with pytest.raises(GameRuleError, match=message):
        await submit_prompt(with_llm(deps, llm), SubmitPrompt(game.id, player_id, PROMPT))

    assert llm.calls == []
    assert await storage.get_events(game.id) == []


async def test_a_round_with_a_prompt_already_is_not_waiting(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())

    with pytest.raises(GameRuleError, match="not waiting for a prompt"):
        await submit_prompt(deps, SubmitPrompt(game.id, "player-1", PROMPT))

    assert await storage.get_events(game.id) == []


async def test_a_game_with_no_round_started_is_not_waiting(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = waiting_for_prompt()
    game.rounds.clear()
    await start(deps, realtime, game)

    with pytest.raises(GameRuleError, match="not waiting for a prompt"):
        await submit_prompt(deps, SubmitPrompt(game.id, "player-1", PROMPT))


async def test_an_unknown_game_is_rejected(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await submit_prompt(deps, SubmitPrompt("nope", "player-1", PROMPT))
