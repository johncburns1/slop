"""Tests for the SQLite storage adapter."""

import sqlite3
from pathlib import Path

import pytest

from slop.adapters.storage import SQLiteStorage
from slop.domain import GameCreated, PlayerJoined, ScriptGenerated
from slop.ports import StoragePort
from tests.adapters.storage.contract import (
    StoragePortContract,
    make_game,
    make_game_created,
    make_player_joined,
    make_script_generated,
)


class TestSQLiteStorage(StoragePortContract):
    """Run the StoragePort contract against SQLiteStorage on a temp file."""

    @pytest.fixture
    def storage(self, tmp_path: Path) -> StoragePort:
        return SQLiteStorage(tmp_path / "slop.db")


async def test_fresh_instance_reads_back_everything_on_the_same_file(tmp_path: Path) -> None:
    path = tmp_path / "slop.db"
    events = [make_game_created(), make_player_joined(), make_script_generated()]
    game = make_game()
    writer = SQLiteStorage(path)
    for event in events:
        await writer.save_event(event)
    await writer.save_snapshot(game)

    reader = SQLiteStorage(path)

    replayed = await reader.get_events("game-1")
    assert replayed == events
    assert [type(e) for e in replayed] == [GameCreated, PlayerJoined, ScriptGenerated]
    assert await reader.get_snapshot("game-1") == game
    assert await reader.get_game_by_room_code("ABCD") == game


def test_creates_the_schema_on_first_open(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "slop.db"

    SQLiteStorage(path)

    with sqlite3.connect(path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert {"events", "snapshots"} <= tables


async def test_unknown_stored_event_type_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "slop.db"
    storage = SQLiteStorage(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO events (game_id, event_type, payload) VALUES (?, ?, ?)",
            ("game-1", "NoSuchEvent", "{}"),
        )

    with pytest.raises(ValueError, match="NoSuchEvent"):
        await storage.get_events("game-1")
