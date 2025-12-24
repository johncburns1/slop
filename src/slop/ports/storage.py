"""Storage port interface.

This port defines the contract for persisting game state,
including games, players, and teams.
"""

from typing import Protocol

from slop.domain.game import Game
from slop.domain.player import Player
from slop.domain.team import Team


class StoragePort(Protocol):
    """Interface for game state persistence.

    Implementations can use in-memory storage, databases, or other
    persistence mechanisms.
    """

    async def save_game(self, game: Game) -> None:
        """Save a game to storage.

        Args:
            game: The game to save
        """
        ...

    async def get_game(self, game_id: str) -> Game | None:
        """Retrieve a game by ID.

        Args:
            game_id: The game's unique identifier

        Returns:
            The Game object if found, None otherwise
        """
        ...

    async def delete_game(self, game_id: str) -> None:
        """Delete a game from storage.

        Args:
            game_id: The game's unique identifier
        """
        ...

    async def get_game_by_room_code(self, room_code: str) -> Game | None:
        """Retrieve a game by room code.

        Args:
            room_code: The game's room code

        Returns:
            The Game object if found, None otherwise
        """
        ...

    async def save_player(self, player: Player) -> None:
        """Save a player to storage.

        Args:
            player: The player to save
        """
        ...

    async def get_player(self, player_id: str) -> Player | None:
        """Retrieve a player by ID.

        Args:
            player_id: The player's unique identifier

        Returns:
            The Player object if found, None otherwise
        """
        ...

    async def save_team(self, team: Team) -> None:
        """Save a team to storage.

        Args:
            team: The team to save
        """
        ...

    async def get_team(self, team_id: str) -> Team | None:
        """Retrieve a team by ID.

        Args:
            team_id: The team's unique identifier

        Returns:
            The Team object if found, None otherwise
        """
        ...
