"""Typed request and response models for the HTTP API.

These are the API's wire format. They stay in the API layer and are never
passed into the domain.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Body of `GET /health`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    version: str
