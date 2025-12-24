"""Player domain model."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Player:
    """Represents a player in the game.

    Players join games, are assigned to teams, and participate in rounds.
    """

    id: str
    name: str
    socket_id: str
    team_id: str | None = None
    is_creator: bool = False
    joined_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def assign_to_team(self, team_id: str) -> None:
        """Assign player to a team."""
        self.team_id = team_id

    def remove_from_team(self) -> None:
        """Remove player from their current team."""
        self.team_id = None

    def update_socket_id(self, socket_id: str) -> None:
        """Update player's socket ID (for reconnections)."""
        self.socket_id = socket_id
