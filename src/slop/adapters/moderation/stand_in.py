"""Deterministic stand-in for a real moderation provider.

Blocks text that contains a listed term as whole words, whatever the case or
punctuation. One list applies to every game, and a second, stricter one only
to family games. The default lists are tiny on purpose: they show the
mechanism, not a real policy. Tests pass their own terms. It makes no network
calls, which makes it suitable for local play, tests, and validation.
"""

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from slop.domain.game import ContentTone
from slop.ports.moderation import ALLOWED, ModerationResult

if TYPE_CHECKING:
    from slop.ports.moderation import ModerationPort

# Blocked in every game.
BLOCKED_ALWAYS: tuple[str, ...] = ("kill yourself",)
# Blocked in family games only.
BLOCKED_FOR_FAMILY: tuple[str, ...] = ("damn", "crap", "sexy", "booze")

OFFENSIVE = "offensive"
MATURE = "mature"

_WORD = re.compile(r"[^\W_]+")


class StandInModerationAdapter:
    """Blocks text containing a listed term, more of them in family games."""

    def __init__(
        self,
        blocked_always: Iterable[str] = BLOCKED_ALWAYS,
        blocked_for_family: Iterable[str] = BLOCKED_FOR_FAMILY,
    ) -> None:
        self._always = _phrases(blocked_always)
        self._family = _phrases(blocked_for_family)

    async def check(self, text: str, tone: ContentTone) -> ModerationResult:
        words = _words(text)
        if _contains_any(words, self._always):
            return ModerationResult.blocked(OFFENSIVE)
        if tone == ContentTone.FAMILY and _contains_any(words, self._family):
            return ModerationResult.blocked(MATURE)
        return ALLOWED


def _words(text: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(text.casefold()))


def _phrases(terms: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    return tuple(phrase for phrase in map(_words, terms) if phrase)


def _contains_any(words: tuple[str, ...], phrases: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        words[start : start + len(phrase)] == phrase
        for phrase in phrases
        for start in range(len(words) - len(phrase) + 1)
    )


if TYPE_CHECKING:
    # mypy fails here if the adapter drifts from the port's signature.
    _port_check: ModerationPort = StandInModerationAdapter()
