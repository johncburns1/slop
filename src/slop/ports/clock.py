"""Clock port interface.

Use cases read the time through this port so tests can fix it.
"""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time."""

    def now(self) -> datetime:
        """Return the current time, timezone-aware in UTC."""
        ...
