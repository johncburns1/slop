"""Tests for domain events."""

import json
from datetime import UTC, datetime

import pytest

from slop.domain import (
    GameCompleted,
    GameCreated,
    GuessAccepted,
    GuessSubmitted,
    PersonalityAssigned,
    PersonalityGuessSubmitted,
    PlayerJoined,
    PlayerJoinedTeam,
    PlayerLeft,
    PromptSubmitted,
    RoleAssigned,
    RoundCompleted,
    RoundStarted,
    ScoresUpdated,
    ScriptGenerated,
    TeamFormed,
)


def test_game_created_event():
    """Test creating a GameCreated event."""
    event = GameCreated(
        game_id="game-1",
        room_code="ABCD",
        content_tone="family",
        max_players=12,
        rounds_per_team=3,
    )

    assert event.game_id == "game-1"
    assert event.room_code == "ABCD"
    assert event.event_type == "GameCreated"
    assert event.content_tone == "family"
    assert event.max_players == 12
    assert event.rounds_per_team == 3
    assert event.event_id is not None
    assert isinstance(event.timestamp, datetime)


def test_player_joined_event():
    """Test creating a PlayerJoined event."""
    event = PlayerJoined(
        game_id="game-1",
        player_id="player-1",
        player_name="Alice",
        socket_id="socket-123",
    )

    assert event.game_id == "game-1"
    assert event.player_id == "player-1"
    assert event.player_name == "Alice"
    assert event.socket_id == "socket-123"
    assert event.event_type == "PlayerJoined"


def test_player_left_event():
    """Test creating a PlayerLeft event."""
    event = PlayerLeft(
        game_id="game-1",
        player_id="player-1",
    )

    assert event.game_id == "game-1"
    assert event.player_id == "player-1"
    assert event.event_type == "PlayerLeft"


def test_team_formed_event():
    """Test creating a TeamFormed event."""
    event = TeamFormed(
        game_id="game-1",
        team_id="team-1",
        team_name="Red Team",
        color="#FF0000",
    )

    assert event.game_id == "game-1"
    assert event.team_id == "team-1"
    assert event.team_name == "Red Team"
    assert event.color == "#FF0000"
    assert event.event_type == "TeamFormed"


def test_player_joined_team_event():
    """Test creating a PlayerJoinedTeam event."""
    event = PlayerJoinedTeam(
        game_id="game-1",
        player_id="player-1",
        team_id="team-1",
    )

    assert event.game_id == "game-1"
    assert event.player_id == "player-1"
    assert event.team_id == "team-1"
    assert event.event_type == "PlayerJoinedTeam"


def test_personality_assigned_event():
    """Test creating a PersonalityAssigned event."""
    event = PersonalityAssigned(
        game_id="game-1",
        team_id="team-1",
        personality_id="dramatic",
        assigned_by_team_id="team-2",
    )

    assert event.game_id == "game-1"
    assert event.team_id == "team-1"
    assert event.personality_id == "dramatic"
    assert event.assigned_by_team_id == "team-2"
    assert event.event_type == "PersonalityAssigned"


