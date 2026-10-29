"""Use case: the host starts a new game with the same players and teams."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, load_game
from slop.domain.errors import GameRuleError
from slop.domain.events import GameRestarted
from slop.domain.game import Game, GameStatus


@dataclass(frozen=True)
class PlayAgain:
    """Command for the host to play again once the game has finished."""

    game_id: str
    player_id: str


async def play_again(deps: GameDeps, command: PlayAgain) -> Game:
    """Reset scores, rounds, and personalities, and open personality selection again.

    The game keeps its id and room code, so every player stays in the room.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the player isn't in the game or isn't the host, or
            the game hasn't finished
    """
    game = await load_game(deps, command.game_id)
    player = next((p for p in game.players if p.id == command.player_id), None)
    if player is None:
        raise GameRuleError(f"Player {command.player_id} is not in this game")
    if not player.is_creator:
        raise GameRuleError("Only the host can do that")
    if game.status != GameStatus.FINISHED:
        raise GameRuleError("The game has not finished")

    return await commit(deps, game, [GameRestarted(game_id=game.id)])
