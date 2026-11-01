"""Tests for the moderation port interface."""

from typing import Protocol

import pytest

from slop.ports import ModerationPort, ModerationResult
from slop.ports.moderation import ALLOWED


def test_moderation_port_is_protocol():
    assert issubclass(ModerationPort, Protocol)
    assert hasattr(ModerationPort, "check")


def test_a_result_is_allowed_or_blocked_with_a_category():
    assert ALLOWED == ModerationResult(allowed=True)
    assert ModerationResult.blocked("mature") == ModerationResult(False, "mature")


@pytest.mark.parametrize(("allowed", "category"), [(True, "mature"), (False, None)])
def test_a_category_is_given_exactly_when_blocked(allowed: bool, category: str | None):
    with pytest.raises(ValueError, match="category"):
        ModerationResult(allowed=allowed, category=category)
