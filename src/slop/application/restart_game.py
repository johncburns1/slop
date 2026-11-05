"""Use case: the host restarts the game, at any point, back to the lobby."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, locked_game
from slop.application.host import check_host
from slop.domain.errors import GameRuleError
from slop.domain.events import GameReset
from slop.domain.game import Game, GameStatus


@dataclass(frozen=True)
class RestartGame:
    """Command for the host to send everyone back to the lobby."""

    game_id: str
    player_id: str


async def restart_game(deps: GameDeps, command: RestartGame) -> Game:
    """Clear scores, rounds, personalities, and awards, and reopen the lobby.

    Works in personality selection, mid-round, and once the game has finished.
    Players and teams stay as they were, and the game keeps its id and room
    code, so nobody has to rejoin; in the lobby the group can change teams
    before the host starts again. ``play_again`` is the finished-game case
    that skips the lobby. A round that was taking guesses has no round now, so
    tracking the game with ``GuessTimers`` cancels its timer, and a script still
    being written for it is thrown away when it arrives (see ``submit_prompt``).

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the player isn't in the game or isn't the host, or
            the game is already in the lobby
    """
    async with locked_game(deps, command.game_id) as game:
        check_host(game, command.player_id)
        if game.status == GameStatus.LOBBY:
            raise GameRuleError("The game is already in the lobby")

        return await commit(deps, game, [GameReset(game_id=game.id)])
