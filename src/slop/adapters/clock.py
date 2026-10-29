"""Clock adapters: the real system clock and a fixed stand-in for tests."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from slop.ports.clock import Clock


class SystemClock:
    """Clock that reads the system time."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)


class FixedClock:
    """Clock that stays at one time until a test moves it."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware time")
        self._now = at

    def now(self) -> datetime:
        """Return the fixed time."""
        return self._now

    def advance(self, delta: timedelta) -> None:
        """Move the clock forward by ``delta``."""
        self._now += delta


if TYPE_CHECKING:
    # mypy fails here if an adapter drifts from the port's signature.
    _system_check: Clock = SystemClock()
    _fixed_check: Clock = FixedClock(datetime.now(UTC))
