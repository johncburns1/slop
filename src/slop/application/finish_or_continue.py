"""Use case: once a round is over, start the next round, a tiebreaker, or end the game.

Call it after every ``RoundCompleted``. The rules for what comes next live in
``slop.domain.game_end``.
"""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, load_game
from slop.domain.errors import GameRuleError
from slop.domain.events import GameCompleted, GameEvent, RoundStarted, TiebreakerStarted
from slop.domain.game import Game, GameStatus
from slop.domain.game_end import EndGame, PlayRound, StartTiebreaker, next_step


@dataclass(frozen=True)
class FinishOrContinue:
    """Command to move the game on once its current round is over."""

    game_id: str


async def finish_or_continue(deps: GameDeps, command: FinishOrContinue) -> Game:
    """Start the next round, start a tiebreaker cycle, or end the game, and tell the room.

    Before the regular rounds run out, the next team in turn acts. After
    them, a single leader wins (``GameCompleted``); teams tied for first
    start a tiebreaker cycle (``TiebreakerStarted``) whose first round starts
    straight away; and a tie that outlasts every cycle ends as a draw, with
    no winner.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the game isn't being played or its current round
            is still in play
    """
    game = await load_game(deps, command.game_id)
    if game.status != GameStatus.PLAYING:
        raise GameRuleError("The game is not being played")
    if any(r.round_number == game.current_round for r in game.rounds):
        raise GameRuleError("The current round is still in play")

    events: list[GameEvent] = []
    match next_step(game):
        case PlayRound(acting_team_id=acting_team_id):
            events.append(_round_started(game, acting_team_id))
        case StartTiebreaker(cycle=cycle, team_ids=team_ids):
            events += [
                TiebreakerStarted(
                    game_id=game.id,
                    cycle=cycle,
                    team_ids=list(team_ids),
                    first_round=game.current_round,
                ),
                _round_started(game, team_ids[0]),
            ]
        case EndGame(winner_team_id=winner_team_id):
            events.append(
                GameCompleted(
                    game_id=game.id,
                    final_scores={team.id: team.score for team in game.teams},
                    winner_team_id=winner_team_id,
                )
            )
    return await commit(deps, game, events)


def _round_started(game: Game, acting_team_id: str) -> RoundStarted:
    return RoundStarted(
        game_id=game.id, round_number=game.current_round, acting_team_id=acting_team_id
    )
