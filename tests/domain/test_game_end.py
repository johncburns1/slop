"""Tests for deciding what happens after a round: play on, break a tie, or end."""

from slop.domain.game import Tiebreaker
from slop.domain.game_end import (
    MAX_TIEBREAKER_CYCLES,
    EndGame,
    PlayRound,
    StartTiebreaker,
    leaders,
    next_step,
)
from tests.builders import scored_after_last_round, tied_after_last_round, waiting_for_prompt


def test_the_next_regular_round_goes_to_the_next_team_in_turn():
    game = waiting_for_prompt()
    game.next_round()

    assert next_step(game) == PlayRound(acting_team_id="team-2")


def test_a_clear_leader_after_the_last_round_wins():
    game = scored_after_last_round(scores=(4, 2))

    assert next_step(game) == EndGame(winner_team_id="team-1")


def test_teams_tied_for_first_start_the_first_tiebreaker_cycle():
    game = tied_after_last_round()

    assert next_step(game) == StartTiebreaker(cycle=1, team_ids=("team-1", "team-2"))


def test_only_the_teams_tied_for_first_play_the_tiebreaker():
    game = scored_after_last_round(scores=(2, 5, 5))

    assert [team.id for team in leaders(game)] == ["team-2", "team-3"]
    assert next_step(game) == StartTiebreaker(cycle=1, team_ids=("team-2", "team-3"))


def test_each_tied_team_acts_once_in_a_tiebreaker_cycle_in_turn():
    game = scored_after_last_round(scores=(5, 5, 5))
    first = game.current_round
    game.tiebreaker = Tiebreaker(cycle=1, team_ids=["team-1", "team-3"], first_round=first)

    assert next_step(game) == PlayRound(acting_team_id="team-1")
    game.next_round()
    assert next_step(game) == PlayRound(acting_team_id="team-3")


def test_a_tie_broken_in_a_tiebreaker_cycle_ends_the_game():
    game = scored_after_last_round(scores=(5, 6))
    game.tiebreaker = Tiebreaker(
        cycle=1, team_ids=["team-1", "team-2"], first_round=game.current_round - 2
    )

    assert next_step(game) == EndGame(winner_team_id="team-2")


def test_a_tie_still_standing_after_a_cycle_starts_another_among_the_leaders():
    game = scored_after_last_round(scores=(6, 6, 6))
    game.teams[0].score = 7
    game.teams[2].score = 7
    game.tiebreaker = Tiebreaker(
        cycle=1, team_ids=["team-1", "team-2", "team-3"], first_round=game.current_round - 3
    )

    assert next_step(game) == StartTiebreaker(cycle=2, team_ids=("team-1", "team-3"))


def test_a_tie_after_the_last_tiebreaker_cycle_is_a_draw():
    game = scored_after_last_round(scores=(6, 6))
    game.tiebreaker = Tiebreaker(
        cycle=MAX_TIEBREAKER_CYCLES,
        team_ids=["team-1", "team-2"],
        first_round=game.current_round - 2,
    )

    assert MAX_TIEBREAKER_CYCLES == 2
    assert next_step(game) == EndGame(winner_team_id=None)
