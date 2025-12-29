"""Tests for Storage port interface."""

from typing import Protocol

import pytest

from slop.domain import Game, GameCreated, PlayerJoined
from slop.domain.events import GameEvent
from slop.ports import StoragePort


def test_storage_port_is_protocol():
    """Test that StoragePort is a Protocol (interface)."""
    assert issubclass(StoragePort, Protocol)


def test_storage_port_has_required_methods():
    """Test that StoragePort defines all required methods for event sourcing."""
    assert hasattr(StoragePort, "save_event")
    assert hasattr(StoragePort, "get_events")
    assert hasattr(StoragePort, "save_snapshot")
    assert hasattr(StoragePort, "get_snapshot")
    assert hasattr(StoragePort, "get_game_by_room_code")
    assert hasattr(StoragePort, "delete_game")


class MockEventSourcedStorageAdapter:
    """Mock event-sourced storage adapter for testing protocol compliance."""

    def __init__(self):
        self._events: dict[str, list[GameEvent]] = {}  # game_id -> events
        self._snapshots: dict[str, Game] = {}  # game_id -> snapshot
        self._room_codes: dict[str, str] = {}  # room_code -> game_id

    async def save_event(self, event: GameEvent) -> None:
        """Mock save event implementation."""
        if event.game_id not in self._events:
            self._events[event.game_id] = []
        self._events[event.game_id].append(event)

    async def get_events(self, game_id: str) -> list[GameEvent]:
        """Mock get events implementation."""
        return self._events.get(game_id, [])

    async def save_snapshot(self, game: Game) -> None:
        """Mock save snapshot implementation."""
        self._snapshots[game.id] = game
        self._room_codes[game.room_code] = game.id

    async def get_snapshot(self, game_id: str) -> Game | None:
        """Mock get snapshot implementation."""
        return self._snapshots.get(game_id)

    async def get_game_by_room_code(self, room_code: str) -> Game | None:
        """Mock get game by room code implementation."""
        game_id = self._room_codes.get(room_code)
        if game_id:
            return self._snapshots.get(game_id)
        return None

    async def delete_game(self, game_id: str) -> None:
        """Mock delete game implementation."""
        if game_id in self._events:
            del self._events[game_id]
        if game_id in self._snapshots:
            game = self._snapshots[game_id]
            del self._snapshots[game_id]
            if game.room_code in self._room_codes:
                del self._room_codes[game.room_code]


@pytest.mark.asyncio
async def test_storage_port_save_and_get_events():
    """Test saving and retrieving events."""
    adapter = MockEventSourcedStorageAdapter()
    event1 = GameCreated(
        game_id="game-1",
        room_code="ABCD",
        content_tone="family",
        max_players=12,
        rounds_per_team=3,
    )
    event2 = PlayerJoined(
        game_id="game-1",
        player_id="player-1",
        player_name="Alice",
        socket_id="socket-123",
    )

    await adapter.save_event(event1)
    await adapter.save_event(event2)
    events = await adapter.get_events("game-1")

    assert len(events) == 2
    assert events[0].event_type == "GameCreated"
    assert events[1].event_type == "PlayerJoined"


@pytest.mark.asyncio
async def test_storage_port_save_and_get_snapshot():
    """Test saving and retrieving a game snapshot."""
    adapter = MockEventSourcedStorageAdapter()
    game = Game(id="game-1", room_code="ABCD")

    await adapter.save_snapshot(game)
    retrieved = await adapter.get_snapshot("game-1")

    assert retrieved is not None
    assert retrieved.id == "game-1"
    assert retrieved.room_code == "ABCD"


@pytest.mark.asyncio
async def test_storage_port_get_game_by_room_code():
    """Test retrieving a game by room code."""
    adapter = MockEventSourcedStorageAdapter()
    game = Game(id="game-1", room_code="WXYZ")

    await adapter.save_snapshot(game)
    retrieved = await adapter.get_game_by_room_code("WXYZ")

    assert retrieved is not None
    assert retrieved.id == "game-1"
    assert retrieved.room_code == "WXYZ"


@pytest.mark.asyncio
async def test_storage_port_delete_game():
    """Test deleting a game and its events."""
    adapter = MockEventSourcedStorageAdapter()
    game = Game(id="game-1", room_code="TEST")
    event = GameCreated(
        game_id="game-1",
        room_code="TEST",
        content_tone="family",
        max_players=12,
        rounds_per_team=3,
    )

    await adapter.save_snapshot(game)
    await adapter.save_event(event)
    await adapter.delete_game("game-1")

    retrieved_snapshot = await adapter.get_snapshot("game-1")
    retrieved_events = await adapter.get_events("game-1")

    assert retrieved_snapshot is None
    assert len(retrieved_events) == 0
