"""Tests for the HTTP request and response models."""

import pytest
from pydantic import ValidationError

from slop.api.schemas import HealthResponse


def test_health_response_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({"status": "broken", "version": "0.1.0"})


def test_health_response_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({"status": "ok", "version": "0.1.0", "extra": 1})
