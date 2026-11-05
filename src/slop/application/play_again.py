"""Use case: the host starts a new game with the same players and teams."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, locked_game
from slop.application.host import check_host
from slop.domain.errors import GameRuleError
from slop.domain.events import GameRestarted
from slop.domain.game import Game, GameStatus
from slop.domain.game_end import MIN_TEAMS_IN_PLAY


@dataclass(frozen=True)
class PlayAgain:
    """Command for the host to play again once the game has finished."""

    game_id: str
    player_id: str


async def play_again(deps: GameDeps, command: PlayAgain) -> Game:
    """Reset scores, rounds, and personalities, and open personality selection again.

    The game keeps its id and room code, so every player stays in the room.
    To go back to the lobby instead, at any point in the game, see ``restart_game``.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the player isn't in the game or isn't the host, or
            the game hasn't finished, or fewer than two teams still have players
    """
    async with locked_game(deps, command.game_id) as game:
        check_host(game, command.player_id)
        if game.status != GameStatus.FINISHED:
            raise GameRuleError("The game has not finished")
        if len(game.teams_in_play()) < MIN_TEAMS_IN_PLAY:
            raise GameRuleError(f"Playing again needs {MIN_TEAMS_IN_PLAY} teams with players")

        return await commit(deps, game, [GameRestarted(game_id=game.id)])
