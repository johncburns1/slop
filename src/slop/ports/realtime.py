"""Realtime communication port interface.

This port defines the contract for real-time communication
between the server and clients (WebSocket, etc.).
"""

from typing import Protocol

from slop.domain.events import GameEvent


class RealtimePort(Protocol):
    """Interface for real-time communication with clients.

    Implementations use WebSocket libraries (Socket.io, etc.)
    to broadcast domain events and synchronize game state across
    all player devices in real-time.
    """

    async def broadcast_to_room(self, room_code: str, event: GameEvent) -> None:
        """Broadcast a domain event to all players in a room.

        Events are serialized to JSON and sent to all connected
        clients in the specified room. Clients use these events
        to update their local state mirrors.

        Args:
            room_code: The game's room code to broadcast to
            event: The domain event to broadcast
        """
        ...

    async def send_to_player(self, socket_id: str, event: GameEvent) -> None:
        """Send a domain event to a specific player.

        Used for player-specific notifications or view-specific data
        (e.g., script content visible only to acting team).

        Args:
            socket_id: The player's WebSocket connection ID
            event: The domain event to send
        """
        ...

    async def join_room(self, socket_id: str, room_code: str) -> None:
        """Add a player's connection to a room.

        Called when a player joins a game. Enables them to receive
        broadcast events for that room.

        Args:
            socket_id: The player's WebSocket connection ID
            room_code: The game's room code
        """
        ...

    async def leave_room(self, socket_id: str, room_code: str) -> None:
        """Remove a player's connection from a room.

        Called when a player leaves a game or disconnects.

        Args:
            socket_id: The player's WebSocket connection ID
            room_code: The game's room code
        """
        ...
