"""ASGI app: the HTTP entry point to the server."""

from fastapi import FastAPI

from slop import __version__
from slop.api.schemas import HealthResponse


async def health() -> HealthResponse:
    """Report that the server is up."""
    return HealthResponse(status="ok", version=__version__)


def create_app() -> FastAPI:
    """Build the ASGI app."""
    app = FastAPI(title="Slop", version=__version__)
    app.add_api_route("/health", health, methods=["GET"], response_model=HealthResponse)
    return app
