"""When a game expires: after a period with no events, or sooner once it has finished.

History is session-only, so an expired game is deleted and its room code
stops resolving (see ``slop.application.expire_games``).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from slop.domain.game import Game, GameStatus

DEFAULT_IDLE = timedelta(hours=2)
DEFAULT_AFTER_FINISH = timedelta(minutes=30)


@dataclass(frozen=True)
class ExpiryPolicy:
    """How long a game lives after its last event: ``idle``, or ``after_finish`` once finished.

    Playing again restarts the game, so it goes back to the ``idle`` period.
    """

    idle: timedelta = DEFAULT_IDLE
    after_finish: timedelta = DEFAULT_AFTER_FINISH

    def __post_init__(self) -> None:
        if self.idle <= timedelta(0) or self.after_finish <= timedelta(0):
            raise ValueError("Expiry periods must be positive")


def is_expired(game: Game, now: datetime, policy: ExpiryPolicy) -> bool:
    """Return whether the game has expired at ``now``."""
    lifetime = policy.after_finish if game.status == GameStatus.FINISHED else policy.idle
    return now - game.last_event_at >= lifetime
