"""The `slop` command line.

`slop serve` starts the server. Each setting comes from a flag, then an env var,
then a default, so several copies can run side by side with different ports and
data directories.
"""

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from slop.api import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_DATA_DIR = Path(".slop-data")


@dataclass(frozen=True)
class ServeSettings:
    host: str
    port: int
    data_dir: Path


def _env_port(parser: argparse.ArgumentParser) -> int:
    raw = os.environ.get("SLOP_PORT")
    if raw is None:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        parser.error(f"SLOP_PORT must be an integer, got {raw!r}")


def parse_args(argv: Sequence[str] | None = None) -> ServeSettings:
    """Parse the command line into server settings."""
    parser = argparse.ArgumentParser(prog="slop")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the server")
    serve.add_argument("--host", help=f"interface to bind (env SLOP_HOST, default {DEFAULT_HOST})")
    serve.add_argument("--port", type=int, help=f"port (env SLOP_PORT, default {DEFAULT_PORT})")
    serve.add_argument(
        "--data-dir",
        type=Path,
        help=f"where game data is stored (env SLOP_DATA_DIR, default {DEFAULT_DATA_DIR})",
    )
    args = parser.parse_args(argv)

    env_data_dir = os.environ.get("SLOP_DATA_DIR")
    return ServeSettings(
        host=args.host or os.environ.get("SLOP_HOST", DEFAULT_HOST),
        port=args.port if args.port is not None else _env_port(serve),
        data_dir=args.data_dir or (Path(env_data_dir) if env_data_dir else DEFAULT_DATA_DIR),
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the `slop` command."""
    settings = parse_args(argv)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(), host=settings.host, port=settings.port)
