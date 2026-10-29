"""Reusable contract tests for LLMPort adapters.

Any LLM adapter, including real network-backed ones, plugs in by subclassing
LLMPortContract and overriding the ``adapter`` fixture:

    class TestMyAdapter(LLMPortContract):
        @pytest.fixture
        def adapter(self) -> LLMPort:
            return MyAdapter(...)

Every test here asserts only what the port promises, so it holds for any
correct implementation, deterministic or not.
"""

import pytest

from slop.domain import AIPersonality, Script
from slop.ports import LLMPort

PROMPT = "Detective solves mysterious art heist"

# The port targets ~150 words; allow generous slack for real models.
MIN_WORDS = 50
MAX_WORDS = 300


def make_personality(id: str = "noir") -> AIPersonality:
    """Build a personality for contract tests."""
    return AIPersonality(
        id=id,
        name=f"{id.title()} Director",
        description=f"Scripts in a {id} style",
        system_prompt=f"Write a short {id} script.",
    )


class LLMPortContract:
    """Behavior every LLMPort implementation must satisfy."""

    @pytest.fixture
    def adapter(self) -> LLMPort:
        """Return the adapter under test. Subclasses must override this."""
        raise NotImplementedError("Override the adapter fixture in your subclass")

    async def test_returns_script(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 2)

        assert isinstance(script, Script)

    @pytest.mark.parametrize("num_roles", [1, 2, 3, 4, 5, 6, 8])
    async def test_has_exactly_requested_roles(self, adapter: LLMPort, num_roles: int) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), num_roles)

        assert script.get_role_count() == num_roles

    async def test_roles_have_unique_names_and_descriptions(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 6)

        names = [role.name for role in script.roles]
        assert all(name.strip() for name in names)
        assert len(set(names)) == len(names)
        assert all(role.description.strip() for role in script.roles)

    async def test_every_role_appears_in_content(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 4)

        for role in script.roles:
            assert role.name in script.content

    @pytest.mark.parametrize("personality_id", ["noir", "melodrama", "absurdist", "custom"])
    async def test_uses_requested_personality(self, adapter: LLMPort, personality_id: str) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(personality_id), 2)

        assert script.personality == personality_id

    async def test_length_is_performable(self, adapter: LLMPort) -> None:
        script = await adapter.generate_script(PROMPT, make_personality(), 3)

        assert MIN_WORDS <= script.word_count <= MAX_WORDS
        assert script.word_count == len(script.content.split())
        assert script.estimated_duration > 0
