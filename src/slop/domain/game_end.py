"""What happens once a round is over: play the next round, break a tie, or end.

After every team has played ``rounds_per_team`` rounds, the team with the most
points wins. Teams tied for first play a tiebreaker cycle in which each of
them acts once, in turn. If a tie for first still stands after
``MAX_TIEBREAKER_CYCLES`` cycles, the game is a draw.

Every team's points count when deciding the leaders, so the tied set is
worked out afresh after each cycle.
"""

from dataclasses import dataclass

from slop.domain.game import Game
from slop.domain.team import Team

MAX_TIEBREAKER_CYCLES = 2


@dataclass(frozen=True)
class PlayRound:
    """Play the round numbered ``game.current_round`` with this team acting."""

    acting_team_id: str


@dataclass(frozen=True)
class StartTiebreaker:
    """Start tiebreaker ``cycle``: each team in ``team_ids`` acts once, in this order."""

    cycle: int
    team_ids: tuple[str, ...]


@dataclass(frozen=True)
class EndGame:
    """End the game. ``winner_team_id`` is None for a draw."""

    winner_team_id: str | None


NextStep = PlayRound | StartTiebreaker | EndGame


def leaders(game: Game) -> list[Team]:
    """Return the teams on the highest score, in the order they were formed."""
    if not game.teams:
        return []
    top = max(team.score for team in game.teams)
    return [team for team in game.teams if team.score == top]


def next_step(game: Game) -> NextStep:
    """Decide what follows once every round before ``game.current_round`` is over."""
    if not game.is_complete():
        return PlayRound(acting_team_id=game.get_acting_team().id)
    tiebreaker = game.tiebreaker
    if tiebreaker is not None:
        played = game.current_round - tiebreaker.first_round
        if played < len(tiebreaker.team_ids):
            return PlayRound(acting_team_id=tiebreaker.team_ids[played])
    tied = leaders(game)
    if len(tied) == 1:
        return EndGame(winner_team_id=tied[0].id)
    cycle = tiebreaker.cycle if tiebreaker is not None else 0
    if cycle >= MAX_TIEBREAKER_CYCLES:
        return EndGame(winner_team_id=None)
    return StartTiebreaker(cycle=cycle + 1, team_ids=tuple(team.id for team in tied))
