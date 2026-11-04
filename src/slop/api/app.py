"""ASGI app: the HTTP entry point to the server, and where its dependencies are wired."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from slop import __version__
from slop.adapters.clock import SystemClock
from slop.adapters.ids import RandomIds
from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.moderation import StandInModerationAdapter
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import SocketIORealtime
from slop.api.messages import GameMessages
from slop.api.rate_limit import RateLimit, RateLimiter
from slop.api.schemas import HealthResponse
from slop.application.engine import GameDeps
from slop.application.expire_games import expire_games
from slop.application.guess_timers import GuessTimers
from slop.domain.expiry import ExpiryPolicy
from slop.ports.clock import Clock
from slop.ports.llm import LLMPort
from slop.ports.moderation import ModerationPort
from slop.ports.storage import StoragePort

SOCKETIO_PATH = "/socket.io"
# The web client: plain HTML, CSS, and JavaScript modules, served as they are.
STATIC_DIR = Path(__file__).parent / "static"
EXPIRY_TASK = "slop.expire_games"
DEFAULT_EXPIRE_EVERY = timedelta(minutes=1)

logger = logging.getLogger(__name__)


async def health() -> HealthResponse:
    """Report that the server is up."""
    return HealthResponse(status="ok", version=__version__)


def create_app(
    realtime: SocketIORealtime | None = None,
    *,
    storage: StoragePort | None = None,
    llm: LLMPort | None = None,
    clock: Clock | None = None,
    rate_limit: RateLimit | None = None,
    moderation: ModerationPort | None = None,
    expiry: ExpiryPolicy | None = None,
    expire_every: timedelta = DEFAULT_EXPIRE_EVERY,
) -> FastAPI:
    """Build the ASGI app, with the Socket.IO endpoint mounted at `/socket.io`
    and the web client served from ``STATIC_DIR`` at `/`.

    Client messages there play the game (see `slop.api.messages`). Games are
    kept in ``storage`` (in memory if None) and scripts come from ``llm`` (the
    stand-in if None). Each connection may send messages at ``rate_limit``
    (the defaults if None), timed by ``clock`` (the system clock if None).
    Player and AI text is checked by ``moderation`` (the stand-in if None;
    pass a real provider's adapter here to use it).
    While the app runs, games past ``expiry`` (the defaults if None) are
    deleted every ``expire_every``, and guessing closes at each round's deadline.
    """
    realtime = realtime or SocketIORealtime()
    clock = clock or SystemClock()
    deps = GameDeps(
        storage=storage or InMemoryStorage(),
        realtime=realtime,
        clock=clock,
        ids=RandomIds(),
        llm=llm or StandInLLMAdapter(),
        moderation=moderation or StandInModerationAdapter(),
    )
    timers = GuessTimers(deps)
    GameMessages(deps, realtime, RateLimiter(rate_limit or RateLimit(), clock), timers).register()

    app = FastAPI(
        title="Slop",
        version=__version__,
        lifespan=_background_tasks(deps, timers, expiry or ExpiryPolicy(), expire_every),
    )
    app.add_api_route("/health", health, methods=["GET"], response_model=HealthResponse)
    app.mount(SOCKETIO_PATH, realtime.asgi_app())
    # Last, so `/health` and `/socket.io` match before the catch-all static files.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    return app


def _background_tasks(
    deps: GameDeps, timers: GuessTimers, policy: ExpiryPolicy, every: timedelta
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """A lifespan that runs guess timers, and deletes expired games every ``every``.

    On startup it picks up the guess timers of games the last server left. All
    of it stops when the app shuts down.
    """

    async def sweep() -> None:
        while True:
            try:
                await expire_games(deps, policy)
            except Exception:
                logger.exception("Expiring games failed; trying again later")
            await asyncio.sleep(every.total_seconds())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await timers.restore()
        sweeper = asyncio.create_task(sweep(), name=EXPIRY_TASK)
        try:
            yield
        finally:
            await timers.stop()
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper

    return lifespan
