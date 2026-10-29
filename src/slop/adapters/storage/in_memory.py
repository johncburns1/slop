"""In-memory storage adapter.

A process-local stand-in for persistent storage, used in tests and local
development. State is lost when the process exits.
"""

from copy import deepcopy

from slop.domain.events import GameEvent
from slop.domain.game import Game


class InMemoryStorage:
    """StoragePort implementation backed by dictionaries.

    Everything crossing the boundary is deep-copied, both on save and on
    load, so callers never share mutable state with what is stored. This
    matches the behavior of a serializing adapter such as SQLite.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[GameEvent]] = {}  # game_id -> events
        self._snapshots: dict[str, Game] = {}  # game_id -> snapshot

    async def save_event(self, event: GameEvent) -> None:
        """Append a copy of the event to the game's log."""
        self._events.setdefault(event.game_id, []).append(event.model_copy(deep=True))

    async def get_events(self, game_id: str) -> list[GameEvent]:
        """Return copies of the game's events in the order they were saved."""
        return [event.model_copy(deep=True) for event in self._events.get(game_id, [])]

    async def save_snapshot(self, game: Game) -> None:
        """Store a copy of the game, replacing any earlier snapshot."""
        self._snapshots[game.id] = deepcopy(game)

    async def get_snapshot(self, game_id: str) -> Game | None:
        """Return a copy of the latest snapshot, or None if there is none."""
        game = self._snapshots.get(game_id)
        return deepcopy(game) if game is not None else None

    async def get_game_by_room_code(self, room_code: str) -> Game | None:
        """Return a copy of the snapshot with this room code, or None."""
        for game in self._snapshots.values():
            if game.room_code == room_code:
                return deepcopy(game)
        return None

    async def delete_game(self, game_id: str) -> None:
        """Remove the game's events and snapshot. Unknown games are ignored."""
        self._events.pop(game_id, None)
        self._snapshots.pop(game_id, None)
