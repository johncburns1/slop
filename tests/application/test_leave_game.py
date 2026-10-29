"""Tests for the leave game use case."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.create_game import CreateGame, create_game
from slop.application.engine import GameDeps, load_game
from slop.application.join_game import Joined, JoinGame, join_game
from slop.application.leave_game import LeaveGame, leave_game
from slop.domain import ContentTone, PlayerLeft
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.builders import lobby_with_two_teams
from tests.evidence import write_evidence


async def lobby_of_two(deps: GameDeps) -> tuple[Joined, Joined]:
    game = await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))
    alice = await join_game(deps, JoinGame(game.room_code, "Alice", "socket-a"))
    bob = await join_game(deps, JoinGame(game.room_code, "Bob", "socket-b"))
    return alice, bob


async def test_a_player_leaves_and_everyone_hears(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    alice, bob = await lobby_of_two(deps)
    game_id, room_code = bob.game.id, bob.game.room_code

    game = await leave_game(deps, LeaveGame(game_id, bob.player_id))

    assert [p.name for p in game.players] == ["Alice"]
    assert await load_game(deps, game_id) == game
    assert isinstance((await storage.get_events(game_id))[-1], PlayerLeft)
    for socket in ("socket-a", "socket-b"):
        assert isinstance(realtime.received_by(socket)[-1], PlayerLeft)
    assert realtime.members_of(room_code) == {"socket-a"}
    log = "".join(e.model_dump_json() + "\n" for e in await storage.get_events(game_id))
    write_evidence("join-and-leave/events.jsonl", log)


async def test_a_player_who_left_can_rejoin_with_the_same_name(deps: GameDeps):
    alice, bob = await lobby_of_two(deps)
    await leave_game(deps, LeaveGame(bob.game.id, bob.player_id))

    again = await join_game(deps, JoinGame(bob.game.room_code, "Bob", "socket-b2"))

    assert [p.name for p in again.game.players] == ["Alice", "Bob"]
    assert again.player_id != bob.player_id


async def test_leaving_also_leaves_the_team(deps: GameDeps, storage: InMemoryStorage):
    game = lobby_with_two_teams()
    await storage.save_snapshot(game)

    after = await leave_game(deps, LeaveGame(game.id, "player-2"))

    assert after.get_team("team-1").player_ids == ["player-1"]


async def test_an_unknown_player_is_rejected(deps: GameDeps):
    alice, _ = await lobby_of_two(deps)

    with pytest.raises(GameRuleError, match="not in this game"):
        await leave_game(deps, LeaveGame(alice.game.id, "nobody"))


async def test_an_unknown_game_is_rejected(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await leave_game(deps, LeaveGame("missing", "player-1"))


async def test_leaving_after_the_game_has_started_is_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = lobby_with_two_teams()
    game.start()
    await storage.save_snapshot(game)
    await realtime.join_room("socket-2", game.room_code)

    with pytest.raises(GameRuleError, match="already started"):
        await leave_game(deps, LeaveGame(game.id, "player-2"))

    assert len((await load_game(deps, game.id)).players) == 4
    assert realtime.members_of(game.room_code) == {"socket-2"}
