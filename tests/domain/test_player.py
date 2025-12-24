"""Tests for Player domain model."""

from datetime import UTC, datetime

from slop.domain import Player


def test_player_creation():
    """Test creating a player with required fields."""
    player = Player(
        id="player-1",
        name="Alice",
        socket_id="socket-123",
    )

    assert player.id == "player-1"
    assert player.name == "Alice"
    assert player.socket_id == "socket-123"
    assert player.team_id is None
    assert player.is_creator is False
    assert isinstance(player.joined_at, datetime)


def test_player_with_optional_fields():
    """Test creating a player with all fields."""
    now = datetime.now(UTC)
    player = Player(
        id="player-1",
        name="Bob",
        socket_id="socket-456",
        team_id="team-1",
        is_creator=True,
        joined_at=now,
    )

    assert player.id == "player-1"
    assert player.name == "Bob"
    assert player.team_id == "team-1"
    assert player.is_creator is True
    assert player.joined_at == now


def test_player_assign_to_team():
    """Test assigning a player to a team."""
    player = Player(id="player-1", name="Charlie", socket_id="socket-789")

    assert player.team_id is None

    player.assign_to_team("team-2")

    assert player.team_id == "team-2"


def test_player_remove_from_team():
    """Test removing a player from a team."""
    player = Player(
        id="player-1",
        name="Dave",
        socket_id="socket-101",
        team_id="team-1",
    )

    assert player.team_id == "team-1"

    player.remove_from_team()

    assert player.team_id is None


def test_player_update_socket_id():
    """Test updating player's socket ID (for reconnections)."""
    player = Player(id="player-1", name="Eve", socket_id="socket-111")

    assert player.socket_id == "socket-111"

    player.update_socket_id("socket-222")

    assert player.socket_id == "socket-222"
