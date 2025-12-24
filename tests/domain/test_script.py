"""Tests for Script and Role domain models."""

from datetime import UTC, datetime

import pytest

from slop.domain import Role, Script


def test_role_creation():
    """Test creating a role with required fields."""
    role = Role(
        name="Detective",
        description="A hard-boiled detective with a troubled past",
    )

    assert role.name == "Detective"
    assert role.description == "A hard-boiled detective with a troubled past"
    assert role.lines == []


def test_role_with_lines():
    """Test creating a role with dialogue lines."""
    role = Role(
        name="Villain",
        description="An evil mastermind",
        lines=["You'll never catch me!", "Mwahahaha!"],
    )

    assert role.name == "Villain"
    assert len(role.lines) == 2
    assert "You'll never catch me!" in role.lines


def test_script_creation():
    """Test creating a script with required fields."""
    roles = [
        Role(name="Hero", description="A brave hero"),
        Role(name="Sidekick", description="The hero's loyal companion"),
    ]

    script = Script(
        content="A thrilling adventure script...",
        roles=roles,
        personality="dramatic",
    )

    assert script.content == "A thrilling adventure script..."
    assert len(script.roles) == 2
    assert script.personality == "dramatic"
    assert script.word_count > 0
    assert script.estimated_duration > 0
    assert isinstance(script.generated_at, datetime)


def test_script_with_optional_fields():
    """Test creating a script with all fields."""
    now = datetime.now(UTC)
    roles = [Role(name="Actor", description="A talented actor")]

    script = Script(
        content="A short script",
        roles=roles,
        personality="absurdist",
        estimated_duration=45,
        word_count=50,
        generated_at=now,
    )

    assert script.estimated_duration == 45
    assert script.word_count == 50
    assert script.generated_at == now


def test_script_calculate_word_count():
    """Test automatic word count calculation."""
    roles = [Role(name="Speaker", description="A person who speaks")]
    content = "This is a test script with exactly ten words here"

    script = Script(content=content, roles=roles, personality="test")

    assert script.word_count == 10


def test_script_estimate_duration():
    """Test automatic duration estimation (~150 words per minute)."""
    roles = [Role(name="Reader", description="A fast reader")]
    # Create content with ~150 words for 1 minute
    words = " ".join(["word"] * 150)

    script = Script(content=words, roles=roles, personality="test")

    # Should be approximately 60 seconds (with some tolerance)
    assert 55 <= script.estimated_duration <= 65


def test_script_validate_roles_not_empty():
    """Test that script requires at least one role."""
    with pytest.raises(ValueError, match="Script must have at least one role"):
        Script(content="Test content", roles=[], personality="test")


def test_script_get_role_count():
    """Test getting the number of roles in a script."""
    roles = [
        Role(name="A", description="First"),
        Role(name="B", description="Second"),
        Role(name="C", description="Third"),
    ]

    script = Script(content="Test", roles=roles, personality="test")

    assert script.get_role_count() == 3
