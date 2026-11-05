"""The shared flow every use case follows: lock, load, check, emit, store, broadcast.

See the ``slop.application`` package docstring for how a use case uses it.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from slop.domain.errors import GameNotFoundError
from slop.domain.events import GameEvent
from slop.domain.game import Game
from slop.domain.projection import apply_event
from slop.ports.clock import Clock
from slop.ports.ids import IdGenerator
from slop.ports.llm import LLMPort
from slop.ports.moderation import ModerationPort
from slop.ports.realtime import RealtimePort
from slop.ports.storage import StoragePort


@dataclass(eq=False)
class _GameLock:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0  # tasks holding it or waiting for it
    owner: asyncio.Task[object] | None = None


class GameLocks:
    """One lock per game id, so commands for a game run one at a time.

    A game's lock exists only while a task holds it or waits for it, so locks
    never outlive their use, whether or not the game still exists.
    """

    def __init__(self) -> None:
        self._locks: dict[str, _GameLock] = {}

    def __len__(self) -> int:
        """How many games have a lock right now."""
        return len(self._locks)

    @asynccontextmanager
    async def hold(self, game_id: str) -> AsyncIterator[None]:
        """Hold the game's lock for the block. It isn't reentrant, so that raises at once.

        Raises:
            RuntimeError: If this task already holds the lock
        """
        if self.held(game_id):
            raise RuntimeError(f"This task already holds the lock of game {game_id}")
        entry = self._locks.setdefault(game_id, _GameLock())
        entry.users += 1
        try:
            async with entry.lock:
                entry.owner = asyncio.current_task()
                try:
                    yield
                finally:
                    entry.owner = None
        finally:
            entry.users -= 1
            if entry.users == 0:
                del self._locks[game_id]

    def held(self, game_id: str) -> bool:
        """Return whether the current task holds the game's lock."""
        entry = self._locks.get(game_id)
        return entry is not None and entry.owner is asyncio.current_task()


@dataclass(frozen=True)
class GameDeps:
    """Everything a use case needs from outside the domain, and the locks of its games."""

    storage: StoragePort
    realtime: RealtimePort
    clock: Clock
    ids: IdGenerator
    llm: LLMPort
    moderation: ModerationPort
    locks: GameLocks = field(default_factory=GameLocks)


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


@asynccontextmanager
async def locked_game(deps: GameDeps, game_id: str) -> AsyncIterator[Game]:
    """Hold the game's lock for the block, and give it the game's latest snapshot.

    Raises:
        GameNotFoundError: If there is no such game, perhaps no longer
    """
    async with deps.locks.hold(game_id):
        yield await load_game(deps, game_id)


@asynccontextmanager
async def locked_room(deps: GameDeps, room_code: str) -> AsyncIterator[Game]:
    """Like ``locked_game``, for the game with this room code.

    Raises:
        GameNotFoundError: If no game has this room code, perhaps no longer
    """
    game_id = (await find_game(deps, room_code)).id
    async with locked_game(deps, game_id) as game:
        yield game


async def commit(deps: GameDeps, game: Game | None, events: Sequence[GameEvent | Private]) -> Game:
    """Apply, store, and broadcast events, and return the game as it is after them.

    ``game`` is the state the events apply to (None only for ``GameCreated``).
    Each event gets its ``event_id`` and ``timestamp`` from ``deps``, so use
    cases don't set them. Plain events go to the whole room; wrap an event in
    ``Private`` to send it only to those players.

    All events are applied before anything is stored, so an inconsistent
    event raises without side effects. Then every event is appended, the
    snapshot saved, and only then is anything broadcast.

    The caller must hold the game's lock (see ``locked_game``) since loading
    ``game``. A new game needs none, as nothing else can know of it yet.

    Raises:
        RuntimeError: If the caller doesn't hold the game's lock
    """
    if game is not None and not deps.locks.held(game.id):
        raise RuntimeError(f"Committing to game {game.id} without holding its lock")
    # (event, socket_ids), where socket_ids None means the whole room. A private
    # event's players are looked up as the game is once it applies, so one can
    # reach a player whom a later event in the same commit removes.
    outgoing: list[tuple[GameEvent, tuple[str, ...] | None]] = []
    for item in events:
        event = _stamp(deps, item.event if isinstance(item, Private) else item)
        game = apply_event(game, event)
        sockets = (
            tuple(game.get_player(player_id).socket_id for player_id in item.player_ids)
            if isinstance(item, Private)
            else None
        )
        outgoing.append((event, sockets))
    if game is None:
        raise ValueError("commit needs at least one event")

    for event, _ in outgoing:
        await deps.storage.save_event(event)
    await deps.storage.save_snapshot(game)

    for event, socket_ids in outgoing:
        if socket_ids is None:
            await deps.realtime.broadcast_to_room(game.room_code, event)
            continue
        for socket_id in socket_ids:
            await deps.realtime.send_to_player(socket_id, event)
    return game


def _stamp(deps: GameDeps, event: GameEvent) -> GameEvent:
    return event.model_copy(update={"event_id": deps.ids.new_id(), "timestamp": deps.clock.now()})
