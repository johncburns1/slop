"""Tests for the `slop` command line."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import socketio

from slop.adapters.storage import SQLiteStorage
from slop.cli import (
    DATABASE_FILE,
    DEFAULT_DATA_DIR,
    DEFAULT_HOST,
    DEFAULT_LLM,
    DEFAULT_PORT,
    ServeSettings,
    parse_args,
)


def test_serve_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SLOP_HOST", "SLOP_PORT", "SLOP_DATA_DIR", "SLOP_LLM"):
        monkeypatch.delenv(name, raising=False)

    assert parse_args(["serve"]) == ServeSettings(
        host=DEFAULT_HOST, port=DEFAULT_PORT, data_dir=DEFAULT_DATA_DIR
    )


def test_serve_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOP_HOST", "0.0.0.0")
    monkeypatch.setenv("SLOP_PORT", "9001")
    monkeypatch.setenv("SLOP_DATA_DIR", "/tmp/slop-a")

    assert parse_args(["serve"]) == ServeSettings(
        host="0.0.0.0", port=9001, data_dir=Path("/tmp/slop-a")
    )


def test_serve_flags_override_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOP_HOST", "0.0.0.0")
    monkeypatch.setenv("SLOP_PORT", "9001")
    monkeypatch.setenv("SLOP_DATA_DIR", "/tmp/slop-a")

    settings = parse_args(
        ["serve", "--host", "127.0.0.2", "--port", "9002", "--data-dir", "/tmp/slop-b"]
    )

    assert settings == ServeSettings(host="127.0.0.2", port=9002, data_dir=Path("/tmp/slop-b"))


def test_serve_rejects_non_integer_port_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOP_PORT", "not-a-port")

    with pytest.raises(SystemExit):
        parse_args(["serve"])


def test_serve_uses_the_stand_in_llm_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLOP_LLM", raising=False)

    assert parse_args(["serve"]).llm == DEFAULT_LLM == "stand-in"


def test_serve_reads_llm_from_flag_or_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOP_LLM", "stand-in")

    assert parse_args(["serve"]).llm == "stand-in"
    assert parse_args(["serve", "--llm", "stand-in"]).llm == "stand-in"


def test_serve_rejects_unknown_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLOP_LLM", "no-such-llm")

    with pytest.raises(SystemExit):
        parse_args(["serve"])
    monkeypatch.delenv("SLOP_LLM")
    with pytest.raises(SystemExit):
        parse_args(["serve", "--llm", "no-such-llm"])


def free_ports(count: int) -> list[int]:
    """Ask the OS for distinct free ports, holding each open until all are picked."""
    sockets = [socket.socket() for _ in range(count)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def get_health(port: int) -> tuple[int, dict[str, Any]]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
        return response.status, json.loads(response.read())


@contextmanager
def running_server(port: int, data_dir: Path) -> Iterator[subprocess.Popen[bytes]]:
    """Run `slop serve` in a subprocess until it reports healthy, then stop it."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SLOP_")}
    process = subprocess.Popen(
        [sys.executable, "-m", "slop", "serve", "--port", str(port), "--data-dir", str(data_dir)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                output = process.stdout.read().decode() if process.stdout else ""
                pytest.fail(f"server on port {port} exited early:\n{output}")
            try:
                get_health(port)
                break
            except (urllib.error.URLError, ConnectionError):
                if time.monotonic() > deadline:
                    pytest.fail(f"server on port {port} never became healthy")
                time.sleep(0.1)
        yield process
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_two_servers_run_side_by_side(tmp_path: Path) -> None:
    port_a, port_b = free_ports(2)
    data_a, data_b = tmp_path / "a", tmp_path / "b"

    with running_server(port_a, data_a), running_server(port_b, data_b):
        assert get_health(port_a)[0] == 200
        assert get_health(port_b)[0] == 200
        assert data_a.is_dir()
        assert data_b.is_dir()


async def test_served_games_are_played_over_socketio_and_stored_in_the_data_dir(
    tmp_path: Path,
) -> None:
    (port,) = free_ports(1)
    client = socketio.AsyncClient()

    with running_server(port, tmp_path):
        await client.connect(f"http://127.0.0.1:{port}", transports=["websocket"], wait_timeout=5)
        try:
            created = await client.call("create_game", {"content_tone": "family"}, timeout=5)
            joined = await client.call(
                "join_game", {"room_code": created["room_code"], "player_name": "Alice"}, timeout=5
            )
        finally:
            await client.disconnect()

    game = await SQLiteStorage(tmp_path / DATABASE_FILE).get_snapshot(created["game_id"])
    assert game is not None
    assert game.room_code == created["room_code"]
    assert [(p.id, p.name) for p in game.players] == [(joined["player_id"], "Alice")]
