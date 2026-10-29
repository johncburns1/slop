"""Run a real ASGI server and real Socket.IO clients for realtime tests.

`serving(app)` starts uvicorn in-process on a free port. `Listener` is a
Socket.IO client that records every game event it receives, parsed back into
domain events so tests can compare them with what was sent.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import socketio
import uvicorn

from slop.adapters.websocket import SocketIORealtime
from slop.domain.events import GameEvent

FLUSH = "test.flush"


def _event_classes() -> dict[str, type[GameEvent]]:
    classes: dict[str, type[GameEvent]] = {}
    pending = list(GameEvent.__subclasses__())
    while pending:
        cls = pending.pop()
        classes[cls.model_fields["event_type"].default] = cls
        pending.extend(cls.__subclasses__())
    return classes


EVENT_CLASSES = _event_classes()


@asynccontextmanager
async def serving(app: Any) -> AsyncIterator[str]:
    """Serve the ASGI app on a free local port and yield its base URL."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            task.result()
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


class Listener:
    """A connected Socket.IO client that records the game events it receives."""

    def __init__(self) -> None:
        self.client = socketio.AsyncClient()
        self.events: list[GameEvent] = []
        self.raw: list[tuple[str, Any]] = []
        self._flushed = asyncio.Event()
        self.client.on("*", self._record)
        self.client.on(FLUSH, self._flushed.set)

    @property
    def sid(self) -> str:
        sid = self.client.get_sid()
        assert isinstance(sid, str)
        return sid

    async def connect(self, url: str) -> None:
        await self.client.connect(url, transports=["websocket"], wait_timeout=5)

    async def received(self, realtime: SocketIORealtime) -> list[GameEvent]:
        """Every game event received so far, in order.

        Sends a marker straight down this client's connection and waits for it,
        so anything emitted before this call has arrived too.
        """
        self._flushed.clear()
        await realtime.server.emit(FLUSH, to=self.sid)
        await asyncio.wait_for(self._flushed.wait(), timeout=5)
        return list(self.events)

    async def _record(self, event_type: str, data: Any) -> None:
        self.raw.append((event_type, data))
        self.events.append(EVENT_CLASSES[event_type].model_validate(data))
