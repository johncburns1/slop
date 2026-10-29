"""Tests for the leave game use case."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps
from slop.application.leave_game import LeaveGame, leave_game
from slop.domain import Player, PlayerLeft
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.application.conftest import seat
from tests.builders import in_guessing_phase, lobby_with_two_teams
from tests.evidence import write_evidence


async def test_leaving_removes_the_player_from_the_game_team_and_room(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    lobby = await seat(storage, realtime, lobby_with_two_teams())

    game = await leave_game(deps, LeaveGame(game_id="game-1", player_id="player-2"))

    assert [p.id for p in game.players] == ["player-1", "player-3", "player-4"]
    assert game.get_team("team-1").player_ids == ["player-1"]
    assert game.get_team("team-2").player_ids == ["player-3", "player-4"]
    assert await storage.get_snapshot(lobby.id) == game
    (event,) = await storage.get_events(lobby.id)
    assert isinstance(event, PlayerLeft)
    assert event.player_id == "player-2"
    assert realtime.broadcasts_to("ABCD") == [event]
    # The leaver hears their own leave, then their socket is out of the room.
    assert realtime.who_received(PlayerLeft) == {p.socket_id for p in lobby.players}
    assert realtime.rooms_of("socket-2") == frozenset()
    assert realtime.members_of("ABCD") == {"socket-1", "socket-3", "socket-4"}
    write_evidence("leave-game/events.jsonl", event.model_dump_json() + "\n")


async def test_a_player_without_a_team_can_leave(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    lobby = lobby_with_two_teams()
    lobby.add_player(Player(id="loner", name="Loner", socket_id="socket-loner"))
    await seat(storage, realtime, lobby)

    game = await leave_game(deps, LeaveGame(game_id="game-1", player_id="loner"))

    assert "loner" not in [p.id for p in game.players]
    assert [t.player_ids for t in game.teams] == [t.player_ids for t in lobby.teams]
    assert realtime.rooms_of("socket-loner") == frozenset()


async def test_a_player_can_leave_a_game_in_progress(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    await seat(storage, realtime, in_guessing_phase())

    game = await leave_game(deps, LeaveGame(game_id="game-1", player_id="player-4"))

    assert game.get_team("team-2").player_ids == ["player-3"]
    assert realtime.who_received(PlayerLeft) == {f"socket-{n}" for n in range(1, 5)}


async def test_a_player_not_in_the_game_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="not in this game"):
        await leave_game(deps, LeaveGame(game_id="game-1", player_id="stranger"))

    assert await storage.get_events("game-1") == []
    assert realtime.broadcasts_to("ABCD") == []


async def test_an_unknown_game_is_rejected(deps: GameDeps, realtime: RecordingRealtime):
    with pytest.raises(GameNotFoundError):
        await leave_game(deps, LeaveGame(game_id="nope", player_id="player-1"))
