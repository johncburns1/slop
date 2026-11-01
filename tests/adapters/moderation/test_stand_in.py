"""Tests for the deterministic stand-in moderation adapter."""

import pytest

from slop.adapters.moderation import StandInModerationAdapter
from slop.adapters.moderation.stand_in import (
    BLOCKED_ALWAYS,
    BLOCKED_FOR_FAMILY,
    MATURE,
    OFFENSIVE,
)
from slop.domain import ContentTone
from slop.ports import ModerationPort, ModerationResult
from tests.adapters.moderation.contract import ModerationPortContract

FAMILY, ADULT = ContentTone.FAMILY, ContentTone.ADULT


class TestStandInModerationAdapterContract(ModerationPortContract):
    """The stand-in, with its default lists, must pass the shared moderation contract."""

    @pytest.fixture
    def adapter(self) -> ModerationPort:
        return StandInModerationAdapter()

    @pytest.fixture
    def blocked_always(self) -> str:
        return BLOCKED_ALWAYS[0]

    @pytest.fixture
    def blocked_for_family(self) -> str:
        return BLOCKED_FOR_FAMILY[0]


async def test_each_list_gives_its_own_category() -> None:
    moderation = StandInModerationAdapter(blocked_always=["gloop"], blocked_for_family=["fizz"])

    assert await moderation.check("gloop", ADULT) == ModerationResult.blocked(OFFENSIVE)
    assert await moderation.check("gloop", FAMILY) == ModerationResult.blocked(OFFENSIVE)
    assert await moderation.check("fizz", FAMILY) == ModerationResult.blocked(MATURE)
    assert (await moderation.check("fizz", ADULT)).allowed


@pytest.mark.parametrize("text", ["GLOOP", "the Gloop!", "...gloop, again", "zip-gloop"])
async def test_terms_match_whatever_the_case_or_punctuation(text: str) -> None:
    moderation = StandInModerationAdapter(blocked_always=["gloop"], blocked_for_family=[])

    assert not (await moderation.check(text, ADULT)).allowed


@pytest.mark.parametrize("text", ["gloopy", "ungloop", "glo op"])
async def test_terms_match_only_whole_words(text: str) -> None:
    moderation = StandInModerationAdapter(blocked_always=["gloop"], blocked_for_family=[])

    assert (await moderation.check(text, ADULT)).allowed


async def test_a_phrase_matches_its_words_in_order() -> None:
    moderation = StandInModerationAdapter(blocked_always=["big  Gloop"], blocked_for_family=[])

    assert not (await moderation.check("a big, gloop!", ADULT)).allowed
    assert (await moderation.check("gloop big", ADULT)).allowed
    assert (await moderation.check("big", ADULT)).allowed


async def test_empty_lists_allow_everything() -> None:
    moderation = StandInModerationAdapter(blocked_always=[], blocked_for_family=["", "  "])

    for text in (*BLOCKED_ALWAYS, *BLOCKED_FOR_FAMILY, ""):
        assert (await moderation.check(text, FAMILY)).allowed
