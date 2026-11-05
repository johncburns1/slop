"""Use case: the host skips a turn that stalled before the acting team got its script.

A team may never agree on a prompt, or the AI may keep failing to write a
script for it. The host can then end the round with no points and pass the
turn on, exactly as if the round had been played: ``move_on`` starts the next
round, starts a tiebreaker, or ends the game. Once the team has its script,
the round plays out instead (the acting team can end guessing early).
"""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, locked_game
from slop.application.finish_or_continue import give_awards_if_finished, move_on
from slop.application.host import check_host
from slop.domain.errors import GameRuleError
from slop.domain.events import GameEvent, RoundCompleted, TurnSkipped
from slop.domain.game import Game, GameStatus
from slop.domain.round import Round


@dataclass(frozen=True)
class SkipTurn:
    """Command for the host to skip the acting team's turn."""

    game_id: str
    player_id: str


async def skip_turn(deps: GameDeps, command: SkipTurn) -> Game:
    """End the current round with no points, tell the room, and move on.

    The room gets ``TurnSkipped`` and then ``RoundCompleted`` with every
    team's unchanged total, followed by whatever ``move_on`` emits. A script
    still being written for the skipped turn is thrown away when it arrives
    (see ``submit_prompt``).

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the player isn't in the game or isn't the host, no
            round is in progress, or the acting team already has its script
    """
    async with locked_game(deps, command.game_id) as game:
        check_host(game, command.player_id)
        current = _stalled_round(game)
        events: list[GameEvent] = [
            TurnSkipped(
                game_id=game.id,
                round_number=current.round_number,
                team_id=current.acting_team_id,
            ),
            RoundCompleted(
                game_id=game.id,
                round_number=current.round_number,
                final_scores={team.id: team.score for team in game.teams},
            ),
        ]
        game = await move_on(deps, await commit(deps, game, events))
    return await give_awards_if_finished(deps, game)


def _stalled_round(game: Game) -> Round:
    """Return the round in progress if its acting team has no script yet, or raise."""
    current = next(
        (r for r in game.rounds if r.round_number == game.current_round),
        None,
    )
    if game.status != GameStatus.PLAYING or current is None:
        raise GameRuleError("No round is in progress")
    if current.script is not None:
        team = game.get_team(current.acting_team_id)
        raise GameRuleError(f"{team.name} already have their script")
    return current
