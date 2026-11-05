"""Tests for deciding what happens after a round: play on, break a tie, or end."""

from slop.domain.game import Game, Tiebreaker
from slop.domain.game_end import (
    MAX_TIEBREAKER_CYCLES,
    EndGame,
    PlayRound,
    StartTiebreaker,
    leaders,
    next_step,
)
from slop.domain.round import Round
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
    play(game, "team-1")
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


def play(game: Game, team_id: str) -> None:
    """Record a round for ``team_id`` at the current round number, and move past it."""
    number = game.current_round
    game.rounds.append(Round(id=f"round-{number}", round_number=number, acting_team_id=team_id))
    game.next_round()


def empty(game: Game, team_id: str) -> None:
    """Take every player off the team, as if the host had removed them all."""
    team = game.get_team(team_id)
    for player_id in list(team.player_ids):
        team.remove_player(player_id)
        game.remove_player(player_id)


def test_a_team_with_no_players_is_skipped_in_the_turn_order():
    game = scored_after_last_round(scores=(0, 0, 0), rounds_per_team=2)
    game.rounds.clear()
    game.current_round = 0
    play(game, "team-1")
    empty(game, "team-2")

    assert next_step(game) == PlayRound(acting_team_id="team-3")
    play(game, "team-3")
    assert next_step(game) == PlayRound(acting_team_id="team-1")
    play(game, "team-1")
    assert next_step(game) == PlayRound(acting_team_id="team-3")
    play(game, "team-3")
    assert next_step(game) == StartTiebreaker(cycle=1, team_ids=("team-1", "team-3"))


def test_a_team_that_dropped_out_keeps_its_score_but_cannot_win_or_tie():
    game = scored_after_last_round(scores=(3, 9, 3))
    empty(game, "team-2")

    assert [team.id for team in leaders(game)] == ["team-1", "team-3"]
    assert next_step(game) == StartTiebreaker(cycle=1, team_ids=("team-1", "team-3"))
    assert game.get_team("team-2").score == 9


def test_a_tied_team_left_with_no_players_misses_its_tiebreaker_turn():
    game = scored_after_last_round(scores=(5, 5, 5))
    game.tiebreaker = Tiebreaker(
        cycle=1, team_ids=["team-1", "team-2", "team-3"], first_round=game.current_round
    )
    play(game, "team-1")
    empty(game, "team-2")

    assert next_step(game) == PlayRound(acting_team_id="team-3")


def test_the_game_ends_when_fewer_than_two_teams_have_players():
    game = waiting_for_prompt()
    game.next_round()
    empty(game, "team-2")

    assert next_step(game) == EndGame(winner_team_id="team-1")
