"""The `slop` command line.

`slop serve` starts the server. Each setting comes from a flag, then an env var,
then a default, so several copies can run side by side with different ports and
data directories. Games are stored in a SQLite file in the data directory,
scripts come from the LLM adapter named by `--llm` (only the stand-in so far),
`--rate-limit`/`--rate-burst` cap how fast each connection may send messages, and
`--expire-idle-minutes`/`--expire-finished-minutes` set when games are deleted.
"""

import argparse
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import uvicorn

from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.storage import SQLiteStorage
from slop.api import create_app
from slop.api.rate_limit import DEFAULT_BURST, DEFAULT_PER_SECOND, RateLimit
from slop.domain.expiry import DEFAULT_AFTER_FINISH, DEFAULT_IDLE, ExpiryPolicy
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
    rate_limit: RateLimit = field(default_factory=RateLimit)
    expiry: ExpiryPolicy = field(default_factory=ExpiryPolicy)


def _env_number[N: (int, float)](
    parser: argparse.ArgumentParser, name: str, kind: type[N], default: N
) -> N:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return kind(raw)
    except ValueError:
        parser.error(f"{name} must be a{'n integer' if kind is int else ' number'}, got {raw!r}")


def _minutes(period: timedelta) -> float:
    return period.total_seconds() / 60


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
    serve.add_argument(
        "--rate-limit",
        type=float,
        help="messages per second each connection may send "
        f"(env SLOP_RATE_LIMIT, default {DEFAULT_PER_SECOND:g})",
    )
    serve.add_argument(
        "--rate-burst",
        type=int,
        help="messages a connection may send at once "
        f"(env SLOP_RATE_BURST, default {DEFAULT_BURST})",
    )
    serve.add_argument(
        "--expire-idle-minutes",
        type=float,
        help="delete a game this long after its last event (env SLOP_EXPIRE_IDLE_MINUTES, "
        f"default {_minutes(DEFAULT_IDLE):g})",
    )
    serve.add_argument(
        "--expire-finished-minutes",
        type=float,
        help="delete a finished game this long after it ends (env SLOP_EXPIRE_FINISHED_MINUTES, "
        f"default {_minutes(DEFAULT_AFTER_FINISH):g})",
    )
    args = parser.parse_args(argv)
    llm = args.llm or os.environ.get("SLOP_LLM", DEFAULT_LLM)
    if llm not in LLM_ADAPTERS:
        serve.error(f"SLOP_LLM must be one of {', '.join(sorted(LLM_ADAPTERS))}, got {llm!r}")

    try:
        rate_limit = RateLimit(
            per_second=args.rate_limit
            if args.rate_limit is not None
            else _env_number(serve, "SLOP_RATE_LIMIT", float, DEFAULT_PER_SECOND),
            burst=args.rate_burst
            if args.rate_burst is not None
            else _env_number(serve, "SLOP_RATE_BURST", int, DEFAULT_BURST),
        )
        idle = args.expire_idle_minutes
        finished = args.expire_finished_minutes
        expiry = ExpiryPolicy(
            idle=timedelta(
                minutes=idle
                if idle is not None
                else _env_number(serve, "SLOP_EXPIRE_IDLE_MINUTES", float, _minutes(DEFAULT_IDLE))
            ),
            after_finish=timedelta(
                minutes=finished
                if finished is not None
                else _env_number(
                    serve, "SLOP_EXPIRE_FINISHED_MINUTES", float, _minutes(DEFAULT_AFTER_FINISH)
                )
            ),
        )
    except (ValueError, OverflowError) as error:
        serve.error(str(error))

    env_data_dir = os.environ.get("SLOP_DATA_DIR")
    return ServeSettings(
        host=args.host or os.environ.get("SLOP_HOST", DEFAULT_HOST),
        port=args.port
        if args.port is not None
        else _env_number(serve, "SLOP_PORT", int, DEFAULT_PORT),
        data_dir=args.data_dir or (Path(env_data_dir) if env_data_dir else DEFAULT_DATA_DIR),
        llm=llm,
        rate_limit=rate_limit,
        expiry=expiry,
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the `slop` command."""
    settings = parse_args(argv)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(
        storage=SQLiteStorage(settings.data_dir / DATABASE_FILE),
        llm=LLM_ADAPTERS[settings.llm](),
        rate_limit=settings.rate_limit,
        expiry=settings.expiry,
    )
    uvicorn.run(app, host=settings.host, port=settings.port)
