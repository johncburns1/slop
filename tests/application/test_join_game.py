"""Tests for the join game use case."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.create_game import CreateGame, create_game
from slop.application.engine import GameDeps, load_game
from slop.application.join_game import MAX_NAME_LENGTH, JoinGame, join_game
from slop.domain import ContentTone, Game, GameStatus, PlayerJoined
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.application.conftest import NOW
from tests.builders import lobby_with_two_teams


async def new_game(deps: GameDeps, **settings: int) -> Game:
    return await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY, **settings))


async def test_a_player_joins_by_room_code_and_everyone_hears(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await new_game(deps)
    first = await join_game(deps, JoinGame(game.room_code, "Alice", "socket-a"))

    second = await join_game(deps, JoinGame(game.room_code, "Bob", "socket-b"))

    player = second.game.get_player(second.player_id)
    assert (player.name, player.socket_id, player.joined_at) == ("Bob", "socket-b", NOW)
    assert [p.name for p in second.game.players] == ["Alice", "Bob"]
    assert second.game.get_player(first.player_id).is_creator is True
    assert await load_game(deps, game.id) == second.game
    assert [type(e) for e in await storage.get_events(game.id)][-2:] == [PlayerJoined] * 2
    assert realtime.members_of(game.room_code) == {"socket-a", "socket-b"}
    assert [
        e.player_name for e in realtime.received_by("socket-a") if isinstance(e, PlayerJoined)
    ] == [
        "Alice",
        "Bob",
    ]


async def test_the_joining_player_hears_their_own_join(deps: GameDeps, realtime: RecordingRealtime):
    game = await new_game(deps)

    joined = await join_game(deps, JoinGame(game.room_code, "Alice", "socket-a"))

    (event,) = realtime.received_by("socket-a")
    assert isinstance(event, PlayerJoined)
    assert event.player_id == joined.player_id


async def test_room_codes_and_names_are_tidied(deps: GameDeps):
    game = await new_game(deps)

    joined = await join_game(deps, JoinGame(f" {game.room_code.lower()} ", "  Alice ", "socket-a"))

    assert joined.game.id == game.id
    assert joined.game.get_player(joined.player_id).name == "Alice"


async def test_an_unknown_room_code_is_rejected(deps: GameDeps):
    with pytest.raises(GameNotFoundError, match="ZZZZ"):
        await join_game(deps, JoinGame("ZZZZ", "Alice", "socket-a"))


@pytest.mark.parametrize("taken", ["Alice", "alice", " ALICE "])
async def test_a_name_already_in_the_game_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, taken: str
):
    game = await new_game(deps)
    await join_game(deps, JoinGame(game.room_code, "Alice", "socket-a"))

    with pytest.raises(GameRuleError, match="already taken"):
        await join_game(deps, JoinGame(game.room_code, taken, "socket-b"))

    assert len((await load_game(deps, game.id)).players) == 1
    assert len(await storage.get_events(game.id)) == 2
    assert realtime.rooms_of("socket-b") == frozenset()


@pytest.mark.parametrize("name", ["", "   ", "x" * (MAX_NAME_LENGTH + 1)])
async def test_blank_or_overlong_names_are_rejected(deps: GameDeps, name: str):
    game = await new_game(deps)

    with pytest.raises(GameRuleError, match="Name"):
        await join_game(deps, JoinGame(game.room_code, name, "socket-a"))


async def test_joining_after_the_game_has_started_is_rejected(
    deps: GameDeps, storage: InMemoryStorage
):
    started = lobby_with_two_teams()
    started.start()
    await storage.save_snapshot(started)

    with pytest.raises(GameRuleError, match="already started"):
        await join_game(deps, JoinGame(started.room_code, "Latecomer", "socket-late"))

    assert (await load_game(deps, started.id)).status == GameStatus.PLAYING
    assert len((await load_game(deps, started.id)).players) == 4


async def test_a_full_game_is_rejected(deps: GameDeps):
    game = await new_game(deps, max_players=3)
    for name in ("A", "B", "C"):
        await join_game(deps, JoinGame(game.room_code, name, f"socket-{name}"))

    with pytest.raises(GameRuleError, match="full"):
        await join_game(deps, JoinGame(game.room_code, "D", "socket-D"))
