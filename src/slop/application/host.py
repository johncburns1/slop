"""Checks shared by the use cases only the host may run."""

from slop.domain.errors import GameRuleError
from slop.domain.game import Game
from slop.domain.player import Player


def check_host(game: Game, player_id: str) -> Player:
    """Return the player if they are the game's host, or raise.

    Raises:
        GameRuleError: If the player isn't in the game or isn't the host
    """
    player = next((p for p in game.players if p.id == player_id), None)
    if player is None:
        raise GameRuleError(f"Player {player_id} is not in this game")
    if not player.is_creator:
        raise GameRuleError("Only the host can do that")
    return player
