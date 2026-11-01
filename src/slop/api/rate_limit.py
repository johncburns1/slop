"""Per-connection rate limiting for client messages: one token bucket per socket.

Each message costs a token. A connection starts with ``burst`` tokens and earns
``per_second`` more each second, up to ``burst``. Time comes from a ``Clock``
so tests can drive it.
"""

from dataclasses import dataclass, field
from datetime import datetime

from slop.ports.clock import Clock

DEFAULT_PER_SECOND = 10.0
DEFAULT_BURST = 20


@dataclass(frozen=True)
class RateLimit:
    """How many messages a connection may send: ``per_second``, in bursts of ``burst``."""

    per_second: float = DEFAULT_PER_SECOND
    burst: int = DEFAULT_BURST

    def __post_init__(self) -> None:
        if not self.per_second > 0 or self.burst < 1:  # also rejects NaN
            raise ValueError("A rate limit needs a positive rate and a burst of at least 1")


@dataclass
class _Bucket:
    tokens: float
    updated: datetime


@dataclass
class RateLimiter:
    """Decides whether each connection's next message may go through."""

    limit: RateLimit
    clock: Clock
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    def allow(self, socket_id: str) -> bool:
        """Spend one of the connection's tokens, or return False if it has none."""
        now = self.clock.now()
        bucket = self._buckets.setdefault(socket_id, _Bucket(float(self.limit.burst), now))
        earned = (now - bucket.updated).total_seconds() * self.limit.per_second
        bucket.tokens = min(float(self.limit.burst), bucket.tokens + max(earned, 0.0))
        bucket.updated = now
        if bucket.tokens < 1:
            return False
        bucket.tokens -= 1
        return True

    def forget(self, socket_id: str) -> None:
        """Drop the connection's bucket, once it has disconnected."""
        self._buckets.pop(socket_id, None)
