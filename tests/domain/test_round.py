"""Tests for Round and Guess domain models."""

from datetime import UTC, datetime

import pytest

from slop.domain import Guess, Role, RoleAssignment, Round, Script


@pytest.fixture
def sample_script():
    """Create a sample script for testing."""
    roles = [
        Role(name="Hero", description="A brave warrior"),
        Role(name="Villain", description="A dastardly foe"),
    ]
    return Script(
        content="A dramatic confrontation...",
        roles=roles,
        personality="dramatic",
    )


def test_role_assignment_creation():
    """Test creating a role assignment."""
    assignment = RoleAssignment(
        player_id="player-1",
        role_name="Detective",
        character_description="A hard-boiled detective with a troubled past",
    )

    assert assignment.player_id == "player-1"
    assert assignment.role_name == "Detective"
    assert assignment.character_description == "A hard-boiled detective with a troubled past"


def test_guess_creation():
    """Test creating a guess."""
    now = datetime.now(UTC)
    guess = Guess(
        team_id="team-1",
        guess="Superhero saves city",
        timestamp=now.timestamp(),
    )

    assert guess.team_id == "team-1"
    assert guess.guess == "Superhero saves city"
    assert guess.timestamp == now.timestamp()
    assert guess.accepted is False


def test_guess_accept():
    """Test accepting a guess."""
    guess = Guess(
        team_id="team-1",
        guess="Test guess",
        timestamp=datetime.now(UTC).timestamp(),
    )

    guess.accept()

    assert guess.accepted is True


def test_round_creation(sample_script):
    """Test creating a round with required fields."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Superhero saves city from aliens",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={"player-1": 0, "player-2": 1},
    )

    assert round_obj.id == "round-1"
    assert round_obj.round_number == 1
    assert round_obj.acting_team_id == "team-1"
    assert round_obj.prompt == "Superhero saves city from aliens"
    assert round_obj.submitted_by == "player-1"
    assert round_obj.script == sample_script
    assert round_obj.role_assignments == {"player-1": 0, "player-2": 1}
    assert round_obj.prompt_guesses == []
    assert round_obj.prompt_winner_team_id is None
    assert round_obj.personality_guess is None
    assert round_obj.personality_correct is False
    assert round_obj.round_score == {}
    assert isinstance(round_obj.timestamp, datetime)


def test_round_add_guess(sample_script):
    """Test adding a guess to a round."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={},
    )

    guess = Guess(
        team_id="team-2",
        guess="My guess",
        timestamp=datetime.now(UTC).timestamp(),
    )

    round_obj.add_guess(guess)

    assert len(round_obj.prompt_guesses) == 1
    assert round_obj.prompt_guesses[0] == guess


def test_round_set_prompt_winner(sample_script):
    """Test setting the team that won by guessing the prompt."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={},
    )

    round_obj.set_prompt_winner("team-2")

    assert round_obj.prompt_winner_team_id == "team-2"


def test_round_set_personality_guess(sample_script):
    """Test setting the acting team's personality guess."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={},
    )

    round_obj.set_personality_guess("dramatic")

    assert round_obj.personality_guess == "dramatic"


def test_round_check_personality_guess_correct(sample_script):
    """Test checking if personality guess is correct."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={},
    )

    round_obj.set_personality_guess("dramatic")
    round_obj.check_personality_guess()

    assert round_obj.personality_correct is True


def test_round_check_personality_guess_incorrect(sample_script):
    """Test checking if personality guess is incorrect."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={},
    )

    round_obj.set_personality_guess("absurdist")
    round_obj.check_personality_guess()

    assert round_obj.personality_correct is False


def test_round_add_score_to_team(sample_script):
    """Test adding score to a specific team for this round."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={},
    )

    round_obj.add_score_to_team("team-1", 2)
    round_obj.add_score_to_team("team-2", 1)

    assert round_obj.round_score["team-1"] == 2
    assert round_obj.round_score["team-2"] == 1


def test_round_get_role_for_player(sample_script):
    """Test getting the assigned role for a player."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={"player-1": 0, "player-2": 1},
    )

    role = round_obj.get_role_for_player("player-1")

    assert role == sample_script.roles[0]
    assert role.name == "Hero"


def test_round_get_role_for_player_not_found(sample_script):
    """Test getting role for player not in round."""
    round_obj = Round(
        id="round-1",
        round_number=1,
        acting_team_id="team-1",
        prompt="Test prompt",
        submitted_by="player-1",
        script=sample_script,
        role_assignments={},
    )

    with pytest.raises(ValueError, match="Player .* not assigned a role"):
        round_obj.get_role_for_player("player-99")
