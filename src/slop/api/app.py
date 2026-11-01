"""ASGI app: the HTTP entry point to the server, and where its dependencies are wired."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from datetime import timedelta

from fastapi import FastAPI

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
from slop.domain.expiry import ExpiryPolicy
from slop.ports.clock import Clock
from slop.ports.llm import LLMPort
from slop.ports.moderation import ModerationPort
from slop.ports.storage import StoragePort

SOCKETIO_PATH = "/socket.io"
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
    """Build the ASGI app, with the Socket.IO endpoint mounted at `/socket.io`.

    Client messages there play the game (see `slop.api.messages`). Games are
    kept in ``storage`` (in memory if None) and scripts come from ``llm`` (the
    stand-in if None). Each connection may send messages at ``rate_limit``
    (the defaults if None), timed by ``clock`` (the system clock if None).
    Player and AI text is checked by ``moderation`` (the stand-in if None;
    pass a real provider's adapter here to use it).
    While the app runs, games past ``expiry`` (the defaults if None) are
    deleted every ``expire_every``.
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
    GameMessages(deps, realtime, RateLimiter(rate_limit or RateLimit(), clock)).register()

    app = FastAPI(
        title="Slop",
        version=__version__,
        lifespan=_expiring_games(deps, expiry or ExpiryPolicy(), expire_every),
    )
    app.add_api_route("/health", health, methods=["GET"], response_model=HealthResponse)
    app.mount(SOCKETIO_PATH, realtime.asgi_app())
    return app


def _expiring_games(
    deps: GameDeps, policy: ExpiryPolicy, every: timedelta
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """A lifespan that deletes expired games every ``every`` until the app shuts down."""

    async def sweep() -> None:
        while True:
            try:
                await expire_games(deps, policy)
            except Exception:
                logger.exception("Expiring games failed; trying again later")
            await asyncio.sleep(every.total_seconds())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sweeper = asyncio.create_task(sweep(), name=EXPIRY_TASK)
        try:
            yield
        finally:
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper

    return lifespan
