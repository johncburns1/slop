"""API layer for REST and WebSocket endpoints.

This layer exposes the application services to external clients
through HTTP and WebSocket interfaces.
"""

from slop.api.app import create_app

__all__ = ["create_app"]
