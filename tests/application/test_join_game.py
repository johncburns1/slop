"""Tests for the join game use case."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps
from slop.application.join_game import MAX_NAME_LENGTH, JoinGame, join_game
from slop.domain import Game, GameStatus, PlayerJoined
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.application.conftest import NOW, seat
from tests.builders import in_guessing_phase, lobby_with_two_teams
from tests.evidence import write_evidence


async def test_joining_adds_the_player_and_tells_the_room(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    lobby = await seat(storage, realtime, lobby_with_two_teams())

    joined = await join_game(deps, JoinGame(room_code="ABCD", name="Zed", socket_id="socket-new"))

    assert joined.player_id == "id-1"
    player = joined.game.get_player("id-1")
    assert (player.name, player.socket_id, player.team_id) == ("Zed", "socket-new", None)
    assert player.joined_at == NOW
    assert not player.is_creator
    assert await storage.get_snapshot(lobby.id) == joined.game
    (event,) = await storage.get_events(lobby.id)
    assert isinstance(event, PlayerJoined)
    assert (event.player_id, event.player_name, event.socket_id) == ("id-1", "Zed", "socket-new")
    assert realtime.rooms_of("socket-new") == {"ABCD"}
    assert realtime.broadcasts_to("ABCD") == [event]
    everyone = {p.socket_id for p in lobby.players} | {"socket-new"}
    assert realtime.who_received(PlayerJoined) == everyone
    write_evidence("join-game/events.jsonl", event.model_dump_json() + "\n")


async def test_the_first_player_to_join_an_empty_lobby_is_its_creator(
    deps: GameDeps, storage: InMemoryStorage
):
    await storage.save_snapshot(Game(id="game-1", room_code="ABCD"))

    joined = await join_game(deps, JoinGame(room_code="ABCD", name="Host", socket_id="s1"))

    assert joined.game.get_player(joined.player_id).is_creator


async def test_the_name_is_trimmed_and_the_room_code_matches_any_case(
    deps: GameDeps, storage: InMemoryStorage
):
    await storage.save_snapshot(lobby_with_two_teams())

    joined = await join_game(deps, JoinGame(room_code=" abcd ", name="  Zed  ", socket_id="s"))

    assert joined.game.get_player(joined.player_id).name == "Zed"


@pytest.mark.parametrize("name", ["Player 1", "player 1", "  PLAYER 1 ", "pLaYeR 1"])
async def test_a_name_already_taken_is_rejected_whatever_its_case(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, name: str
):
    await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="already taken"):
        await join_game(deps, JoinGame(room_code="ABCD", name=name, socket_id="socket-new"))

    await _assert_nothing_happened(storage, realtime)


@pytest.mark.parametrize("name", ["", "   ", "x" * (MAX_NAME_LENGTH + 1)])
async def test_a_name_that_is_blank_or_too_long_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, name: str
):
    await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="Name must be"):
        await join_game(deps, JoinGame(room_code="ABCD", name=name, socket_id="socket-new"))

    await _assert_nothing_happened(storage, realtime)


async def test_a_name_of_the_maximum_length_is_accepted(deps: GameDeps, storage: InMemoryStorage):
    await storage.save_snapshot(lobby_with_two_teams())
    name = "x" * MAX_NAME_LENGTH

    joined = await join_game(deps, JoinGame(room_code="ABCD", name=f" {name} ", socket_id="s"))

    assert joined.game.get_player(joined.player_id).name == name


async def test_an_unknown_room_code_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    await seat(storage, realtime, lobby_with_two_teams())

    with pytest.raises(GameNotFoundError):
        await join_game(deps, JoinGame(room_code="WXYZ", name="Zed", socket_id="socket-new"))

    await _assert_nothing_happened(storage, realtime)


async def test_joining_after_the_game_has_started_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    started = await seat(storage, realtime, in_guessing_phase())
    assert started.status == GameStatus.PLAYING

    with pytest.raises(GameRuleError, match="already started"):
        await join_game(deps, JoinGame(room_code="ABCD", name="Zed", socket_id="socket-new"))

    await _assert_nothing_happened(storage, realtime)


async def test_joining_a_full_game_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    lobby = lobby_with_two_teams()
    lobby.settings.max_players = len(lobby.players)
    await seat(storage, realtime, lobby)

    with pytest.raises(GameRuleError, match="full"):
        await join_game(deps, JoinGame(room_code="ABCD", name="Zed", socket_id="socket-new"))

    await _assert_nothing_happened(storage, realtime)


async def _assert_nothing_happened(storage: InMemoryStorage, realtime: RecordingRealtime) -> None:
    assert await storage.get_events("game-1") == []
    assert realtime.broadcasts_to("ABCD") == []
    assert realtime.rooms_of("socket-new") == frozenset()
