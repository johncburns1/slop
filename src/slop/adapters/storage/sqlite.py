"""SQLite storage adapter.

Persists the append-only event log and the latest snapshot per game in a
single SQLite file. Uses the stdlib `sqlite3` module; each blocking call runs
in a worker thread via `asyncio.to_thread` so it never blocks the event loop.
"""

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from pydantic import TypeAdapter

from slop.domain.events import GameEvent
from slop.domain.game import Game

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_game_id ON events (game_id, seq);
CREATE TABLE IF NOT EXISTS snapshots (
    game_id TEXT PRIMARY KEY,
    room_code TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_room_code ON snapshots (room_code);
"""

# Snapshots are stored as JSON. The domain dataclasses stay unaware of this:
# the serializer lives here and rebuilds fresh Game objects on every load.
_GAME_JSON = TypeAdapter(Game)


def _event_classes() -> dict[str, type[GameEvent]]:
    """Map each concrete event's `event_type` to its class."""
    classes: dict[str, type[GameEvent]] = {}
    pending = list(GameEvent.__subclasses__())
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        event_type = cls.model_fields["event_type"].default
        if isinstance(event_type, str):
            classes[event_type] = cls
    return classes


def _load_event(event_type: str, payload: str) -> GameEvent:
    """Rebuild an event as the concrete subclass named by `event_type`."""
    cls = _event_classes().get(event_type)
    if cls is None:
        raise ValueError(f"Unknown stored event type: {event_type}")
    return cls.model_validate_json(payload)


class SQLiteStorage:
    """StoragePort implementation backed by a SQLite file.

    Events are serialized with Pydantic JSON and snapshots with an
    adapter-local JSON serializer, so loads always return new objects that
    share no mutable state with callers.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection and commit (or roll back) when the block ends."""
        with closing(sqlite3.connect(self._path)) as conn, conn:
            yield conn

    async def save_event(self, event: GameEvent) -> None:
        """Append the event to the game's log."""
        await asyncio.to_thread(self._save_event, event)

    def _save_event(self, event: GameEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (game_id, event_type, payload) VALUES (?, ?, ?)",
                (event.game_id, event.event_type, event.model_dump_json()),
            )

    async def get_events(self, game_id: str) -> list[GameEvent]:
        """Return the game's events in the order they were saved."""
        return await asyncio.to_thread(self._get_events, game_id)

    def _get_events(self, game_id: str) -> list[GameEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_type, payload FROM events WHERE game_id = ? ORDER BY seq",
                (game_id,),
            ).fetchall()
        return [_load_event(event_type, payload) for event_type, payload in rows]

    async def save_snapshot(self, game: Game) -> None:
        """Store the game, replacing any earlier snapshot."""
        await asyncio.to_thread(self._save_snapshot, game)

    def _save_snapshot(self, game: Game) -> None:
        payload = _GAME_JSON.dump_json(game).decode()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snapshots (game_id, room_code, payload) VALUES (?, ?, ?) "
                "ON CONFLICT (game_id) DO UPDATE SET "
                "room_code = excluded.room_code, payload = excluded.payload",
                (game.id, game.room_code, payload),
            )

    async def get_snapshot(self, game_id: str) -> Game | None:
        """Return the latest snapshot, or None if there is none."""
        return await asyncio.to_thread(
            self._load_snapshot, "SELECT payload FROM snapshots WHERE game_id = ?", game_id
        )

    async def get_game_by_room_code(self, room_code: str) -> Game | None:
        """Return the snapshot with this room code, or None."""
        return await asyncio.to_thread(
            self._load_snapshot,
            "SELECT payload FROM snapshots WHERE room_code = ? ORDER BY rowid LIMIT 1",
            room_code,
        )

    def _load_snapshot(self, query: str, key: str) -> Game | None:
        with self._connect() as conn:
            row = conn.execute(query, (key,)).fetchone()
        return _GAME_JSON.validate_json(row[0]) if row is not None else None

    async def delete_game(self, game_id: str) -> None:
        """Remove the game's events and snapshot. Unknown games are ignored."""
        await asyncio.to_thread(self._delete_game, game_id)

    def _delete_game(self, game_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM events WHERE game_id = ?", (game_id,))
            conn.execute("DELETE FROM snapshots WHERE game_id = ?", (game_id,))
