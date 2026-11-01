"""ASGI app: the HTTP entry point to the server, and where its dependencies are wired."""

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
from slop.ports.clock import Clock
from slop.ports.llm import LLMPort
from slop.ports.moderation import ModerationPort
from slop.ports.storage import StoragePort

SOCKETIO_PATH = "/socket.io"


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
) -> FastAPI:
    """Build the ASGI app, with the Socket.IO endpoint mounted at `/socket.io`.

    Client messages there play the game (see `slop.api.messages`). Games are
    kept in ``storage`` (in memory if None) and scripts come from ``llm`` (the
    stand-in if None). Each connection may send messages at ``rate_limit``
    (the defaults if None), timed by ``clock`` (the system clock if None).
    Player and AI text is checked by ``moderation`` (the stand-in if None;
    pass a real provider's adapter here to use it).
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

    app = FastAPI(title="Slop", version=__version__)
    app.add_api_route("/health", health, methods=["GET"], response_model=HealthResponse)
    app.mount(SOCKETIO_PATH, realtime.asgi_app())
    return app
