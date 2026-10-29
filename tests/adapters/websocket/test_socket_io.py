"""Tests for the Socket.IO realtime adapter, run against a real server and clients."""

from collections.abc import AsyncIterator

import pytest

from slop.adapters.websocket import SocketIORealtime
from slop.domain.events import GameEvent
from slop.ports import RealtimePort
from tests.adapters.websocket.contract import (
    RealtimePortContract,
    Received,
    make_script_generated,
)
from tests.socketio_clients import Listener, serving


class NamedSockets:
    """Lets the contract's made-up socket names stand for real connections.

    The contract talks about "socket-1", "socket-2", and so on, but Socket.IO
    assigns its own session IDs. The first time a name comes up, this connects
    a real client and from then on passes its session ID to the adapter.
    """

    def __init__(self, adapter: SocketIORealtime, url: str) -> None:
        self.adapter = adapter
        self.url = url
        self.listeners: dict[str, Listener] = {}

    async def listener(self, name: str) -> Listener:
        if name not in self.listeners:
            listener = Listener()
            await listener.connect(self.url)
            self.listeners[name] = listener
        return self.listeners[name]

    async def sid(self, name: str) -> str:
        return (await self.listener(name)).sid

    async def broadcast_to_room(self, room_code: str, event: GameEvent) -> None:
        await self.adapter.broadcast_to_room(room_code, event)

    async def send_to_player(self, socket_id: str, event: GameEvent) -> None:
        await self.adapter.send_to_player(await self.sid(socket_id), event)

    async def join_room(self, socket_id: str, room_code: str) -> None:
        await self.adapter.join_room(await self.sid(socket_id), room_code)

    async def leave_room(self, socket_id: str, room_code: str) -> None:
        await self.adapter.leave_room(await self.sid(socket_id), room_code)

    async def received(self, name: str) -> list[GameEvent]:
        return await (await self.listener(name)).received(self.adapter)

    async def close(self) -> None:
        for listener in self.listeners.values():
            await listener.client.disconnect()


@pytest.fixture
async def sockets() -> AsyncIterator[NamedSockets]:
    adapter = SocketIORealtime()
    async with serving(adapter.asgi_app()) as url:
        sockets = NamedSockets(adapter, url)
        try:
            yield sockets
        finally:
            await sockets.close()


class TestSocketIORealtime(RealtimePortContract):
    """Run the RealtimePort contract against SocketIORealtime over real connections."""

    @pytest.fixture
    def realtime(self, sockets: NamedSockets) -> RealtimePort:
        return sockets

    @pytest.fixture
    def received(self, sockets: NamedSockets) -> Received:
        return sockets.received


async def test_events_go_out_under_their_type_as_json(sockets: NamedSockets) -> None:
    script = make_script_generated()

    await sockets.send_to_player("socket-1", script)
    await sockets.received("socket-1")

    assert sockets.listeners["socket-1"].raw == [
        ("ScriptGenerated", script.model_dump(mode="json"))
    ]
