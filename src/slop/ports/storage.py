"""Storage port interface.

This port defines the contract for event sourcing persistence,
including event log storage and materialized snapshots.
"""

from typing import Protocol

from slop.domain.events import GameEvent
from slop.domain.game import Game


class StoragePort(Protocol):
    """Interface for event sourcing storage.

    Implements hybrid event sourcing with append-only event log
    and materialized snapshots for fast reads.
    """

    async def save_event(self, event: GameEvent) -> None:
        """Append an event to the event log.

        Events are immutable and append-only. This operation must be
        atomic and durable before broadcasting to clients.

        Args:
            event: The domain event to persist
        """
        ...

    async def get_events(self, game_id: str) -> list[GameEvent]:
        """Retrieve all events for a game.

        Used for event replay and crash recovery.

        Args:
            game_id: The game's unique identifier

        Returns:
            List of events in chronological order
        """
        ...

    async def save_snapshot(self, game: Game) -> None:
        """Save a materialized snapshot of current game state.

        Snapshots enable fast reads without replaying entire event log.
        Updated after each event is processed.

        Args:
            game: The current game state to snapshot
        """
        ...

    async def get_snapshot(self, game_id: str) -> Game | None:
        """Retrieve the latest snapshot of game state.

        Args:
            game_id: The game's unique identifier

        Returns:
            The Game snapshot if found, None otherwise
        """
        ...

    async def get_game_by_room_code(self, room_code: str) -> Game | None:
        """Retrieve a game by room code.

        Returns the materialized snapshot for the game with this room code.

        Args:
            room_code: The game's room code

        Returns:
            The Game object if found, None otherwise
        """
        ...

    async def delete_game(self, game_id: str) -> None:
        """Delete a game and all its events.

        Called when a game is completed. Removes both event log
        and snapshot to clean up storage.

        Args:
            game_id: The game's unique identifier
        """
        ...
