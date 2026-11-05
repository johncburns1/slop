"""What happens once a round is over: play the next round, break a tie, or end.

After every team has played ``rounds_per_team`` rounds, the team with the most
points wins. Teams tied for first play a tiebreaker cycle in which each of
them acts once, in turn. If a tie for first still stands after
``MAX_TIEBREAKER_CYCLES`` cycles, the game is a draw.

Every team's points count when deciding the leaders, so the tied set is
worked out afresh after each cycle.

A team with no players left (the host removed them all) drops out: it takes no
more turns, regular or tiebreaker, and can't lead, though its score stays.
Once fewer than ``MIN_TEAMS_IN_PLAY`` teams have players, the game ends.
"""

from collections import Counter
from dataclasses import dataclass

from slop.domain.game import Game
from slop.domain.team import Team

MAX_TIEBREAKER_CYCLES = 2
MIN_TEAMS_IN_PLAY = 2


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
    """Return the teams in play on the highest score, in the order they were formed.

    If no team has players left, every team counts.
    """
    teams = game.teams_in_play() or game.teams
    if not teams:
        return []
    top = max(team.score for team in teams)
    return [team for team in teams if team.score == top]


def next_step(game: Game) -> NextStep:
    """Decide what follows once every round before ``game.current_round`` is over."""
    if len(game.teams_in_play()) < MIN_TEAMS_IN_PLAY:
        return end_of_game(game)
    tiebreaker = game.tiebreaker
    if tiebreaker is None:
        team = next_regular_team(game)
        if team is not None:
            return PlayRound(acting_team_id=team.id)
    else:
        acted = {r.acting_team_id for r in game.rounds if r.round_number >= tiebreaker.first_round}
        in_play = {team.id for team in game.teams_in_play()}
        for team_id in tiebreaker.team_ids:
            if team_id not in acted and team_id in in_play:
                return PlayRound(acting_team_id=team_id)
    tied = leaders(game)
    cycle = tiebreaker.cycle if tiebreaker is not None else 0
    if len(tied) == 1 or cycle >= MAX_TIEBREAKER_CYCLES:
        return end_of_game(game)
    return StartTiebreaker(cycle=cycle + 1, team_ids=tuple(team.id for team in tied))


def next_regular_team(game: Game) -> Team | None:
    """Return the team that acts in the next regular round, or None once they are all played.

    Teams take turns in the order they were formed, starting after the team
    that acted last, each until it has acted ``rounds_per_team`` times. Teams
    with no players are skipped. Call it only before any tiebreaker.
    """
    played = Counter(r.acting_team_id for r in game.rounds)
    ids = [team.id for team in game.teams]
    last = game.rounds[-1].acting_team_id if game.rounds else None
    start = ids.index(last) + 1 if last in ids else 0
    for offset in range(len(game.teams)):
        team = game.teams[(start + offset) % len(game.teams)]
        if team.player_ids and played[team.id] < game.settings.rounds_per_team:
            return team
    return None


def end_of_game(game: Game) -> EndGame:
    """End the game now: a single leader wins, and anything else is a draw."""
    tied = leaders(game)
    return EndGame(winner_team_id=tied[0].id if len(tied) == 1 else None)
