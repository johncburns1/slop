"""Tests for the shared use case flow."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.storage import InMemoryStorage, SQLiteStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, Private, commit, find_game, load_game
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
