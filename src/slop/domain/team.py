"""Team domain model."""

from dataclasses import dataclass, field


@dataclass
class Team:
    """Represents a team in the game.

    Teams consist of players and compete to score points.
    Each team gets an AI personality assigned by another team.
    """

    id: str
    name: str
    color: str
    player_ids: list[str] = field(default_factory=list)
    score: int = 0
    assigned_personality: str | None = None
    personality_assigned_by: str | None = None
    max_players: int = 3

    def add_player(self, player_id: str) -> None:
        """Add a player to the team.

        Raises:
            ValueError: If team is already full.
        """
        if self.is_full():
            raise ValueError(f"Team is full (max {self.max_players} players)")
        self.player_ids.append(player_id)

    def remove_player(self, player_id: str) -> None:
        """Remove a player from the team.

        Raises:
            ValueError: If player is not on the team.
        """
        if player_id not in self.player_ids:
            raise ValueError(f"Player {player_id} not on team")
        self.player_ids.remove(player_id)

    def add_score(self, points: int) -> None:
        """Add points to team's total score."""
        self.score += points

    def assign_personality(self, personality_id: str, assigned_by: str) -> None:
        """Assign an AI personality to this team.

        Args:
            personality_id: The ID of the AI personality
            assigned_by: The team ID that assigned this personality
        """
        self.assigned_personality = personality_id
        self.personality_assigned_by = assigned_by

    def is_full(self) -> bool:
        """Check if team is at maximum capacity."""
        return len(self.player_ids) >= self.max_players
