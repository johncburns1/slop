"""ASGI app: the HTTP entry point to the server."""

from fastapi import FastAPI

from slop import __version__


async def health() -> dict[str, str]:
    """Report that the server is up."""
    return {"status": "ok", "version": __version__}


def create_app() -> FastAPI:
    """Build the ASGI app."""
    app = FastAPI(title="Slop", version=__version__)
    app.add_api_route("/health", health, methods=["GET"])
    return app
