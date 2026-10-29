"""ASGI app: the HTTP entry point to the server."""

from fastapi import FastAPI

from slop import __version__
from slop.adapters.websocket import SocketIORealtime
from slop.api.schemas import HealthResponse

SOCKETIO_PATH = "/socket.io"


async def health() -> HealthResponse:
    """Report that the server is up."""
    return HealthResponse(status="ok", version=__version__)


def create_app(realtime: SocketIORealtime | None = None) -> FastAPI:
    """Build the ASGI app, with the Socket.IO endpoint mounted at `/socket.io`."""
    app = FastAPI(title="Slop", version=__version__)
    app.add_api_route("/health", health, methods=["GET"], response_model=HealthResponse)
    app.mount(SOCKETIO_PATH, (realtime or SocketIORealtime()).asgi_app())
    return app
