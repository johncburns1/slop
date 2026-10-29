"""The shared flow every use case follows: load, check, emit, store, broadcast.

See the ``slop.application`` package docstring for how a use case uses it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from slop.domain.errors import GameNotFoundError
from slop.domain.events import GameEvent
from slop.domain.game import Game
from slop.domain.projection import apply_event
from slop.ports.clock import Clock
from slop.ports.ids import IdGenerator
from slop.ports.llm import LLMPort
from slop.ports.realtime import RealtimePort
from slop.ports.storage import StoragePort


@dataclass(frozen=True)
class GameDeps:
    """Everything a use case needs from outside the domain."""

    storage: StoragePort
    realtime: RealtimePort
    clock: Clock
    ids: IdGenerator
    llm: LLMPort


@dataclass(frozen=True)
class Private:
    """An event sent only to some players instead of the whole room."""

    event: GameEvent
    player_ids: tuple[str, ...]


async def load_game(deps: GameDeps, game_id: str) -> Game:
    """Return the game's latest snapshot.

    Raises:
        GameNotFoundError: If there is no such game
    """
    game = await deps.storage.get_snapshot(game_id)
    if game is None:
        raise GameNotFoundError(f"No game {game_id}")
    return game


async def find_game(deps: GameDeps, room_code: str) -> Game:
    """Return the latest snapshot of the game with this room code.

    Raises:
        GameNotFoundError: If no game has this room code
    """
    game = await deps.storage.get_game_by_room_code(room_code)
    if game is None:
        raise GameNotFoundError(f"No game with room code {room_code}")
    return game


async def commit(deps: GameDeps, game: Game | None, events: Sequence[GameEvent | Private]) -> Game:
    """Apply, store, and broadcast events, and return the game as it is after them.

    ``game`` is the state the events apply to (None only for ``GameCreated``).
    Each event gets its ``event_id`` and ``timestamp`` from ``deps``, so use
    cases don't set them. Plain events go to the whole room; wrap an event in
    ``Private`` to send it only to those players.

    All events are applied before anything is stored, so an inconsistent
    event raises without side effects. Then every event is appended, the
    snapshot saved, and only then is anything broadcast.
    """
    # (event, player_ids), where player_ids None means the whole room.
    outgoing = [
        (_stamp(deps, item.event), item.player_ids)
        if isinstance(item, Private)
        else (_stamp(deps, item), None)
        for item in events
    ]
    for event, _ in outgoing:
        game = apply_event(game, event)
    if game is None:
        raise ValueError("commit needs at least one event")

    for event, _ in outgoing:
        await deps.storage.save_event(event)
    await deps.storage.save_snapshot(game)

    for event, player_ids in outgoing:
        if player_ids is None:
            await deps.realtime.broadcast_to_room(game.room_code, event)
            continue
        for player_id in player_ids:
            await deps.realtime.send_to_player(game.get_player(player_id).socket_id, event)
    return game


def _stamp(deps: GameDeps, event: GameEvent) -> GameEvent:
    return event.model_copy(update={"event_id": deps.ids.new_id(), "timestamp": deps.clock.now()})
