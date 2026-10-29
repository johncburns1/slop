"""ASGI app: the HTTP entry point to the server."""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from slop import __version__


async def health(request: Request) -> JSONResponse:
    """Report that the server is up."""
    return JSONResponse({"status": "ok", "version": __version__})


def create_app() -> Starlette:
    """Build the ASGI app."""
    return Starlette(routes=[Route("/health", health, methods=["GET"])])
