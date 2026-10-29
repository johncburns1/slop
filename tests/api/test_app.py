"""Tests for the HTTP app."""

import asyncio
import json
import urllib.request
from typing import Any

from slop import __version__
from slop.adapters.websocket import SocketIORealtime
from slop.api import create_app
from slop.api.schemas import HealthResponse
from tests.adapters.websocket.contract import make_game_created, make_script_generated
from tests.socketio_clients import Listener, serving


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
