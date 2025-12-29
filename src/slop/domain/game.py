"""Game and GameSettings domain models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from slop.domain.player import Player
from slop.domain.round import Round
from slop.domain.team import Team


class GameStatus(Enum):
    """Possible states of a game session."""

    LOBBY = "lobby"
    PERSONALITY_SELECTION = "personality_selection"
    PLAYING = "playing"
    FINISHED = "finished"


class ContentTone(Enum):
    """Content tone options for generated scripts."""

    FAMILY = "family"
    ADULT = "adult"


@dataclass
class GameSettings:
    """Configuration settings for a game session."""

    rounds_per_team: int = 3
    guess_timer_seconds: int = 60
    max_players_per_team: int = 3
    content_tone: ContentTone = ContentTone.FAMILY


@dataclass
class Game:
    """Represents a complete game session.

    A game includes players, teams, rounds, and manages the overall
    game state and progression.
    """

    id: str
    room_code: str
    status: GameStatus = GameStatus.LOBBY
    settings: GameSettings = field(default_factory=GameSettings)
    teams: list[Team] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)
    rounds: list[Round] = field(default_factory=list)
    current_round: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate game fields after initialization."""
        if not (4 <= len(self.room_code) <= 6):
            raise ValueError("Room code must be 4-6 characters")

    def add_player(self, player: Player) -> None:
        """Add a player to the game."""
        self.players.append(player)

    def remove_player(self, player_id: str) -> None:
        """Remove a player from the game.

        Args:
            player_id: The player's ID

        Raises:
            ValueError: If player is not found
        """
        player = self.get_player(player_id)
        self.players.remove(player)

    def get_player(self, player_id: str) -> Player:
        """Get a player by ID.

        Args:
            player_id: The player's ID

        Returns:
            The Player object

        Raises:
            ValueError: If player is not found
        """
        for player in self.players:
            if player.id == player_id:
                return player
        raise ValueError(f"Player {player_id} not found")

    def add_team(self, team: Team) -> None:
        """Add a team to the game."""
        self.teams.append(team)

    def remove_team(self, team_id: str) -> None:
        """Remove a team from the game."""
        team = self.get_team(team_id)
        self.teams.remove(team)

    def get_team(self, team_id: str) -> Team:
        """Get a team by ID.

        Args:
            team_id: The team's ID

        Returns:
            The Team object

        Raises:
            ValueError: If team is not found
        """
        for team in self.teams:
            if team.id == team_id:
                return team
        raise ValueError(f"Team {team_id} not found")

    def start(self) -> None:
        """Start the game.

        Raises:
            ValueError: If game is not in LOBBY status
        """
        if self.status != GameStatus.LOBBY:
            raise ValueError("Game must be in LOBBY status to start")
        self.status = GameStatus.PLAYING

    def finish(self) -> None:
        """Mark the game as finished."""
        self.status = GameStatus.FINISHED

    def set_personality_selection_phase(self) -> None:
        """Move the game to personality selection phase."""
        self.status = GameStatus.PERSONALITY_SELECTION

    def next_round(self) -> None:
        """Advance to the next round."""
        self.current_round += 1

    def get_total_rounds(self) -> int:
        """Calculate the total expected number of rounds.

        Returns:
            Total rounds (number of teams * rounds per team)
        """
        return len(self.teams) * self.settings.rounds_per_team

    def is_complete(self) -> bool:
        """Check if all rounds have been played.

        Returns:
            True if current round >= total expected rounds
        """
        return self.current_round >= self.get_total_rounds()

    def get_acting_team(self) -> Team:
        """Get the team that should be acting in the current round.

        Teams take turns in round-robin fashion.

        Returns:
            The Team object for the current acting team

        Raises:
            ValueError: If there are no teams
        """
        if not self.teams:
            raise ValueError("No teams in game")

        team_index = self.current_round % len(self.teams)
        return self.teams[team_index]
