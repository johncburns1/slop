"""Reusable contract tests for ModerationPort adapters.

Any moderation adapter, including real network-backed ones, plugs in by
subclassing ModerationPortContract and overriding the fixtures: ``adapter``,
and sample texts the adapter blocks in every game and only in family games:

    class TestMyAdapter(ModerationPortContract):
        @pytest.fixture
        def adapter(self) -> ModerationPort:
            return MyAdapter(...)

Every test here asserts only what the port promises.
"""

import pytest

from slop.domain import ContentTone
from slop.ports import ModerationPort, ModerationResult

ORDINARY = (
    "Cat steals the moon",
    "Grandma enters intergalactic baking contest",
    "Alice",
    "Detective Mallory: This city chews people up.",
)


class ModerationPortContract:
    """Behavior every ModerationPort implementation must satisfy."""

    @pytest.fixture
    def adapter(self) -> ModerationPort:
        """Return the adapter under test. Subclasses must override this."""
        raise NotImplementedError("Override the adapter fixture in your subclass")

    @pytest.fixture
    def blocked_always(self) -> str:
        """Text the adapter blocks whatever the content setting."""
        raise NotImplementedError("Override the blocked_always fixture in your subclass")

    @pytest.fixture
    def blocked_for_family(self) -> str:
        """Text the adapter blocks in family games but allows in adult ones."""
        raise NotImplementedError("Override the blocked_for_family fixture in your subclass")

    @pytest.mark.parametrize("tone", list(ContentTone))
    @pytest.mark.parametrize("text", ORDINARY)
    async def test_ordinary_text_is_allowed(
        self, adapter: ModerationPort, text: str, tone: ContentTone
    ) -> None:
        result = await adapter.check(text, tone)

        assert result == ModerationResult(allowed=True)

    @pytest.mark.parametrize("tone", list(ContentTone))
    async def test_offensive_text_is_blocked_with_a_category(
        self, adapter: ModerationPort, blocked_always: str, tone: ContentTone
    ) -> None:
        result = await adapter.check(blocked_always, tone)

        assert not result.allowed
        assert result.category

    async def test_family_games_are_stricter_than_adult_ones(
        self, adapter: ModerationPort, blocked_for_family: str
    ) -> None:
        family = await adapter.check(blocked_for_family, ContentTone.FAMILY)
        adult = await adapter.check(blocked_for_family, ContentTone.ADULT)

        assert not family.allowed
        assert family.category
        assert adult.allowed

    @pytest.mark.parametrize("tone", list(ContentTone))
    async def test_blocked_text_stays_blocked_inside_longer_text(
        self, adapter: ModerationPort, blocked_always: str, tone: ContentTone
    ) -> None:
        result = await adapter.check(f"Narrator: well. {blocked_always}! The end.", tone)

        assert not result.allowed
