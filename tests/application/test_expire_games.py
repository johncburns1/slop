"""Tests for the expire games use case."""

from dataclasses import replace
from datetime import timedelta

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.ids import SequentialIds
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.create_game import CreateGame, create_game
from slop.application.engine import GameDeps, find_game
from slop.application.expire_games import expire_games
from slop.application.join_game import JoinGame, join_game
from slop.application.play_again import PlayAgain, play_again
from slop.application.rejoin_game import RejoinGame, rejoin_game
from slop.domain import ContentTone, Game, GameStatus
from slop.domain.errors import GameNotFoundError
from slop.domain.expiry import ExpiryPolicy
from tests.application.test_play_again import finished
from tests.builders import scored_after_last_round

POLICY = ExpiryPolicy(idle=timedelta(hours=2), after_finish=timedelta(minutes=30))


async def new_game(deps: GameDeps, name: str = "Alice") -> tuple[Game, str]:
    """Create a game with one player. Returns the game and the player's id."""
    game = await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))
    joined = await join_game(deps, JoinGame(game.room_code, name, f"socket-{name}"))
    return joined.game, joined.player_id


async def test_an_idle_game_is_deleted_and_its_room_code_stops_resolving(
    deps: GameDeps, storage: InMemoryStorage, clock: FixedClock
):
    idle, player_id = await new_game(deps)
    clock.advance(timedelta(hours=1))
    active, _ = await new_game(deps, "Bob")
    clock.advance(timedelta(hours=1))

    expired = await expire_games(deps, POLICY)

    assert expired == [idle.id]
    assert await storage.get_events(idle.id) == []
    assert await storage.get_snapshot(idle.id) is None
    with pytest.raises(GameNotFoundError):
        await find_game(deps, idle.room_code)
    with pytest.raises(GameNotFoundError):
        await join_game(deps, JoinGame(idle.room_code, "Carol", "socket-carol"))
    with pytest.raises(GameNotFoundError):
        await rejoin_game(deps, RejoinGame(idle.room_code, player_id, "socket-new"))
    assert await storage.get_snapshot(active.id) == active
    assert len(await storage.get_events(active.id)) == 2


async def test_any_event_keeps_a_game_alive(deps: GameDeps, clock: FixedClock):
    game, _ = await new_game(deps)
    clock.advance(timedelta(hours=1, minutes=59))
    await join_game(deps, JoinGame(game.room_code, "Bob", "socket-bob"))
    clock.advance(timedelta(hours=1, minutes=59))

    assert await expire_games(deps, POLICY) == []


async def test_a_finished_game_is_deleted_after_the_shorter_period(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, clock: FixedClock
):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))
    assert game.status == GameStatus.FINISHED

    clock.advance(timedelta(minutes=29))
    assert await expire_games(deps, POLICY) == []
    clock.advance(timedelta(minutes=1))
    assert await expire_games(deps, POLICY) == [game.id]
    assert await storage.get_snapshot(game.id) is None


async def test_playing_again_goes_back_to_the_idle_period(
    deps: GameDeps, realtime: RecordingRealtime, clock: FixedClock
):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))
    clock.advance(timedelta(minutes=20))
    await play_again(deps, PlayAgain(game.id, "player-1"))

    clock.advance(timedelta(hours=1))
    assert await expire_games(deps, POLICY) == []
    clock.advance(timedelta(hours=1))
    assert await expire_games(deps, POLICY) == [game.id]


async def test_a_room_code_is_reissued_only_once_its_game_has_expired(
    deps: GameDeps, clock: FixedClock
):
    deps = replace(deps, ids=SequentialIds(["ABCD", "ABCD", "WXYZ", "ABCD"]))
    family = CreateGame(content_tone=ContentTone.FAMILY)
    first = await create_game(deps, family)
    clock.advance(timedelta(hours=2))
    second = await create_game(deps, family)  # ABCD is still held by the first game

    assert await expire_games(deps, POLICY) == [first.id]
    third = await create_game(deps, family)

    assert (first.room_code, second.room_code, third.room_code) == ("ABCD", "WXYZ", "ABCD")
    assert (await find_game(deps, "ABCD")).id == third.id
