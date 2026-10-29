"""Tests for the clock adapters."""

from datetime import UTC, datetime, timedelta

import pytest

from slop.adapters.clock import FixedClock, SystemClock


def test_system_clock_returns_the_current_utc_time():
    before = datetime.now(UTC)
    now = SystemClock().now()

    assert before <= now <= datetime.now(UTC)
    assert now.tzinfo is UTC


def test_fixed_clock_stays_put_until_advanced():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = FixedClock(start)

    assert clock.now() == clock.now() == start
    clock.advance(timedelta(minutes=5))
    assert clock.now() == start + timedelta(minutes=5)


def test_fixed_clock_needs_a_timezone():
    with pytest.raises(ValueError, match="timezone"):
        FixedClock(datetime(2026, 1, 1))
