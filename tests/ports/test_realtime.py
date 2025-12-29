"""Tests for Realtime port interface."""

from typing import Protocol

import pytest

from slop.domain import GameCreated, RoundStarted
from slop.domain.events import GameEvent
from slop.ports import RealtimePort


def test_realtime_port_is_protocol():
    """Test that RealtimePort is a Protocol (interface)."""
    assert issubclass(RealtimePort, Protocol)


def test_realtime_port_has_required_methods():
    """Test that RealtimePort defines all required methods."""
    assert hasattr(RealtimePort, "broadcast_to_room")
    assert hasattr(RealtimePort, "send_to_player")
    assert hasattr(RealtimePort, "join_room")
    assert hasattr(RealtimePort, "leave_room")


class MockRealtimeAdapter:
    """Mock realtime adapter for testing protocol compliance."""

    def __init__(self):
        self._rooms: dict[str, set[str]] = {}  # room_code -> set of socket_ids
        self._messages: list[tuple[str, str, GameEvent]] = []  # type, target, event

    async def broadcast_to_room(self, room_code: str, event: GameEvent) -> None:
        """Mock broadcast to room implementation."""
        self._messages.append(("broadcast", room_code, event))

    async def send_to_player(self, socket_id: str, event: GameEvent) -> None:
        """Mock send to player implementation."""
        self._messages.append(("send", socket_id, event))

    async def join_room(self, socket_id: str, room_code: str) -> None:
        """Mock join room implementation."""
        if room_code not in self._rooms:
            self._rooms[room_code] = set()
        self._rooms[room_code].add(socket_id)

    async def leave_room(self, socket_id: str, room_code: str) -> None:
        """Mock leave room implementation."""
        if room_code in self._rooms:
            self._rooms[room_code].discard(socket_id)


@pytest.mark.asyncio
async def test_realtime_port_broadcast_to_room():
    """Test broadcasting a domain event to a room."""
    adapter = MockRealtimeAdapter()
    event = GameCreated(
        game_id="game-1",
        room_code="ABCD",
        content_tone="family",
        max_players=12,
        rounds_per_team=3,
    )

    await adapter.broadcast_to_room(room_code="ABCD", event=event)

    assert len(adapter._messages) == 1
    msg_type, target, broadcasted_event = adapter._messages[0]
    assert msg_type == "broadcast"
    assert target == "ABCD"
    assert broadcasted_event.event_type == "GameCreated"
    assert broadcasted_event.game_id == "game-1"


@pytest.mark.asyncio
async def test_realtime_port_send_to_player():
    """Test sending a domain event to a specific player."""
    adapter = MockRealtimeAdapter()
    event = RoundStarted(
        game_id="game-1",
        round_number=1,
        acting_team_id="team-1",
    )

    await adapter.send_to_player(socket_id="socket-123", event=event)

    assert len(adapter._messages) == 1
    msg_type, target, sent_event = adapter._messages[0]
    assert msg_type == "send"
    assert target == "socket-123"
    assert sent_event.event_type == "RoundStarted"


@pytest.mark.asyncio
async def test_realtime_port_join_room():
    """Test adding a player to a room."""
    adapter = MockRealtimeAdapter()

    await adapter.join_room("socket-123", "ABCD")

    assert "socket-123" in adapter._rooms["ABCD"]


@pytest.mark.asyncio
async def test_realtime_port_leave_room():
    """Test removing a player from a room."""
    adapter = MockRealtimeAdapter()

    await adapter.join_room("socket-123", "ABCD")
    await adapter.leave_room("socket-123", "ABCD")

    assert "socket-123" not in adapter._rooms.get("ABCD", set())


@pytest.mark.asyncio
async def test_realtime_port_multiple_players_in_room():
    """Test multiple players in the same room."""
    adapter = MockRealtimeAdapter()

    await adapter.join_room("socket-1", "ABCD")
    await adapter.join_room("socket-2", "ABCD")
    await adapter.join_room("socket-3", "ABCD")

    assert len(adapter._rooms["ABCD"]) == 3
    assert "socket-1" in adapter._rooms["ABCD"]
    assert "socket-2" in adapter._rooms["ABCD"]
    assert "socket-3" in adapter._rooms["ABCD"]
