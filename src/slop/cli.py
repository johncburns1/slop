"""The `slop` command line.

`slop serve` starts the server. Each setting comes from a flag, then an env var,
then a default, so several copies can run side by side with different ports and
data directories. Games are stored in a SQLite file in the data directory, and
scripts come from the LLM adapter named by `--llm` (only the stand-in so far).
"""

import argparse
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.storage import SQLiteStorage
from slop.api import create_app
from slop.ports.llm import LLMPort

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_DATA_DIR = Path(".slop-data")
DATABASE_FILE = "slop.sqlite3"
# Add a real provider here to make it selectable with --llm / SLOP_LLM.
LLM_ADAPTERS: dict[str, Callable[[], LLMPort]] = {"stand-in": StandInLLMAdapter}
DEFAULT_LLM = "stand-in"


@dataclass(frozen=True)
class ServeSettings:
    host: str
    port: int
    data_dir: Path
    llm: str = DEFAULT_LLM


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
    serve.add_argument(
        "--llm",
        choices=sorted(LLM_ADAPTERS),
        help=f"which LLM writes scripts (env SLOP_LLM, default {DEFAULT_LLM})",
    )
    args = parser.parse_args(argv)
    llm = args.llm or os.environ.get("SLOP_LLM", DEFAULT_LLM)
    if llm not in LLM_ADAPTERS:
        serve.error(f"SLOP_LLM must be one of {', '.join(sorted(LLM_ADAPTERS))}, got {llm!r}")

    env_data_dir = os.environ.get("SLOP_DATA_DIR")
    return ServeSettings(
        host=args.host or os.environ.get("SLOP_HOST", DEFAULT_HOST),
        port=args.port if args.port is not None else _env_port(serve),
        data_dir=args.data_dir or (Path(env_data_dir) if env_data_dir else DEFAULT_DATA_DIR),
        llm=llm,
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the `slop` command."""
    settings = parse_args(argv)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(
        storage=SQLiteStorage(settings.data_dir / DATABASE_FILE),
        llm=LLM_ADAPTERS[settings.llm](),
    )
    uvicorn.run(app, host=settings.host, port=settings.port)
