"""``GameClient`` over Socket.IO, against a real server.

``SocketIOServer.running()`` serves the app on a free local port, the way the
other real-server tests do (see ``tests.socketio_clients``). Each
``SocketIOClient`` is its own Socket.IO connection and speaks only the message
contract in ``slop.api.messages``; its inbox is every game event that
connection received, parsed back into domain events.

The one thing outside the contract is ``caught_up``: the test asks the server
to send a marker down the connection and waits for it, so every event sent
before it has arrived. The bots then decide on everything the server has said,
with no sleeps.
"""

import asyncio
import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import socketio

from slop.adapters.websocket import SocketIORealtime
from slop.api import create_app
from slop.api.schemas import ErrorMessage, PlayerViewReply
from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.domain.events import GameEvent
from slop.domain.game import ContentTone
from tests.socketio_clients import EVENT_CLASSES, serving

TIMEOUT = 5  # seconds to wait for any one ack, connection, or marker
CAUGHT_UP = "test.caught_up"
ERROR = "error"


class SocketIOServer:
    """The app served on a free port, and the clients connected to it."""

    transport = "Socket.IO (real server)"

    def __init__(self, url: str, realtime: SocketIORealtime) -> None:
        self.url = url
        self.realtime = realtime
        self._clients: list[SocketIOClient] = []

    @classmethod
    @asynccontextmanager
    async def running(cls) -> AsyncIterator["SocketIOServer"]:
        """Serve a fresh app until the block ends, then disconnect every client."""
        realtime = SocketIORealtime()
        async with serving(create_app(realtime)) as url:
            server = cls(url, realtime)
            try:
                yield server
            finally:
                for client in server._clients:
                    await client.disconnect()

    async def create_game(
        self, *, rounds_per_team: int = 1, content_tone: ContentTone = ContentTone.FAMILY
    ) -> str:
        """Create a game from a connection of its own, and return its room code."""
        client = await self._open()
        try:
            created = await client.call(
                "create_game",
                {"content_tone": content_tone.value, "rounds_per_team": rounds_per_team},
            )
        finally:
            await client.disconnect()
        return str(created["room_code"])

    async def connect_player(self, seat: int) -> "SocketIOClient":
        client = await self._open()
        self._clients.append(client)
        return client

    async def _open(self) -> "SocketIOClient":
        client = SocketIOClient(self)
        await client.connect()
        return client


class SocketIOClient:
    """``GameClient`` with its own Socket.IO connection to the server."""

    def __init__(self, server: SocketIOServer) -> None:
        self._server = server
        self._events: list[GameEvent] = []
        self.errors: list[dict[str, Any]] = []
        self._socket_id: str | None = None
        self._markers = itertools.count()
        self._marker_seen = -1
        self._marker_arrived = asyncio.Condition()
        self._sio = self._new_connection()

    @property
    def socket_id(self) -> str:
        if self._socket_id is None:
            raise RuntimeError("Never connected")
        return self._socket_id

    @property
    def connected(self) -> bool:
        return bool(self._sio.connected)

    async def connect(self) -> None:
        await self._sio.connect(self._server.url, transports=["websocket"], wait_timeout=TIMEOUT)
        sid = self._sio.get_sid()
        assert isinstance(sid, str)
        self._socket_id = sid

    async def disconnect(self) -> None:
        """Close the connection. The server keeps the player in the game."""
        await self._sio.disconnect()

    async def rejoin_game(self, room_code: str, player_id: str) -> PlayerViewReply:
        """Open a new connection and ``rejoin_game`` on it.

        The inbox carries on from the old connection; whatever was sent while
        disconnected is never received.
        """
        if self.connected:
            await self.disconnect()
        self._sio = self._new_connection()
        await self.connect()
        view = await self.call("rejoin_game", {"room_code": room_code, "player_id": player_id})
        return PlayerViewReply.model_validate(view)

    async def join_game(self, room_code: str, player_name: str) -> str:
        joined = await self.call("join_game", {"room_code": room_code, "player_name": player_name})
        return str(joined["player_id"])

    async def create_team(self, team_name: str, color: str) -> None:
        await self.call("create_team", {"team_name": team_name, "color": color})

    async def join_team(self, team_id: str) -> None:
        await self.call("join_team", {"team_id": team_id})

    async def start_personality_selection(self) -> None:
        await self.call("start_personality_selection")

    async def assign_personality(self, personality_id: str) -> None:
        await self.call("assign_personality", {"personality_id": personality_id})

    async def submit_prompt(self, prompt: str) -> None:
        await self.call("submit_prompt", {"prompt": prompt})

    async def submit_guess(self, guess: str) -> None:
        await self.call("submit_guess", {"guess": guess})

    async def pick_winning_guess(self, guess_index: int | None) -> None:
        await self.call("pick_winning_guess", {"guess_index": guess_index})

    async def guess_personality(self, personality_id: str) -> None:
        await self.call("guess_personality", {"personality_id": personality_id})

    def inbox(self) -> list[GameEvent]:
        return list(self._events)

    async def caught_up(self) -> None:
        """Wait until every event the server sent this connection so far has arrived."""
        marker = next(self._markers)
        await self._server.realtime.server.emit(CAUGHT_UP, marker, to=self.socket_id)
        async with self._marker_arrived:
            await asyncio.wait_for(
                self._marker_arrived.wait_for(lambda: self._marker_seen >= marker), TIMEOUT
            )

    async def call(self, message: str, payload: dict[str, Any] | None = None) -> Any:
        """Send a message and return its ack.

        Raises:
            RuntimeError: If not connected
            GameNotFoundError: If the server answered ``game_not_found``
            GameRuleError: If the server rejected the message any other way
        """
        if not self.connected:
            raise RuntimeError("Not connected")
        ack = await self._sio.call(message, payload or {}, timeout=TIMEOUT)
        if isinstance(ack, dict) and ack.keys() == {"code", "message", "request"}:
            error = ErrorMessage.model_validate(ack)
            if error.code == "game_not_found":
                raise GameNotFoundError(error.message)
            raise GameRuleError(f"{error.code}: {error.message}")
        return ack

    def _new_connection(self) -> socketio.AsyncClient:
        sio = socketio.AsyncClient(reconnection=False)
        sio.on("*", self._receive)
        sio.on(CAUGHT_UP, self._caught_up_to)
        return sio

    def _receive(self, name: str, data: Any) -> None:
        # Not a coroutine, so events are recorded in the order they arrive.
        if name == ERROR:
            self.errors.append(data)
        else:
            self._events.append(EVENT_CLASSES[name].model_validate(data))

    async def _caught_up_to(self, marker: int) -> None:
        async with self._marker_arrived:
            self._marker_seen = max(self._marker_seen, marker)
            self._marker_arrived.notify_all()
