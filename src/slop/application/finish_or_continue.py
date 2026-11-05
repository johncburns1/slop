"""Use case: once a round is over, start the next round, a tiebreaker, or end the game.

Call it after every ``RoundCompleted``. The rules for what comes next live in
``slop.domain.game_end``.
"""

from dataclasses import dataclass

from slop.application.awards import give_awards
from slop.application.engine import GameDeps, commit, locked_game
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
    no winner. Once the game has ended, the room gets the LLM's awards
    (``AwardsGiven``, see ``slop.application.awards``), if it wrote any usable.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the game isn't being played or its current round
            is still in play
    """
    async with locked_game(deps, command.game_id) as game:
        game = await move_on(deps, game)
    return await give_awards_if_finished(deps, game)


async def move_on(deps: GameDeps, game: Game) -> Game:
    """Do what ``finish_or_continue`` does, short of the awards, for its caller holding the lock.

    Raises:
        GameRuleError: If the game isn't being played or its current round
            is still in play
    """
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


async def give_awards_if_finished(deps: GameDeps, game: Game) -> Game:
    """Ask for the awards if ``move_on`` ended the game. Call it without holding the lock."""
    return await give_awards(deps, game) if game.status == GameStatus.FINISHED else game


def _round_started(game: Game, acting_team_id: str) -> RoundStarted:
    return RoundStarted(
        game_id=game.id, round_number=game.current_round, acting_team_id=acting_team_id
    )
