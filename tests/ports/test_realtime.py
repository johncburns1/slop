"""Tests for Realtime port interface."""

from typing import Any, Protocol

import pytest

from slop.ports import RealtimePort


def test_realtime_port_is_protocol():
    """Test that RealtimePort is a Protocol (interface)."""
    assert issubclass(RealtimePort, Protocol)


def test_realtime_port_has_required_methods():
    """Test that RealtimePort defines all required methods."""
    assert hasattr(RealtimePort, "broadcast_to_room")
    assert hasattr(RealtimePort, "send_to_player")
    assert hasattr(RealtimePort, "add_player_to_room")
    assert hasattr(RealtimePort, "remove_player_from_room")
    assert hasattr(RealtimePort, "get_players_in_room")


class MockRealtimeAdapter:
    """Mock realtime adapter for testing protocol compliance."""

    def __init__(self):
        self._rooms: dict[str, set[str]] = {}  # room_id -> set of player_ids
        self._messages: list[tuple[str, str, dict[str, Any]]] = []  # type, target, data

    async def broadcast_to_room(self, room_id: str, event: str, data: dict[str, Any]) -> None:
        """Mock broadcast to room implementation."""
        self._messages.append(("broadcast", room_id, {"event": event, "data": data}))

    async def send_to_player(self, player_id: str, event: str, data: dict[str, Any]) -> None:
        """Mock send to player implementation."""
        self._messages.append(("send", player_id, {"event": event, "data": data}))

    async def add_player_to_room(self, player_id: str, room_id: str) -> None:
        """Mock add player to room implementation."""
        if room_id not in self._rooms:
            self._rooms[room_id] = set()
        self._rooms[room_id].add(player_id)

    async def remove_player_from_room(self, player_id: str, room_id: str) -> None:
        """Mock remove player from room implementation."""
        if room_id in self._rooms:
            self._rooms[room_id].discard(player_id)

    async def get_players_in_room(self, room_id: str) -> list[str]:
        """Mock get players in room implementation."""
        return list(self._rooms.get(room_id, set()))


@pytest.mark.asyncio
async def test_realtime_port_broadcast_to_room():
    """Test broadcasting a message to a room."""
    adapter = MockRealtimeAdapter()

    await adapter.broadcast_to_room(
        room_id="room-1",
        event="game_started",
        data={"game_id": "game-1"},
    )

    assert len(adapter._messages) == 1
    msg_type, target, payload = adapter._messages[0]
    assert msg_type == "broadcast"
    assert target == "room-1"
    assert payload["event"] == "game_started"


@pytest.mark.asyncio
async def test_realtime_port_send_to_player():
    """Test sending a message to a specific player."""
    adapter = MockRealtimeAdapter()

    await adapter.send_to_player(
        player_id="player-1",
        event="role_assigned",
        data={"role": "Hero"},
    )

    assert len(adapter._messages) == 1
    msg_type, target, payload = adapter._messages[0]
    assert msg_type == "send"
    assert target == "player-1"
    assert payload["event"] == "role_assigned"


@pytest.mark.asyncio
async def test_realtime_port_add_player_to_room():
    """Test adding a player to a room."""
    adapter = MockRealtimeAdapter()

    await adapter.add_player_to_room("player-1", "room-1")
    players = await adapter.get_players_in_room("room-1")

    assert "player-1" in players


@pytest.mark.asyncio
async def test_realtime_port_remove_player_from_room():
    """Test removing a player from a room."""
    adapter = MockRealtimeAdapter()

    await adapter.add_player_to_room("player-1", "room-1")
    await adapter.remove_player_from_room("player-1", "room-1")
    players = await adapter.get_players_in_room("room-1")

    assert "player-1" not in players


@pytest.mark.asyncio
async def test_realtime_port_get_players_in_room():
    """Test getting all players in a room."""
    adapter = MockRealtimeAdapter()

    await adapter.add_player_to_room("player-1", "room-1")
    await adapter.add_player_to_room("player-2", "room-1")
    await adapter.add_player_to_room("player-3", "room-1")

    players = await adapter.get_players_in_room("room-1")

    assert len(players) == 3
    assert "player-1" in players
    assert "player-2" in players
    assert "player-3" in players


@pytest.mark.asyncio
async def test_realtime_port_get_players_in_empty_room():
    """Test getting players from a room that doesn't exist."""
    adapter = MockRealtimeAdapter()

    players = await adapter.get_players_in_room("nonexistent-room")

    assert players == []
