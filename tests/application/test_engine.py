"""Tests for the shared use case flow."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.storage import InMemoryStorage, SQLiteStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, GameLocks, Private, commit, find_game, load_game
from slop.domain import GameEvent, PlayerLeft, PromptSubmitted, ScriptGenerated
from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.domain.projection import ProjectionError, replay
from slop.ports import StoragePort
from tests.application.conftest import NOW
from tests.event_logs import GAME_ID, full_game_events, lobby_events, round_zero_events
from tests.evidence import write_evidence


def all_event_types() -> set[type[GameEvent]]:
    found: set[type[GameEvent]] = set()
    pending = list(GameEvent.__subclasses__())
    while pending:
        cls = pending.pop()
        found.add(cls)
        pending += cls.__subclasses__()
    return {cls for cls in found if cls.__module__ == "slop.domain.events"}


async def commit_one_by_one(deps: GameDeps, events: list[GameEvent], clock: FixedClock) -> None:
    game = None
    for event in events:
        clock.advance(timedelta(seconds=1))
        if game is None:
            game = await commit(deps, None, [event])
            continue
        async with deps.locks.hold(game.id):
            game = await commit(deps, game, [event])


@pytest.fixture(params=["in_memory", "sqlite"])
def any_storage(request: pytest.FixtureRequest, tmp_path: Path) -> StoragePort:
    if request.param == "sqlite":
        return SQLiteStorage(tmp_path / "slop.db")
    return InMemoryStorage()


async def test_replaying_saved_events_matches_the_snapshot_for_every_event_type(
    any_storage: StoragePort, deps: GameDeps, clock: FixedClock
):
    storage = any_storage
    deps = replace(deps, storage=storage)
    events = full_game_events()
    assert {type(e) for e in events} == all_event_types(), "add new event types to event_logs"

    await commit_one_by_one(deps, events, clock)

    saved = await storage.get_events(GAME_ID)
    snapshot = await storage.get_snapshot(GAME_ID)
    assert [e.event_type for e in saved] == [e.event_type for e in events]
    assert replay(saved) == snapshot
    log = "".join(e.model_dump_json() + "\n" for e in saved)
    write_evidence(f"replay-full-game/{type(storage).__name__}-events.jsonl", log)


async def test_commit_stamps_events_from_the_clock_and_id_generator(
    deps: GameDeps, storage: InMemoryStorage
):
    await commit(deps, None, lobby_events()[:2])

    saved = await storage.get_events(GAME_ID)
    assert [(e.event_id, e.timestamp) for e in saved] == [("id-1", NOW), ("id-2", NOW)]


async def test_commit_broadcasts_to_the_room_and_sends_private_events_to_players(
    deps: GameDeps, realtime: RecordingRealtime
):
    personalities_and_start, (prompt, script) = round_zero_events()[:3], round_zero_events()[3:5]
    game = await commit(deps, None, [*lobby_events(), *personalities_and_start])
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)

    async with deps.locks.hold(game.id):
        await commit(deps, game, [prompt, Private(script, ("player-1", "player-2"))])

    assert realtime.who_received(PromptSubmitted) == {f"socket-{n}" for n in range(1, 5)}
    assert realtime.who_received(ScriptGenerated) == {"socket-1", "socket-2"}
    assert ScriptGenerated not in {type(e) for e in realtime.broadcasts_to("ABCD")}


async def test_commit_stores_and_broadcasts_nothing_when_an_event_cannot_apply(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await commit(deps, None, lobby_events()[:1])
    good = lobby_events()[1]
    bad = PlayerLeft(game_id=GAME_ID, player_id="nobody")

    with pytest.raises(ProjectionError):
        async with deps.locks.hold(game.id):
            await commit(deps, game, [good, bad])

    assert len(await storage.get_events(GAME_ID)) == 1
    assert len(realtime.broadcasts_to("ABCD")) == 1


async def test_load_and_find_return_the_snapshot(deps: GameDeps):
    game = await commit(deps, None, lobby_events())

    assert await load_game(deps, GAME_ID) == game
    assert await find_game(deps, "ABCD") == game


async def test_load_and_find_raise_a_rule_error_for_unknown_games(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await load_game(deps, "missing")
    with pytest.raises(GameRuleError, match="ZZZZ"):
        await find_game(deps, "ZZZZ")


async def test_commit_refuses_a_caller_without_the_games_lock(
    deps: GameDeps, storage: InMemoryStorage
):
    game = await commit(deps, None, lobby_events()[:1])

    with pytest.raises(RuntimeError, match="without holding its lock"):
        await commit(deps, game, [lobby_events()[1]])

    assert len(await storage.get_events(GAME_ID)) == 1


async def test_holding_a_games_lock_twice_raises_instead_of_deadlocking():
    locks = GameLocks()
    async with locks.hold("game-1"):
        with pytest.raises(RuntimeError, match="already holds"):
            async with locks.hold("game-1"):
                pass


async def test_a_lock_is_held_only_by_the_task_inside_the_block():
    locks = GameLocks()

    async def held_elsewhere() -> bool:
        return locks.held("game-1")

    assert not locks.held("game-1")
    async with locks.hold("game-1"):
        assert locks.held("game-1")
        assert not locks.held("game-2")
        assert not await asyncio.create_task(held_elsewhere())
    assert not locks.held("game-1")


async def test_a_game_has_a_lock_only_while_it_is_held_or_awaited():
    locks = GameLocks()

    async def wait_for_lock() -> None:
        async with locks.hold("game-1"):
            pass

    async with locks.hold("game-1"):
        waiting = asyncio.create_task(wait_for_lock())
        cancelled = asyncio.create_task(wait_for_lock())
        await asyncio.sleep(0)
        assert len(locks) == 1
        cancelled.cancel()
        await asyncio.gather(cancelled, return_exceptions=True)
        assert len(locks) == 1
    await waiting

    assert len(locks) == 0


async def test_a_lock_is_released_when_its_block_raises():
    locks = GameLocks()

    with pytest.raises(ValueError):
        async with locks.hold("game-1"):
            raise ValueError

    assert len(locks) == 0
