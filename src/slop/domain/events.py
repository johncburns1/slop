"""Domain events for event sourcing.

All game state changes are represented as immutable events that can be
serialized, stored, and broadcast to clients.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class GameEvent(BaseModel):
    """Base class for all domain events.

    Events are immutable records of state changes in the game.
    They form the append-only event log for event sourcing.
    """

    model_config = ConfigDict(frozen=True)  # Make events immutable

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    game_id: str
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GameCreated(GameEvent):
    """Emitted when a new game is created."""

    event_type: str = "GameCreated"
    room_code: str
    content_tone: str
    max_players: int
    rounds_per_team: int


class PlayerJoined(GameEvent):
    """Emitted when a player joins a game."""

    event_type: str = "PlayerJoined"
    player_id: str
    player_name: str
    socket_id: str


class PlayerLeft(GameEvent):
    """Emitted when a player leaves a game."""

    event_type: str = "PlayerLeft"
    player_id: str


class TeamFormed(GameEvent):
    """Emitted when a team is created."""

    event_type: str = "TeamFormed"
    team_id: str
    team_name: str
    color: str


class PlayerJoinedTeam(GameEvent):
    """Emitted when a player joins a team."""

    event_type: str = "PlayerJoinedTeam"
    player_id: str
    team_id: str


class PersonalityAssigned(GameEvent):
    """Emitted when a team is assigned an AI personality."""

    event_type: str = "PersonalityAssigned"
    team_id: str
    personality_id: str
    assigned_by_team_id: str


class RoundStarted(GameEvent):
    """Emitted when a new round begins."""

    event_type: str = "RoundStarted"
    round_number: int
    acting_team_id: str


class PromptSubmitted(GameEvent):
    """Emitted when a prompt is submitted for a round."""

    event_type: str = "PromptSubmitted"
    round_number: int
    prompt: str
    submitted_by: str  # player_id


class ScriptGenerated(GameEvent):
    """Emitted when an AI script is generated."""

    event_type: str = "ScriptGenerated"
    round_number: int
    script_content: str
    personality_id: str
    roles: list[dict[str, Any]]  # List of role data
    word_count: int
    estimated_duration: int


class RoleAssigned(GameEvent):
    """Emitted when a role is assigned to a player."""

    event_type: str = "RoleAssigned"
    round_number: int
    player_id: str
    role_name: str
    character_description: str


class GuessSubmitted(GameEvent):
    """Emitted when a team submits a guess for the prompt."""

    event_type: str = "GuessSubmitted"
    round_number: int
    team_id: str
    guess: str


class GuessAccepted(GameEvent):
    """Emitted when a guess is accepted as correct."""

    event_type: str = "GuessAccepted"
    round_number: int
    team_id: str


class PersonalityGuessSubmitted(GameEvent):
    """Emitted when the acting team guesses the AI personality."""

    event_type: str = "PersonalityGuessSubmitted"
    round_number: int
    personality_guess: str


class ScoresUpdated(GameEvent):
    """Emitted when scores are calculated and updated."""

    event_type: str = "ScoresUpdated"
    round_number: int
    score_changes: dict[str, int]  # team_id -> points awarded


class RoundCompleted(GameEvent):
    """Emitted when a round is completed (recovery checkpoint).

    This event serves as a checkpoint for crash recovery.
    """

    event_type: str = "RoundCompleted"
    round_number: int
    final_scores: dict[str, int]  # team_id -> total score


class GameCompleted(GameEvent):
    """Emitted when the game ends."""

    event_type: str = "GameCompleted"
    final_scores: dict[str, int]  # team_id -> final score
    winner_team_id: str | None
