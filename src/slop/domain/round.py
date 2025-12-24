"""Round and Guess domain models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from slop.domain.script import Role, Script


@dataclass
class Guess:
    """Represents a team's guess for the original prompt.

    Guesses are made by teams trying to determine what prompt
    the acting team submitted.
    """

    team_id: str
    guess: str
    timestamp: float
    accepted: bool = False

    def accept(self) -> None:
        """Mark this guess as accepted by the acting team."""
        self.accepted = True


@dataclass
class Round:
    """Represents a single round of gameplay.

    Each round involves one team acting out a script while others guess
    the original prompt. The acting team also guesses which AI personality
    was used to generate their script.
    """

    id: str
    round_number: int
    acting_team_id: str
    prompt: str
    submitted_by: str
    script: Script
    role_assignments: dict[str, int]  # player_id -> role index
    prompt_guesses: list[Guess] = field(default_factory=list)
    prompt_winner_team_id: str | None = None
    personality_guess: str | None = None
    personality_correct: bool = False
    round_score: dict[str, int] = field(default_factory=dict)  # team_id -> points
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_guess(self, guess: Guess) -> None:
        """Add a prompt guess from a team."""
        self.prompt_guesses.append(guess)

    def set_prompt_winner(self, team_id: str) -> None:
        """Set which team won by guessing the prompt correctly."""
        self.prompt_winner_team_id = team_id

    def set_personality_guess(self, personality_id: str) -> None:
        """Set the acting team's guess for the AI personality."""
        self.personality_guess = personality_id

    def check_personality_guess(self) -> None:
        """Check if the personality guess is correct."""
        if self.personality_guess == self.script.personality:
            self.personality_correct = True
        else:
            self.personality_correct = False

    def add_score_to_team(self, team_id: str, points: int) -> None:
        """Add points to a specific team's score for this round."""
        if team_id not in self.round_score:
            self.round_score[team_id] = 0
        self.round_score[team_id] += points

    def get_role_for_player(self, player_id: str) -> Role:
        """Get the role assigned to a specific player.

        Args:
            player_id: The player's ID

        Returns:
            The Role object assigned to this player

        Raises:
            ValueError: If player is not assigned a role in this round
        """
        if player_id not in self.role_assignments:
            raise ValueError(f"Player {player_id} not assigned a role in this round")

        role_index = self.role_assignments[player_id]
        return self.script.roles[role_index]
