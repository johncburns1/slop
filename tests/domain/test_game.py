"""Tests for Game and GameSettings domain models."""

from datetime import datetime

import pytest

from slop.domain import ContentTone, Game, GameSettings, GameStatus, Player, Team


def test_game_status_enum():
    """Test GameStatus enum values."""
    assert GameStatus.LOBBY.value == "lobby"
    assert GameStatus.PERSONALITY_SELECTION.value == "personality_selection"
    assert GameStatus.PLAYING.value == "playing"
    assert GameStatus.FINISHED.value == "finished"


def test_content_tone_enum():
    """Test ContentTone enum values."""
    assert ContentTone.FAMILY.value == "family"
    assert ContentTone.ADULT.value == "adult"


def test_game_settings_creation():
    """Test creating game settings with defaults."""
    settings = GameSettings()

    assert settings.rounds_per_team == 3
    assert settings.guess_timer_seconds == 60
    assert settings.max_players_per_team == 3
    assert settings.content_tone == ContentTone.FAMILY


def test_game_settings_custom_values():
    """Test creating game settings with custom values."""
    settings = GameSettings(
        rounds_per_team=5,
        guess_timer_seconds=90,
        max_players_per_team=4,
        content_tone=ContentTone.ADULT,
    )

    assert settings.rounds_per_team == 5
    assert settings.guess_timer_seconds == 90
    assert settings.max_players_per_team == 4
    assert settings.content_tone == ContentTone.ADULT


def test_game_creation():
    """Test creating a game with required fields."""
    game = Game(
        id="game-1",
        room_code="ABCD",
    )

    assert game.id == "game-1"
    assert game.room_code == "ABCD"
    assert game.status == GameStatus.LOBBY
    assert isinstance(game.settings, GameSettings)
    assert game.teams == []
    assert game.players == []
    assert game.rounds == []
    assert game.current_round == 0
    assert isinstance(game.created_at, datetime)


def test_game_with_custom_settings():
    """Test creating a game with custom settings."""
    settings = GameSettings(rounds_per_team=5, content_tone=ContentTone.ADULT)
    game = Game(
        id="game-1",
        room_code="WXYZ",
        settings=settings,
    )

    assert game.settings.rounds_per_team == 5
    assert game.settings.content_tone == ContentTone.ADULT


def test_game_add_player():
    """Test adding a player to the game."""
    game = Game(id="game-1", room_code="TEST")
    player = Player(id="player-1", name="Alice", socket_id="socket-1")

    game.add_player(player)

    assert len(game.players) == 1
    assert game.players[0] == player


def test_game_remove_player():
    """Test removing a player from the game."""
    game = Game(id="game-1", room_code="TEST")
    player = Player(id="player-1", name="Bob", socket_id="socket-1")
    game.add_player(player)

    game.remove_player("player-1")

    assert len(game.players) == 0


def test_game_remove_player_not_found():
    """Test removing a player that doesn't exist."""
    game = Game(id="game-1", room_code="TEST")

    with pytest.raises(ValueError, match="Player .* not found"):
        game.remove_player("player-99")


def test_game_get_player():
    """Test getting a player by ID."""
    game = Game(id="game-1", room_code="TEST")
    player = Player(id="player-1", name="Charlie", socket_id="socket-1")
    game.add_player(player)

    found_player = game.get_player("player-1")

    assert found_player == player


def test_game_get_player_not_found():
    """Test getting a player that doesn't exist."""
    game = Game(id="game-1", room_code="TEST")

    with pytest.raises(ValueError, match="Player .* not found"):
        game.get_player("player-99")


def test_game_add_team():
    """Test adding a team to the game."""
    game = Game(id="game-1", room_code="TEST")
    team = Team(id="team-1", name="Red Team", color="#FF0000")

    game.add_team(team)

    assert len(game.teams) == 1
    assert game.teams[0] == team


