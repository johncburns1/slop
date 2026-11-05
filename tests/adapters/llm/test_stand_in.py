"""Tests for the deterministic stand-in LLM adapter."""

import pytest

from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.llm.stand_in import ADULT_CLOSING, AWARD_TITLES
from slop.domain import Award, ContentTone, Script
from slop.ports import LLMPort
from tests.adapters.llm.contract import (
    FAMILY,
    PROMPT,
    LLMPortContract,
    ToneUsed,
    make_personality,
    make_summary,
)


class TestStandInLLMAdapterContract(LLMPortContract):
    """The stand-in must pass the shared LLM contract."""

    @pytest.fixture
    def adapter(self) -> LLMPort:
        return StandInLLMAdapter()

    @pytest.fixture
    def tone_used(self) -> ToneUsed:
        return _tone_of


def _tone_of(result: Script | list[Award]) -> ContentTone:
    """The tone the stand-in wrote this for, judged from its text."""
    if isinstance(result, Script):
        return ContentTone.ADULT if ADULT_CLOSING in result.content else ContentTone.FAMILY
    (tone,) = [
        tone
        for tone, titles in AWARD_TITLES.items()
        if {award.title for award in result} <= set(vars(titles).values())
    ]
    return tone


async def test_same_input_gives_same_script() -> None:
    first = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 3, FAMILY)
    second = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 3, FAMILY)

    assert first == second


async def test_different_prompts_give_different_scripts() -> None:
    adapter = StandInLLMAdapter()
    first = await adapter.generate_script(PROMPT, make_personality(), 3, FAMILY)
    second = await adapter.generate_script(
        "Grandma enters intergalactic baking contest", make_personality(), 3, FAMILY
    )

    assert first.content != second.content


async def test_personality_changes_the_script() -> None:
    adapter = StandInLLMAdapter()
    noir = await adapter.generate_script(PROMPT, make_personality("noir"), 3, FAMILY)
    melodrama = await adapter.generate_script(PROMPT, make_personality("melodrama"), 3, FAMILY)

    assert noir.content != melodrama.content


async def test_script_mentions_prompt() -> None:
    script = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 2, FAMILY)

    assert PROMPT.lower() in script.content.lower()


async def test_every_role_has_lines() -> None:
    script = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 5, FAMILY)

    for role in script.roles:
        assert role.lines
        for line in role.lines:
            assert f"{role.name}: {line}" in script.content


@pytest.mark.parametrize("num_roles", [0, -1])
async def test_rejects_non_positive_role_count(num_roles: int) -> None:
    with pytest.raises(ValueError, match="num_roles"):
        await StandInLLMAdapter().generate_script(PROMPT, make_personality(), num_roles, FAMILY)


@pytest.mark.parametrize("prompt", ["", "   "])
async def test_rejects_blank_prompt(prompt: str) -> None:
    with pytest.raises(ValueError, match="prompt"):
        await StandInLLMAdapter().generate_script(prompt, make_personality(), 2, FAMILY)


async def test_same_summary_gives_same_awards() -> None:
    first = await StandInLLMAdapter().generate_awards(make_summary())
    second = await StandInLLMAdapter().generate_awards(make_summary())

    assert first == second


async def test_awards_quote_a_real_prompt_and_a_real_guess() -> None:
    summary = make_summary()

    awards = await StandInLLMAdapter().generate_awards(summary)

    reasons = " ".join(award.reason for award in awards)
    prompts = [r.prompt for r in summary.rounds if r.prompt]
    guesses = [g.guess for r in summary.rounds for g in r.guesses if not g.correct]
    assert any(f'"{prompt}"' in reasons for prompt in prompts)
    assert any(f'"{guess}"' in reasons for guess in guesses)


async def test_the_winner_gets_an_award_and_a_draw_names_no_winner() -> None:
    won = await StandInLLMAdapter().generate_awards(make_summary(winner="Blue"))
    drawn = await StandInLLMAdapter().generate_awards(make_summary(winner=None))

    assert any(a.recipient == "Blue" and "won" in a.reason for a in won)
    assert not any("won" in a.reason for a in drawn)


async def test_the_content_setting_changes_the_awards() -> None:
    family = await StandInLLMAdapter().generate_awards(make_summary())
    adult = await StandInLLMAdapter().generate_awards(make_summary(content_tone=ContentTone.ADULT))

    assert [a.title for a in family] != [a.title for a in adult]


async def test_an_adult_script_only_adds_the_adult_closing() -> None:
    adapter = StandInLLMAdapter()
    family = await adapter.generate_script(PROMPT, make_personality(), 3, ContentTone.FAMILY)
    adult = await adapter.generate_script(PROMPT, make_personality(), 3, ContentTone.ADULT)

    assert ADULT_CLOSING not in family.content
    assert adult.content == f"{family.content}\n[{ADULT_CLOSING}]"
    assert adult.roles == family.roles
