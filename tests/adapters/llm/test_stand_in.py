"""Tests for the deterministic stand-in LLM adapter."""

import pytest

from slop.adapters.llm import StandInLLMAdapter
from slop.ports import LLMPort
from tests.adapters.llm.contract import PROMPT, LLMPortContract, make_personality


class TestStandInLLMAdapterContract(LLMPortContract):
    """The stand-in must pass the shared LLM contract."""

    @pytest.fixture
    def adapter(self) -> LLMPort:
        return StandInLLMAdapter()


async def test_same_input_gives_same_script() -> None:
    first = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 3)
    second = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 3)

    assert first == second


async def test_different_prompts_give_different_scripts() -> None:
    adapter = StandInLLMAdapter()
    first = await adapter.generate_script(PROMPT, make_personality(), 3)
    second = await adapter.generate_script(
        "Grandma enters intergalactic baking contest", make_personality(), 3
    )

    assert first.content != second.content


async def test_personality_changes_the_script() -> None:
    adapter = StandInLLMAdapter()
    noir = await adapter.generate_script(PROMPT, make_personality("noir"), 3)
    melodrama = await adapter.generate_script(PROMPT, make_personality("melodrama"), 3)

    assert noir.content != melodrama.content


async def test_script_mentions_prompt() -> None:
    script = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 2)

    assert PROMPT.lower() in script.content.lower()


async def test_every_role_has_lines() -> None:
    script = await StandInLLMAdapter().generate_script(PROMPT, make_personality(), 5)

    for role in script.roles:
        assert role.lines
        for line in role.lines:
            assert f"{role.name}: {line}" in script.content


@pytest.mark.parametrize("num_roles", [0, -1])
async def test_rejects_non_positive_role_count(num_roles: int) -> None:
    with pytest.raises(ValueError, match="num_roles"):
        await StandInLLMAdapter().generate_script(PROMPT, make_personality(), num_roles)


@pytest.mark.parametrize("prompt", ["", "   "])
async def test_rejects_blank_prompt(prompt: str) -> None:
    with pytest.raises(ValueError, match="prompt"):
        await StandInLLMAdapter().generate_script(prompt, make_personality(), 2)
