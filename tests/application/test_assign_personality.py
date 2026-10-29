"""Tests for the assign personality use case."""

import json
from dataclasses import dataclass, field, replace

import pytest

from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.assign_personality import AssignPersonality, assign_personality, target_team
from slop.application.engine import GameDeps, load_game
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain import (
    AIPersonality,
    Game,
    GameStatus,
    PersonalityAssigned,
    PersonalityPicked,
    RoundStarted,
    Script,
)
from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.domain.personalities import PERSONALITIES, get_personality
from tests.builders import lobby_with_two_teams, selecting_personalities
from tests.evidence import write_evidence

# Team 1 is player-1/2 on socket-1/2, team 2 is player-3/4, team 3 is player-5/6.
TEAM_SOCKETS = {
    "team-1": {"socket-1", "socket-2"},
    "team-2": {"socket-3", "socket-4"},
    "team-3": {"socket-5", "socket-6"},
}


@dataclass
class RecordingLLM:
    """Defers to the stand-in and records which personality each call used."""

    personalities: list[AIPersonality] = field(default_factory=list)

    async def generate_script(
        self, prompt: str, personality: AIPersonality, num_roles: int
    ) -> Script:
        self.personalities.append(personality)
        return await StandInLLMAdapter().generate_script(prompt, personality, num_roles)


