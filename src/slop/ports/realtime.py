"""Realtime communication port interface.

This port defines the contract for real-time communication
between the server and clients (WebSocket, etc.).
"""

from typing import Any, Protocol


class RealtimePort(Protocol):
    """Interface for real-time communication with clients.

    Implementations can use WebSocket libraries (Socket.io, etc.)
    to provide synchronized game state across all player devices.
    """

    async def broadcast_to_room(self, room_id: str, event: str, data: dict[str, Any]) -> None:
        """Broadcast a message to all players in a room.

        Args:
            room_id: The room/game ID to broadcast to
            event: The event type/name
            data: The event payload data
        """
        ...

    async def send_to_player(self, player_id: str, event: str, data: dict[str, Any]) -> None:
        """Send a message to a specific player.

        Args:
            player_id: The player's unique identifier
            event: The event type/name
            data: The event payload data
        """
        ...

    async def add_player_to_room(self, player_id: str, room_id: str) -> None:
        """Add a player to a room for real-time updates.

        Args:
            player_id: The player's unique identifier
            room_id: The room/game ID
        """
        ...

    async def remove_player_from_room(self, player_id: str, room_id: str) -> None:
        """Remove a player from a room.

        Args:
            player_id: The player's unique identifier
            room_id: The room/game ID
        """
        ...

    async def get_players_in_room(self, room_id: str) -> list[str]:
        """Get all players currently in a room.

        Args:
            room_id: The room/game ID

        Returns:
            List of player IDs in the room
        """
        ...
