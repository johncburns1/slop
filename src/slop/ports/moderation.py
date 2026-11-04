"""Moderation port interface.

This port defines the contract for content moderation: checking text before
anyone sees it. Player text (names, prompts, guesses) is checked before it is
accepted, and AI text (scripts, awards) before it is shown. What is allowed
depends on the game's content setting.
"""

from dataclasses import dataclass
from typing import Protocol

from slop.domain.game import ContentTone


@dataclass(frozen=True)
class ModerationResult:
    """Whether text may be shown, and if not, a short reason category such as ``"mature"``.

    ``category`` is None exactly when the text is allowed.
    """

    allowed: bool
    category: str | None = None

    def __post_init__(self) -> None:
        if self.allowed != (self.category is None):
            raise ValueError("Blocked text needs a category, and allowed text has none")

    @classmethod
    def blocked(cls, category: str) -> "ModerationResult":
        return cls(allowed=False, category=category)


ALLOWED = ModerationResult(allowed=True)


class ModerationPort(Protocol):
    """Interface for content moderation providers."""

    async def check(self, text: str, tone: ContentTone) -> ModerationResult:
        """Return whether ``text`` may be shown in a game with this content setting.

        ``ContentTone.FAMILY`` is at least as strict as ``ContentTone.ADULT``:
        anything blocked for adults is blocked for families too. A provider
        that can't decide must block in family games, and may allow in adult
        ones so that an outage doesn't stop them being played.
        """
        ...