async def start(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game and put every player's socket in its room."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return game


def personality_ids_received(realtime: RecordingRealtime, socket_id: str) -> set[str]:
    return {
        e.personality_id
        for e in realtime.received_by(socket_id)
        if isinstance(e, PersonalityAssigned)
    }


@pytest.mark.parametrize(
    ("num_teams", "expected"),
    [
        (2, {"team-1": "team-2", "team-2": "team-1"}),
        (3, {"team-1": "team-2", "team-2": "team-3", "team-3": "team-1"}),
    ],
)
def test_teams_pick_round_a_ring_so_nobody_picks_for_itself(num_teams, expected):
    game = selecting_personalities(num_teams=num_teams)

    assert {team.id: target_team(game, team.id).id for team in game.teams} == expected


async def test_only_the_picking_team_learns_the_pick_and_the_room_learns_a_pick_was_made(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, selecting_personalities(num_teams=3))

    game = await assign_personality(deps, AssignPersonality(game.id, "player-1", "noir"))

    receiver = game.get_team("team-2")
    assert (receiver.assigned_personality, receiver.personality_assigned_by) == ("noir", "team-1")
    for socket_id in TEAM_SOCKETS["team-1"]:
        assert personality_ids_received(realtime, socket_id) == {"noir"}
    for socket_id in TEAM_SOCKETS["team-2"] | TEAM_SOCKETS["team-3"]:
        assert personality_ids_received(realtime, socket_id) == set()
        assert not any("noir" in e.model_dump_json() for e in realtime.received_by(socket_id))
    (picked,) = realtime.broadcasts_to(game.room_code)
    assert isinstance(picked, PersonalityPicked)
    assert picked.picked_by_team_id == "team-1"
    assert game.status == GameStatus.PERSONALITY_SELECTION
    assert await load_game(deps, game.id) == game
    assert [type(e) for e in await storage.get_events(game.id)] == [
        PersonalityAssigned,
        PersonalityPicked,
    ]


async def test_the_game_starts_only_once_every_team_has_a_personality(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, selecting_personalities(num_teams=3))

    game = await assign_personality(deps, AssignPersonality(game.id, "player-1", "noir"))
    assert (game.status, game.rounds) == (GameStatus.PERSONALITY_SELECTION, [])
    game = await assign_personality(deps, AssignPersonality(game.id, "player-4", "absurdist"))
    assert (game.status, game.rounds) == (GameStatus.PERSONALITY_SELECTION, [])
    assert not any(isinstance(e, RoundStarted) for e in realtime.broadcasts_to(game.room_code))

    game = await assign_personality(deps, AssignPersonality(game.id, "player-6", "melodrama"))

    assert game.status == GameStatus.PLAYING
    assert {t.id: t.assigned_personality for t in game.teams} == {
        "team-1": "melodrama",
        "team-2": "noir",
        "team-3": "absurdist",
    }
    (current,) = game.rounds
    assert (current.round_number, current.acting_team_id) == (game.current_round, "team-1")
    started = realtime.broadcasts_to(game.room_code)[-1]
    assert isinstance(started, RoundStarted)
    assert started.acting_team_id == "team-1"
    # No team ever received the personality it was given.
    for team_id, sockets in TEAM_SOCKETS.items():
        own = game.get_team(team_id).assigned_personality
        for socket_id in sockets:
            assert own not in personality_ids_received(realtime, socket_id)

    events = await storage.get_events(game.id)
    write_evidence(
        "assign-personality/who-received-what.json",
        json.dumps(
            {
                socket_id: [
                    e.event_type
                    + (f"({e.personality_id})" if isinstance(e, PersonalityAssigned) else "")
                    for e in realtime.received_by(socket_id)
                ]
                for socket_id in sorted(set().union(*TEAM_SOCKETS.values()))
            },
            indent=2,
        ),
    )
    write_evidence(
        "assign-personality/events.jsonl", "".join(e.model_dump_json() + "\n" for e in events)
    )


async def test_the_stored_personality_is_one_submit_prompt_can_play_with(
    deps: GameDeps, realtime: RecordingRealtime
):
    llm = RecordingLLM()
    deps = replace(deps, llm=llm)
    game = await start(deps, realtime, selecting_personalities())
    await assign_personality(deps, AssignPersonality(game.id, "player-1", "melodrama"))
    await assign_personality(deps, AssignPersonality(game.id, "player-3", "shakespearean"))

    game = await submit_prompt(deps, SubmitPrompt(game.id, "player-1", "Cat steals the moon"))

    assert llm.personalities == [get_personality("shakespearean")]
    assert game.rounds[0].script is not None


@pytest.mark.parametrize("personality_id", sorted(PERSONALITIES))
async def test_any_starter_personality_can_be_picked(
    deps: GameDeps, realtime: RecordingRealtime, personality_id: str
):
    game = await start(deps, realtime, selecting_personalities())

    game = await assign_personality(deps, AssignPersonality(game.id, "player-2", personality_id))

    assert game.get_team("team-2").assigned_personality == personality_id


async def rejects(
    deps: GameDeps, storage: InMemoryStorage, game: Game, command: AssignPersonality, match: str
):
    events_before = await storage.get_events(game.id)
    with pytest.raises(GameRuleError, match=match):
        await assign_personality(deps, command)
    assert await storage.get_events(game.id) == events_before
    assert await load_game(deps, game.id) == game


async def test_a_team_cannot_pick_twice(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, selecting_personalities(num_teams=3))
    game = await assign_personality(deps, AssignPersonality(game.id, "player-1", "noir"))

    await rejects(
        deps, storage, game, AssignPersonality(game.id, "player-2", "absurdist"), "already"
    )


async def test_an_unknown_personality_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, selecting_personalities())

    await rejects(deps, storage, game, AssignPersonality(game.id, "player-1", "cowboy"), "cowboy")


async def test_picking_outside_personality_selection_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, lobby_with_two_teams())

    await rejects(
        deps, storage, game, AssignPersonality(game.id, "player-1", "noir"), "not picking"
    )


async def test_a_player_not_in_the_game_cannot_pick(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, selecting_personalities())

    await rejects(
        deps, storage, game, AssignPersonality(game.id, "player-99", "noir"), "not in this game"
    )


async def test_a_player_without_a_team_cannot_pick(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = selecting_personalities()
    game.get_player("player-1").team_id = None
    game.get_team("team-1").remove_player("player-1")
    game = await start(deps, realtime, game)

    await rejects(
        deps, storage, game, AssignPersonality(game.id, "player-1", "noir"), "not on a team"
    )


async def test_a_game_needs_two_teams_to_pick(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = selecting_personalities()
    game.remove_team("team-2")
    game = await start(deps, realtime, game)

    await rejects(
        deps, storage, game, AssignPersonality(game.id, "player-1", "noir"), "at least 2 teams"
    )


async def test_an_unknown_game_is_not_found(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await assign_personality(deps, AssignPersonality("nope", "player-1", "noir"))
