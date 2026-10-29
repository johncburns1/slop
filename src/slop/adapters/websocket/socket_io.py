"""Socket.IO transport for real-time messaging.

Wraps a `socketio.AsyncServer`. Socket IDs are Socket.IO session IDs and rooms
are Socket.IO rooms named by room code. Each event goes out under its
`event_type` with its Pydantic JSON-mode dump as the payload. No client commands
are handled yet; clients can only connect and listen.

python-socketio ships without type hints, so the untyped calls stay inside this
module (see the mypy override for `socketio.*` in pyproject.toml).
"""

from typing import TYPE_CHECKING

import socketio

from slop.domain.events import GameEvent

if TYPE_CHECKING:
    from slop.ports.realtime import RealtimePort


class SocketIORealtime:
    """RealtimePort implementation on a Socket.IO server."""

    def __init__(self, server: socketio.AsyncServer | None = None) -> None:
        self.server = server or socketio.AsyncServer(async_mode="asgi")

    def asgi_app(self) -> socketio.ASGIApp:
        """An ASGI app that serves this server's Socket.IO endpoint at any path it is mounted on."""
        return socketio.ASGIApp(self.server, socketio_path=None)

    async def broadcast_to_room(self, room_code: str, event: GameEvent) -> None:
        """Emit the event to every socket currently in the room."""
        await self.server.emit(event.event_type, _payload(event), room=room_code)

    async def send_to_player(self, socket_id: str, event: GameEvent) -> None:
        """Emit the event to this socket only."""
        await self.server.emit(event.event_type, _payload(event), to=socket_id)

    async def join_room(self, socket_id: str, room_code: str) -> None:
        """Add the socket to the room. Joining twice has no extra effect."""
        await self.server.enter_room(socket_id, room_code)

    async def leave_room(self, socket_id: str, room_code: str) -> None:
        """Remove the socket from the room. Unknown sockets are ignored."""
        await self.server.leave_room(socket_id, room_code)


def _payload(event: GameEvent) -> dict[str, object]:
    return event.model_dump(mode="json")


if TYPE_CHECKING:
    # mypy fails here if the adapter drifts from the port's signature.
    _port_check: RealtimePort = SocketIORealtime()
