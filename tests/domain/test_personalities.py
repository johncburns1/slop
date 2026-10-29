"""Tests for the built-in personality catalog."""

import pytest

from slop.domain.errors import GameRuleError
from slop.domain.personalities import PERSONALITIES, get_personality
from tests.builders import DEFAULT_PERSONALITIES


def test_the_personalities_the_builders_use_are_built_in():
    for personality_id in DEFAULT_PERSONALITIES:
        assert get_personality(personality_id).id == personality_id


def test_every_personality_is_keyed_by_its_id():
    assert all(key == p.id for key, p in PERSONALITIES.items())


def test_an_unknown_personality_is_a_rule_error():
    with pytest.raises(GameRuleError, match="cowboy"):
        get_personality("cowboy")


def test_the_starter_set_has_the_three_classics_and_a_few_more():
    assert {"noir", "melodrama", "absurdist"} <= PERSONALITIES.keys()
    assert 5 <= len(PERSONALITIES) <= 6


def test_every_personality_has_a_short_style_description():
    for personality in PERSONALITIES.values():
        assert 0 < len(personality.description) <= 80
