"""Tests for Storage port interface."""

from typing import Protocol

import pytest

from slop.domain import Game, Player, Team
from slop.ports import StoragePort


def test_storage_port_is_protocol():
    """Test that StoragePort is a Protocol (interface)."""
    assert issubclass(StoragePort, Protocol)


def test_storage_port_has_required_methods():
    """Test that StoragePort defines all required methods."""
    assert hasattr(StoragePort, "save_game")
    assert hasattr(StoragePort, "get_game")
    assert hasattr(StoragePort, "delete_game")
    assert hasattr(StoragePort, "get_game_by_room_code")
    assert hasattr(StoragePort, "save_player")
    assert hasattr(StoragePort, "get_player")
    assert hasattr(StoragePort, "save_team")
    assert hasattr(StoragePort, "get_team")


class MockStorageAdapter:
    """Mock storage adapter for testing protocol compliance."""

    def __init__(self):
        self._games: dict[str, Game] = {}
        self._players: dict[str, Player] = {}
        self._teams: dict[str, Team] = {}
        self._room_codes: dict[str, str] = {}  # room_code -> game_id

    async def save_game(self, game: Game) -> None:
        """Mock save game implementation."""
        self._games[game.id] = game
        self._room_codes[game.room_code] = game.id

    async def get_game(self, game_id: str) -> Game | None:
        """Mock get game implementation."""
        return self._games.get(game_id)

    async def delete_game(self, game_id: str) -> None:
        """Mock delete game implementation."""
        if game_id in self._games:
            game = self._games[game_id]
            del self._games[game_id]
            del self._room_codes[game.room_code]

    async def get_game_by_room_code(self, room_code: str) -> Game | None:
        """Mock get game by room code implementation."""
        game_id = self._room_codes.get(room_code)
        if game_id:
            return self._games.get(game_id)
        return None

    async def save_player(self, player: Player) -> None:
        """Mock save player implementation."""
        self._players[player.id] = player

    async def get_player(self, player_id: str) -> Player | None:
        """Mock get player implementation."""
        return self._players.get(player_id)

    async def save_team(self, team: Team) -> None:
        """Mock save team implementation."""
        self._teams[team.id] = team

    async def get_team(self, team_id: str) -> Team | None:
        """Mock get team implementation."""
        return self._teams.get(team_id)


@pytest.mark.asyncio
async def test_storage_port_save_and_get_game():
    """Test saving and retrieving a game."""
    adapter = MockStorageAdapter()
    game = Game(id="game-1", room_code="ABCD")

    await adapter.save_game(game)
    retrieved = await adapter.get_game("game-1")

    assert retrieved is not None
    assert retrieved.id == "game-1"
    assert retrieved.room_code == "ABCD"


@pytest.mark.asyncio
async def test_storage_port_get_game_by_room_code():
    """Test retrieving a game by room code."""
    adapter = MockStorageAdapter()
    game = Game(id="game-1", room_code="WXYZ")

    await adapter.save_game(game)
    retrieved = await adapter.get_game_by_room_code("WXYZ")

    assert retrieved is not None
    assert retrieved.id == "game-1"


@pytest.mark.asyncio
async def test_storage_port_delete_game():
    """Test deleting a game."""
    adapter = MockStorageAdapter()
    game = Game(id="game-1", room_code="TEST")

    await adapter.save_game(game)
    await adapter.delete_game("game-1")
    retrieved = await adapter.get_game("game-1")

    assert retrieved is None


@pytest.mark.asyncio
async def test_storage_port_save_and_get_player():
    """Test saving and retrieving a player."""
    adapter = MockStorageAdapter()
    player = Player(id="player-1", name="Alice", socket_id="socket-1")

    await adapter.save_player(player)
    retrieved = await adapter.get_player("player-1")

    assert retrieved is not None
    assert retrieved.name == "Alice"


@pytest.mark.asyncio
async def test_storage_port_save_and_get_team():
    """Test saving and retrieving a team."""
    adapter = MockStorageAdapter()
    team = Team(id="team-1", name="Red Team", color="#FF0000")

    await adapter.save_team(team)
    retrieved = await adapter.get_team("team-1")

    assert retrieved is not None
    assert retrieved.name == "Red Team"
