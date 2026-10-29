"""Tests for the HTTP app."""

import json
from typing import Any

from slop import __version__
from slop.api import create_app


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
