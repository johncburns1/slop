"""Tests for the HTTP app."""

import asyncio
import json
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from slop import __version__
from slop.adapters.clock import FixedClock
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import SocketIORealtime
from slop.api import create_app
from slop.api.schemas import HealthResponse
from slop.domain import Game
from tests.adapters.websocket.contract import make_game_created, make_script_generated
from tests.socketio_clients import Listener, serving

T0 = datetime(2026, 1, 1, tzinfo=UTC)


async def get(path: str) -> tuple[int, dict[str, Any]]:
    """Send one GET request straight to the ASGI app and return status and JSON body."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await create_app()(scope, receive, send)

    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(body)


async def test_health_returns_ok_with_version() -> None:
    status, body = await get("/health")

    assert status == 200
    assert body == {"status": "ok", "version": __version__}


def test_health_declares_typed_response_model() -> None:
    schema = create_app().openapi()

    response = schema["paths"]["/health"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }
    assert HealthResponse.model_validate({"status": "ok", "version": "1"}).status == "ok"


def fetch_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


async def test_served_app_delivers_realtime_events_over_socketio() -> None:
    """Two real clients join one room on a running server: both get the
    broadcast, and only the target gets the direct send. /health still works."""
    realtime = SocketIORealtime()
    async with serving(create_app(realtime)) as url:
        alice, bob = Listener(), Listener()
        await alice.connect(url)
        await bob.connect(url)
        try:
            await realtime.join_room(alice.sid, "ABCD")
            await realtime.join_room(bob.sid, "ABCD")
            game_created, script = make_game_created(), make_script_generated()

            await realtime.broadcast_to_room("ABCD", game_created)
            await realtime.send_to_player(alice.sid, script)

            assert await alice.received(realtime) == [game_created, script]
            assert await bob.received(realtime) == [game_created]
            health = await asyncio.to_thread(fetch_json, f"{url}/health")
            assert health == {"status": "ok", "version": __version__}
        finally:
            await alice.client.disconnect()
            await bob.client.disconnect()


class FlakyStorage(InMemoryStorage):
    """Fails the first time it is asked to list games."""

    def __init__(self) -> None:
        super().__init__()
        self.listed = 0

    async def list_games(self) -> list[Game]:
        self.listed += 1
        if self.listed == 1:
            raise OSError("disk hiccup")
        return await super().list_games()


async def test_expiry_keeps_sweeping_after_a_failure(caplog: pytest.LogCaptureFixture) -> None:
    storage = FlakyStorage()
    await storage.save_snapshot(Game(id="game-1", room_code="ABCD", last_event_at=T0))
    clock = FixedClock(T0 + timedelta(hours=2))
    app = create_app(storage=storage, clock=clock, expire_every=timedelta(milliseconds=1))

    async with app.router.lifespan_context(app):
        for _ in range(500):
            if await storage.get_snapshot("game-1") is None:
                break
            await asyncio.sleep(0.01)

    assert await storage.get_snapshot("game-1") is None
    assert "Expiring games failed" in caplog.text


def fetch(url: str) -> tuple[int, str, str]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.headers["content-type"], response.read().decode()


async def test_served_app_hosts_the_web_client_alongside_health_and_socketio() -> None:
    """The web client is served at `/`, its scripts as JavaScript modules, and
    /health and Socket.IO messages still work on the same server."""
    async with serving(create_app()) as url:
        status, content_type, page = await asyncio.to_thread(fetch, f"{url}/")
        assert status == 200
        assert content_type.startswith("text/html")
        assert '<script type="module" src="/app.js">' in page

        for script in ("/app.js", "/game.js", "/screens/lobby.js", "/vendor/socket.io.esm.min.js"):
            status, content_type, _ = await asyncio.to_thread(fetch, f"{url}{script}")
            assert status == 200
            assert content_type.startswith("text/javascript"), script

        health = await asyncio.to_thread(fetch_json, f"{url}/health")
        assert health == {"status": "ok", "version": __version__}

        player = Listener()
        await player.connect(url)
        try:
            created = await player.client.call("create_game", {"content_tone": "family"}, timeout=5)
            assert set(created) == {"game_id", "room_code"}
        finally:
            await player.client.disconnect()
