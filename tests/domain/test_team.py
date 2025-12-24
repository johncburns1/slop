"""Tests for Team domain model."""

import pytest

from slop.domain import Team


def test_team_creation():
    """Test creating a team with required fields."""
    team = Team(
        id="team-1",
        name="Red Team",
        color="#FF0000",
    )

    assert team.id == "team-1"
    assert team.name == "Red Team"
    assert team.color == "#FF0000"
    assert team.player_ids == []
    assert team.score == 0
    assert team.assigned_personality is None
    assert team.personality_assigned_by is None


def test_team_with_optional_fields():
    """Test creating a team with all fields."""
    team = Team(
        id="team-1",
        name="Blue Team",
        color="#0000FF",
        player_ids=["player-1", "player-2"],
        score=10,
        assigned_personality="dramatic",
        personality_assigned_by="team-2",
    )

    assert team.player_ids == ["player-1", "player-2"]
    assert team.score == 10
    assert team.assigned_personality == "dramatic"
    assert team.personality_assigned_by == "team-2"


def test_team_add_player():
    """Test adding a player to a team."""
    team = Team(id="team-1", name="Green Team", color="#00FF00")

    assert len(team.player_ids) == 0

    team.add_player("player-1")

    assert len(team.player_ids) == 1
    assert "player-1" in team.player_ids


def test_team_add_player_max_limit():
    """Test that adding players respects max team size."""
    team = Team(id="team-1", name="Yellow Team", color="#FFFF00")

    team.add_player("player-1")
    team.add_player("player-2")
    team.add_player("player-3")

    with pytest.raises(ValueError, match="Team is full"):
        team.add_player("player-4")


def test_team_remove_player():
    """Test removing a player from a team."""
    team = Team(
        id="team-1",
        name="Purple Team",
        color="#800080",
        player_ids=["player-1", "player-2"],
    )

    assert len(team.player_ids) == 2

    team.remove_player("player-1")

    assert len(team.player_ids) == 1
    assert "player-1" not in team.player_ids
    assert "player-2" in team.player_ids


def test_team_remove_player_not_found():
    """Test removing a player that's not on the team."""
    team = Team(id="team-1", name="Orange Team", color="#FFA500")

    with pytest.raises(ValueError, match="Player .* not on team"):
        team.remove_player("player-99")


def test_team_add_score():
    """Test adding points to team score."""
    team = Team(id="team-1", name="Pink Team", color="#FFC0CB")

    assert team.score == 0

    team.add_score(5)

    assert team.score == 5

    team.add_score(3)

    assert team.score == 8


def test_team_assign_personality():
    """Test assigning an AI personality to a team."""
    team = Team(id="team-1", name="Brown Team", color="#A52A2A")

    team.assign_personality("absurdist", assigned_by="team-2")

    assert team.assigned_personality == "absurdist"
    assert team.personality_assigned_by == "team-2"


def test_team_is_full():
    """Test checking if team is at max capacity."""
    team = Team(id="team-1", name="Cyan Team", color="#00FFFF")

    assert not team.is_full()

    team.add_player("player-1")
    team.add_player("player-2")

    assert not team.is_full()

    team.add_player("player-3")

    assert team.is_full()
