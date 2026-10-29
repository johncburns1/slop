"""Tests for the game-state builders: each named state is a valid game."""

import pytest

from slop.domain import GameStatus
from tests.builders import (
    in_guessing_phase,
    lobby_with_two_teams,
    personalities_assigned,
    tied_after_last_round,
    waiting_for_prompt,
)


def assert_players_match_teams(game):
    """Every player is on exactly the team that lists them."""
    for team in game.teams:
        assert len(team.player_ids) <= team.max_players
        for player_id in team.player_ids:
            assert game.get_player(player_id).team_id == team.id
    listed = [pid for team in game.teams for pid in team.player_ids]
    assert sorted(listed) == sorted(p.id for p in game.players)


def test_lobby_with_two_teams():
    game = lobby_with_two_teams()

    assert game.status == GameStatus.LOBBY
    assert [team.id for team in game.teams] == ["team-1", "team-2"]
    assert len(game.players) == 4
    assert_players_match_teams(game)
    assert [p.id for p in game.players if p.is_creator] == ["player-1"]
    assert all(team.score == 0 for team in game.teams)
    assert all(team.assigned_personality is None for team in game.teams)
    assert game.rounds == []
    assert game.current_round == 0


def test_lobby_with_two_teams_overrides():
    game = lobby_with_two_teams(room_code="WXYZ", players_per_team=3)

    assert game.room_code == "WXYZ"
    assert all(len(team.player_ids) == 3 for team in game.teams)
    assert_players_match_teams(game)


def test_lobby_with_two_teams_rejects_overfull_teams():
    with pytest.raises(ValueError, match="Team is full"):
        lobby_with_two_teams(players_per_team=4)


def test_personalities_assigned():
    game = personalities_assigned()
    red, blue = game.teams

    assert game.status == GameStatus.PERSONALITY_SELECTION
    assert_players_match_teams(game)
    # Each team's personality was picked by the other team, never itself.
    assert (red.assigned_personality, red.personality_assigned_by) == ("noir", "team-2")
    assert (blue.assigned_personality, blue.personality_assigned_by) == ("melodrama", "team-1")


def test_personalities_assigned_overrides():
    game = personalities_assigned(personalities=("absurdist", "noir"))

    assert [team.assigned_personality for team in game.teams] == ["absurdist", "noir"]


def test_in_guessing_phase():
    game = in_guessing_phase()
    current = game.rounds[-1]
    acting = game.get_acting_team()

    assert game.status == GameStatus.PLAYING
    assert not game.is_complete()
    assert_players_match_teams(game)
    assert current.round_number == game.current_round
    assert current.acting_team_id == acting.id
    assert current.submitted_by in acting.player_ids
    assert current.script.personality == acting.assigned_personality
    # Every acting player has a role; no one else does.
    assert sorted(current.role_assignments) == sorted(acting.player_ids)
    assert sorted(current.role_assignments.values()) == list(range(current.script.get_role_count()))
    # Guesses are in from other teams but nothing is decided yet.
    assert current.prompt_guesses
    assert all(g.team_id != acting.id for g in current.prompt_guesses)
    assert not any(g.accepted for g in current.prompt_guesses)
    assert current.prompt_winner_team_id is None
    assert current.personality_guess is None
    assert current.round_score == {}


def test_in_guessing_phase_overrides():
    game = in_guessing_phase(prompt="Robot butler quits during dinner party", guesses=())

    assert game.rounds[-1].prompt == "Robot butler quits during dinner party"
    assert game.rounds[-1].prompt_guesses == []


def test_tied_after_last_round():
    game = tied_after_last_round()

    assert game.status == GameStatus.PLAYING
    assert game.is_complete()
    assert_players_match_teams(game)
    assert len(game.rounds) == game.get_total_rounds() == 6
    assert [r.round_number for r in game.rounds] == list(range(6))
    # Teams alternate acting, as get_acting_team schedules them.
    assert [r.acting_team_id for r in game.rounds] == ["team-1", "team-2"] * 3
    # Team totals equal the sum of the round scores, and they are level.
    for team in game.teams:
        assert team.score == sum(r.round_score.get(team.id, 0) for r in game.rounds)
    assert len({team.score for team in game.teams}) == 1
    assert game.teams[0].score > 0


def test_tied_after_last_round_overrides():
    game = tied_after_last_round(rounds_per_team=1)

    assert len(game.rounds) == 2
    assert game.is_complete()
    assert game.teams[0].score == game.teams[1].score


def test_waiting_for_prompt():
    game = waiting_for_prompt()

    assert game.status == GameStatus.PLAYING
    assert_players_match_teams(game)
    (current,) = game.rounds
    assert (current.round_number, current.acting_team_id) == (0, "team-1")
    assert (current.prompt, current.script, current.role_assignments) == (None, None, {})
    assert game.get_team("team-1").assigned_personality == "noir"
