"""Use case: a player leaves a game, and their team if they had one."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, load_game
from slop.domain.errors import GameRuleError
from slop.domain.events import PlayerLeft
from slop.domain.game import Game


@dataclass(frozen=True)
class LeaveGame:
    """Command for a player to leave a game."""

    game_id: str
    player_id: str


async def leave_game(deps: GameDeps, command: LeaveGame) -> Game:
    """Remove a player from the game and their team, and their connection from its room.

    The event is broadcast before the connection leaves the room, so the
    player hears their own leave too.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the player is not in the game
    """
    game = await load_game(deps, command.game_id)
    player = next((p for p in game.players if p.id == command.player_id), None)
    if player is None:
        raise GameRuleError("That player is not in this game")

    event = PlayerLeft(game_id=game.id, player_id=player.id)
    game = await commit(deps, game, [event])
    await deps.realtime.leave_room(player.socket_id, game.room_code)
    return game
