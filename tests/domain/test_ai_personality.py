"""Tests for AIPersonality domain model."""

import pytest

from slop.domain import AIPersonality


def test_ai_personality_creation():
    """Test creating an AI personality with required fields."""
    personality = AIPersonality(
        id="dramatic",
        name="Dramatic Director",
        description="Over-the-top dramatic scenes with intense emotions",
        system_prompt="You are a dramatic director creating theatrical scripts...",
    )

    assert personality.id == "dramatic"
    assert personality.name == "Dramatic Director"
    assert personality.description == "Over-the-top dramatic scenes with intense emotions"
    assert personality.system_prompt == "You are a dramatic director creating theatrical scripts..."
    assert personality.example_script is None


def test_ai_personality_with_example():
    """Test creating an AI personality with example script."""
    personality = AIPersonality(
        id="absurdist",
        name="Absurdist Theater",
        description="Nonsensical and surreal scenarios",
        system_prompt="Create absurd theatrical scripts...",
        example_script="[Detective interrogates a sentient banana about tax fraud]",
    )

    assert (
        personality.example_script == "[Detective interrogates a sentient banana about tax fraud]"
    )


def test_ai_personality_validate_id_not_empty():
    """Test that personality ID cannot be empty."""
    with pytest.raises(ValueError, match="ID cannot be empty"):
        AIPersonality(
            id="",
            name="Test",
            description="Test",
            system_prompt="Test",
        )


def test_ai_personality_validate_name_not_empty():
    """Test that personality name cannot be empty."""
    with pytest.raises(ValueError, match="Name cannot be empty"):
        AIPersonality(
            id="test",
            name="",
            description="Test",
            system_prompt="Test",
        )


def test_ai_personality_validate_system_prompt_not_empty():
    """Test that system prompt cannot be empty."""
    with pytest.raises(ValueError, match="System prompt cannot be empty"):
        AIPersonality(
            id="test",
            name="Test",
            description="Test",
            system_prompt="",
        )