def test_game_remove_team():
    """Test removing a team from the game."""
    game = Game(id="game-1", room_code="TEST")
    team = Team(id="team-1", name="Blue Team", color="#0000FF")
    game.add_team(team)

    game.remove_team("team-1")

    assert len(game.teams) == 0


def test_game_get_team():
    """Test getting a team by ID."""
    game = Game(id="game-1", room_code="TEST")
    team = Team(id="team-1", name="Green Team", color="#00FF00")
    game.add_team(team)

    found_team = game.get_team("team-1")

    assert found_team == team


def test_game_get_team_not_found():
    """Test getting a team that doesn't exist."""
    game = Game(id="game-1", room_code="TEST")

    with pytest.raises(ValueError, match="Team .* not found"):
        game.get_team("team-99")


def test_game_start():
    """Test starting the game."""
    game = Game(id="game-1", room_code="TEST")

    game.start()

    assert game.status == GameStatus.PLAYING


def test_game_start_requires_lobby_status():
    """Test that game can only start from lobby."""
    game = Game(id="game-1", room_code="TEST")
    game.status = GameStatus.PLAYING

    with pytest.raises(ValueError, match="Game must be in LOBBY"):
        game.start()


def test_game_finish():
    """Test finishing the game."""
    game = Game(id="game-1", room_code="TEST")
    game.status = GameStatus.PLAYING

    game.finish()

    assert game.status == GameStatus.FINISHED


def test_game_set_personality_selection_phase():
    """Test moving to personality selection phase."""
    game = Game(id="game-1", room_code="TEST")

    game.set_personality_selection_phase()

    assert game.status == GameStatus.PERSONALITY_SELECTION


def test_game_next_round():
    """Test advancing to the next round."""
    game = Game(id="game-1", room_code="TEST")

    assert game.current_round == 0

    game.next_round()

    assert game.current_round == 1


def test_game_get_total_rounds():
    """Test calculating total expected rounds."""
    game = Game(id="game-1", room_code="TEST")
    game.settings = GameSettings(rounds_per_team=3)
    game.add_team(Team(id="team-1", name="Team 1", color="#FF0000"))
    game.add_team(Team(id="team-2", name="Team 2", color="#00FF00"))

    total_rounds = game.get_total_rounds()

    assert total_rounds == 6  # 2 teams * 3 rounds each


def test_game_is_complete():
    """Test checking if all rounds are complete."""
    game = Game(id="game-1", room_code="TEST")
    game.settings = GameSettings(rounds_per_team=2)
    game.add_team(Team(id="team-1", name="Team 1", color="#FF0000"))
    game.add_team(Team(id="team-2", name="Team 2", color="#00FF00"))

    assert not game.is_complete()

    # Play all rounds (2 teams * 2 rounds = 4 total)
    for _ in range(4):
        game.next_round()

    assert game.is_complete()


def test_game_get_acting_team():
    """Test getting the current acting team."""
    game = Game(id="game-1", room_code="TEST")
    team1 = Team(id="team-1", name="Team 1", color="#FF0000")
    team2 = Team(id="team-2", name="Team 2", color="#00FF00")
    game.add_team(team1)
    game.add_team(team2)

    # Round 0 should be team 1
    acting_team = game.get_acting_team()
    assert acting_team == team1

    # Round 1 should be team 2
    game.next_round()
    acting_team = game.get_acting_team()
    assert acting_team == team2

    # Round 2 should be team 1 again
    game.next_round()
    acting_team = game.get_acting_team()
    assert acting_team == team1


def test_game_validate_room_code():
    """Test room code validation."""
    # Valid room codes
    Game(id="game-1", room_code="ABCD")
    Game(id="game-2", room_code="XY12")

    # Invalid room codes
    with pytest.raises(ValueError, match="Room code must be"):
        Game(id="game-3", room_code="ABC")  # Too short

    with pytest.raises(ValueError, match="Room code must be"):
        Game(id="game-4", room_code="ABCDEFGH")  # Too long
