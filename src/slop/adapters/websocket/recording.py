"""Recording stand-in for a real-time transport.

Keeps room membership in memory and, instead of sending anything over a
network, records every event each socket would have received. Tests use its
query helpers to check who saw what, for example that only the acting team
received the script.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from slop.domain.events import GameEvent

if TYPE_CHECKING:
    from slop.ports.realtime import RealtimePort


@dataclass(frozen=True)
class Delivery:
    """One event arriving at one socket.

    `room_code` is the room it was broadcast to, or None for a direct send.
    """

    socket_id: str
    event: GameEvent
    room_code: str | None


class RecordingRealtime:
    """RealtimePort implementation that records deliveries instead of sending.

    Events are deep-copied when recorded and again when queried, so callers
    never share mutable state with the record. This matches a serializing
    transport, where each client gets its own copy.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, set[str]] = {}  # room_code -> socket_ids
        self._deliveries: list[Delivery] = []  # in send order
        self._broadcasts: dict[str, list[GameEvent]] = {}  # room_code -> events

    async def broadcast_to_room(self, room_code: str, event: GameEvent) -> None:
        """Record the event for every socket currently in the room."""
        self._broadcasts.setdefault(room_code, []).append(event.model_copy(deep=True))
        for socket_id in sorted(self._rooms.get(room_code, set())):
            self._record(socket_id, event, room_code)

    async def send_to_player(self, socket_id: str, event: GameEvent) -> None:
        """Record the event for this socket only."""
        self._record(socket_id, event, None)

    async def join_room(self, socket_id: str, room_code: str) -> None:
        """Add the socket to the room. Joining twice has no extra effect."""
        self._rooms.setdefault(room_code, set()).add(socket_id)

    async def leave_room(self, socket_id: str, room_code: str) -> None:
        """Remove the socket from the room. Unknown sockets are ignored."""
        self._rooms.get(room_code, set()).discard(socket_id)

    # Query helpers for tests

    def received_by(self, socket_id: str) -> list[GameEvent]:
        """Every event the socket received, in order."""
        return [d.event for d in self.deliveries_to(socket_id)]

    def deliveries_to(self, socket_id: str) -> list[Delivery]:
        """Every delivery to the socket, in order, including how it arrived."""
        return [
            Delivery(d.socket_id, d.event.model_copy(deep=True), d.room_code)
            for d in self._deliveries
            if d.socket_id == socket_id
        ]

    def who_received(self, event_type: type[GameEvent]) -> frozenset[str]:
        """The sockets that received at least one event of this type."""
        return frozenset(d.socket_id for d in self._deliveries if isinstance(d.event, event_type))

    def broadcasts_to(self, room_code: str) -> list[GameEvent]:
        """Every event broadcast to the room, in order, whoever was in it."""
        return [event.model_copy(deep=True) for event in self._broadcasts.get(room_code, [])]

    def members_of(self, room_code: str) -> frozenset[str]:
        """The sockets currently in the room."""
        return frozenset(self._rooms.get(room_code, set()))

    def rooms_of(self, socket_id: str) -> frozenset[str]:
        """The rooms the socket is currently in."""
        return frozenset(room for room, members in self._rooms.items() if socket_id in members)

    def _record(self, socket_id: str, event: GameEvent, room_code: str | None) -> None:
        self._deliveries.append(Delivery(socket_id, event.model_copy(deep=True), room_code))


if TYPE_CHECKING:
    # mypy fails here if the adapter drifts from the port's signature.
    _port_check: RealtimePort = RecordingRealtime()
