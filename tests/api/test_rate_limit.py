"""Tests for the per-connection token bucket rate limiter."""

from datetime import UTC, datetime, timedelta

import pytest

from slop.adapters.clock import FixedClock
from slop.api.rate_limit import RateLimit, RateLimiter

START = datetime(2026, 1, 1, tzinfo=UTC)


def limiter(per_second: float = 10, burst: int = 20) -> tuple[RateLimiter, FixedClock]:
    clock = FixedClock(START)
    return RateLimiter(RateLimit(per_second=per_second, burst=burst), clock), clock


def test_defaults_are_ten_per_second_with_a_burst_of_twenty() -> None:
    assert RateLimit() == RateLimit(per_second=10, burst=20)


def test_a_connection_may_send_a_full_burst_and_no_more() -> None:
    rate_limiter, _ = limiter(burst=3)

    assert [rate_limiter.allow("a") for _ in range(4)] == [True, True, True, False]


def test_tokens_refill_with_time_up_to_the_burst() -> None:
    rate_limiter, clock = limiter(per_second=2, burst=3)
    for _ in range(3):
        rate_limiter.allow("a")

    clock.advance(timedelta(seconds=0.5))
    assert [rate_limiter.allow("a") for _ in range(2)] == [True, False]

    clock.advance(timedelta(hours=1))
    assert [rate_limiter.allow("a") for _ in range(4)] == [True, True, True, False]


def test_each_connection_has_its_own_bucket() -> None:
    rate_limiter, _ = limiter(burst=1)

    assert rate_limiter.allow("a")
    assert not rate_limiter.allow("a")
    assert rate_limiter.allow("b")


def test_a_forgotten_connection_starts_with_a_full_bucket() -> None:
    rate_limiter, _ = limiter(burst=1)
    rate_limiter.allow("a")

    rate_limiter.forget("a")
    rate_limiter.forget("never-seen")

    assert rate_limiter.allow("a")


@pytest.mark.parametrize(("per_second", "burst"), [(0, 1), (-1, 1), (1, 0)])
def test_limits_must_be_positive(per_second: float, burst: int) -> None:
    with pytest.raises(ValueError):
        RateLimit(per_second=per_second, burst=burst)
