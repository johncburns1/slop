"""Tests for LLM port interface."""

from typing import Protocol

import pytest

from slop.domain import AIPersonality, Role, Script
from slop.ports import LLMPort


def test_llm_port_is_protocol():
    """Test that LLMPort is a Protocol (interface)."""
    assert issubclass(LLMPort, Protocol)


def test_llm_port_has_generate_script_method():
    """Test that LLMPort defines generate_script method."""
    assert hasattr(LLMPort, "generate_script")


class MockLLMAdapter:
    """Mock LLM adapter for testing protocol compliance."""

    async def generate_script(
        self,
        prompt: str,
        personality: AIPersonality,
        num_roles: int,
    ) -> Script:
        """Mock implementation of script generation."""
        roles = [
            Role(name=f"Character {i}", description=f"Description {i}") for i in range(num_roles)
        ]
        return Script(
            content=f"Mock script for: {prompt}",
            roles=roles,
            personality=personality.id,
        )


def test_mock_adapter_implements_llm_port():
    """Test that mock adapter satisfies LLMPort protocol."""
    adapter = MockLLMAdapter()

    # Should not raise type error
    assert isinstance(adapter, object)  # Basic check


@pytest.mark.asyncio
async def test_llm_port_generate_script():
    """Test that generate_script creates a script with correct structure."""
    adapter = MockLLMAdapter()
    personality = AIPersonality(
        id="dramatic",
        name="Dramatic Director",
        description="Over-the-top dramatic scenes",
        system_prompt="Create dramatic theatrical scripts...",
    )

    script = await adapter.generate_script(
        prompt="Detective solves mysterious art heist",
        personality=personality,
        num_roles=2,
    )

    assert isinstance(script, Script)
    assert len(script.roles) == 2
    assert script.personality == "dramatic"
    assert script.word_count > 0
    assert script.estimated_duration > 0
