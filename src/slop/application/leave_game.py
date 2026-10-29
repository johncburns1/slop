"""Use case: a player leaves a game in the lobby."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, load_game
from slop.domain.errors import GameRuleError
from slop.domain.events import PlayerLeft
from slop.domain.game import Game, GameStatus


@dataclass(frozen=True)
class LeaveGame:
    """Command for ``player_id`` to leave the game ``game_id``."""

    game_id: str
    player_id: str


async def leave_game(deps: GameDeps, command: LeaveGame) -> Game:
    """Remove a player from the lobby (and their team), and tell the room.

    The leaving player hears it too, then their socket leaves the room.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the player isn't in the game, or the game has started
    """
    game = await load_game(deps, command.game_id)
    player = next((p for p in game.players if p.id == command.player_id), None)
    if player is None:
        raise GameRuleError("That player is not in this game")
    if game.status != GameStatus.LOBBY:
        raise GameRuleError("This game has already started, so players can't leave")

    game = await commit(deps, game, [PlayerLeft(game_id=game.id, player_id=player.id)])
    await deps.realtime.leave_room(player.socket_id, game.room_code)
    return game