def test_round_started_event():
    """Test creating a RoundStarted event."""
    event = RoundStarted(
        game_id="game-1",
        round_number=1,
        acting_team_id="team-1",
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.acting_team_id == "team-1"
    assert event.event_type == "RoundStarted"


def test_prompt_submitted_event():
    """Test creating a PromptSubmitted event."""
    event = PromptSubmitted(
        game_id="game-1",
        round_number=1,
        prompt="Detective solves mysterious art heist",
        submitted_by="player-1",
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.prompt == "Detective solves mysterious art heist"
    assert event.submitted_by == "player-1"
    assert event.event_type == "PromptSubmitted"


def test_script_generated_event():
    """Test creating a ScriptGenerated event."""
    event = ScriptGenerated(
        game_id="game-1",
        round_number=1,
        script_content="A thrilling detective story...",
        personality_id="dramatic",
        roles=[
            {"name": "Detective", "description": "The lead investigator"},
            {"name": "Thief", "description": "The art thief"},
        ],
        word_count=150,
        estimated_duration=60,
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.script_content == "A thrilling detective story..."
    assert event.personality_id == "dramatic"
    assert len(event.roles) == 2
    assert event.word_count == 150
    assert event.estimated_duration == 60
    assert event.event_type == "ScriptGenerated"


def test_role_assigned_event():
    """Test creating a RoleAssigned event."""
    event = RoleAssigned(
        game_id="game-1",
        round_number=1,
        player_id="player-1",
        role_name="Detective",
        character_description="The lead investigator",
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.player_id == "player-1"
    assert event.role_name == "Detective"
    assert event.character_description == "The lead investigator"
    assert event.event_type == "RoleAssigned"


def test_guess_submitted_event():
    """Test creating a GuessSubmitted event."""
    event = GuessSubmitted(
        game_id="game-1",
        round_number=1,
        team_id="team-2",
        guess="Detective solves art heist",
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.team_id == "team-2"
    assert event.guess == "Detective solves art heist"
    assert event.event_type == "GuessSubmitted"


def test_guess_accepted_event():
    """Test creating a GuessAccepted event."""
    event = GuessAccepted(
        game_id="game-1",
        round_number=1,
        team_id="team-2",
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.team_id == "team-2"
    assert event.event_type == "GuessAccepted"


def test_personality_guess_submitted_event():
    """Test creating a PersonalityGuessSubmitted event."""
    event = PersonalityGuessSubmitted(
        game_id="game-1",
        round_number=1,
        personality_guess="dramatic",
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.personality_guess == "dramatic"
    assert event.event_type == "PersonalityGuessSubmitted"


def test_scores_updated_event():
    """Test creating a ScoresUpdated event."""
    event = ScoresUpdated(
        game_id="game-1",
        round_number=1,
        score_changes={"team-1": 2, "team-2": 1},
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.score_changes == {"team-1": 2, "team-2": 1}
    assert event.event_type == "ScoresUpdated"


def test_round_completed_event():
    """Test creating a RoundCompleted event (recovery checkpoint)."""
    event = RoundCompleted(
        game_id="game-1",
        round_number=1,
        final_scores={"team-1": 5, "team-2": 3},
    )

    assert event.game_id == "game-1"
    assert event.round_number == 1
    assert event.final_scores == {"team-1": 5, "team-2": 3}
    assert event.event_type == "RoundCompleted"


def test_game_completed_event():
    """Test creating a GameCompleted event."""
    event = GameCompleted(
        game_id="game-1",
        final_scores={"team-1": 12, "team-2": 8},
        winner_team_id="team-1",
    )

    assert event.game_id == "game-1"
    assert event.final_scores == {"team-1": 12, "team-2": 8}
    assert event.winner_team_id == "team-1"
    assert event.event_type == "GameCompleted"


def test_event_immutability():
    """Test that events are immutable."""
    event = PlayerJoined(
        game_id="game-1",
        player_id="player-1",
        player_name="Alice",
        socket_id="socket-123",
    )

    with pytest.raises(Exception):  # Pydantic raises ValidationError
        event.player_name = "Bob"


def test_event_json_serialization():
    """Test that events can be serialized to JSON."""
    event = GameCreated(
        game_id="game-1",
        room_code="ABCD",
        content_tone="family",
        max_players=12,
        rounds_per_team=3,
    )

    # Serialize to JSON
    json_str = event.model_dump_json()
    data = json.loads(json_str)

    assert data["game_id"] == "game-1"
    assert data["room_code"] == "ABCD"
    assert data["event_type"] == "GameCreated"
    assert data["content_tone"] == "family"


def test_event_json_deserialization():
    """Test that events can be deserialized from JSON."""
    json_data = {
        "event_id": "evt-123",
        "game_id": "game-1",
        "event_type": "PlayerJoined",
        "timestamp": datetime.now(UTC).isoformat(),
        "player_id": "player-1",
        "player_name": "Alice",
        "socket_id": "socket-123",
    }

    event = PlayerJoined.model_validate(json_data)

    assert event.game_id == "game-1"
    assert event.player_id == "player-1"
    assert event.player_name == "Alice"
    assert event.socket_id == "socket-123"


def test_event_has_unique_id():
    """Test that each event gets a unique ID."""
    event1 = PlayerJoined(
        game_id="game-1",
        player_id="player-1",
        player_name="Alice",
        socket_id="socket-123",
    )
    event2 = PlayerJoined(
        game_id="game-1",
        player_id="player-2",
        player_name="Bob",
        socket_id="socket-456",
    )

    assert event1.event_id != event2.event_id
