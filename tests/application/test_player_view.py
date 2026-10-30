"""Tests for what each player may see of a game."""

import pytest

from slop.application.player_view import PlayerView, player_view
from slop.domain import GameStatus
from slop.domain.errors import GameRuleError
from tests.builders import (
    DEFAULT_PROMPT,
    in_guessing_phase,
    lobby_with_two_teams,
    selecting_personalities,
    tied_after_last_round,
    waiting_for_prompt,
)

# In the builders, team 1 (players 1 and 2) acts first, with ``noir`` picked by
# team 2; team 2 (players 3 and 4) guesses, with ``melodrama`` picked by team 1.


def personalities_in(view: PlayerView) -> set[str]:
    """Every personality id the view mentions anywhere."""
    return {p for p in ("noir", "melodrama", "absurdist") if p in repr(view)}


def test_everyone_sees_the_lobby_teams_and_scores():
    game = lobby_with_two_teams()
    game.get_team("team-2").add_score(2)

    view = player_view(game, "player-3")

    assert (view.game_id, view.room_code, view.status) == ("game-1", "ABCD", GameStatus.LOBBY)
    assert (view.player_id, view.team_id) == ("player-3", "team-2")
    assert [(p.id, p.team_id, p.is_host) for p in view.players] == [
        ("player-1", "team-1", True),
        ("player-2", "team-1", False),
        ("player-3", "team-2", False),
        ("player-4", "team-2", False),
    ]
    assert [(t.id, t.name, t.player_ids, t.score) for t in view.teams] == [
        ("team-1", "Red Team", ("player-1", "player-2"), 0),
        ("team-2", "Blue Team", ("player-3", "player-4"), 2),
    ]
    assert view.settings.rounds_per_team == game.settings.rounds_per_team
    assert view.current_round is None
    assert view.my_pick is None


def test_only_the_picking_team_sees_its_pick_and_everyone_sees_that_it_picked():
    game = selecting_personalities()
    game.get_team("team-2").assign_personality("noir", assigned_by="team-1")

    picker = player_view(game, "player-1")
    target = player_view(game, "player-3")

    assert picker.my_pick is not None
    assert (picker.my_pick.team_id, picker.my_pick.personality_id) == ("team-2", "noir")
    assert target.my_pick is None
    assert personalities_in(target) == set()
    for view in (picker, target):
        assert [t.has_picked for t in view.teams] == [True, False]
        assert [t.personality_id for t in view.teams] == [None, None]


def test_the_acting_team_sees_the_prompt_script_and_roles_mid_round():
    game = in_guessing_phase()

    view = player_view(game, "player-2")

    current = view.current_round
    assert current is not None
    assert (current.round_number, current.acting_team_id) == (0, "team-1")
    assert current.phase == "guessing"
    assert current.prompt == DEFAULT_PROMPT
    assert current.script is not None
    assert current.script.content == f"A short scene about {DEFAULT_PROMPT}."
    assert [(r.name, r.player_id) for r in current.script.roles] == [
        ("Character 1", "player-1"),
        ("Character 2", "player-2"),
    ]
    assert [g.guess for g in current.guesses] == [
        "Aliens invade a city",
        "Hero fights space monsters",
    ]


def test_the_acting_team_never_sees_its_own_personality_before_the_reveal():
    view = player_view(in_guessing_phase(), "player-1")

    # Only the pick team 1 made for team 2, never the personality it is performing with.
    assert personalities_in(view) == {"melodrama"}
    assert [t.personality_id for t in view.teams] == [None, None]


def test_guessing_teams_see_the_phase_and_guesses_but_no_prompt_script_or_secret():
    view = player_view(in_guessing_phase(), "player-3")

    current = view.current_round
    assert current is not None
    assert (current.acting_team_id, current.phase) == ("team-1", "guessing")
    assert len(current.guesses) == 2
    assert current.prompt is None
    assert current.script is None
    assert DEFAULT_PROMPT not in repr(view)
    assert personalities_in(view) == {"noir"}  # its own pick for team 1, nothing else


def test_the_round_phase_follows_the_round():
    game = waiting_for_prompt()
    phases = [player_view(game, "player-3").current_round]
    game = in_guessing_phase()
    phases.append(player_view(game, "player-3").current_round)
    game.rounds[0].close_guessing()
    phases.append(player_view(game, "player-3").current_round)

    assert [p.phase if p else None for p in phases] == [
        "waiting_for_prompt",
        "guessing",
        "guessing_personality",
    ]


def test_a_personality_is_shown_to_everyone_once_it_has_been_revealed():
    game = in_guessing_phase()
    current = game.rounds[0]
    current.close_guessing()
    current.set_personality_guess("noir")
    current.check_personality_guess()

    for player_id in ("player-1", "player-3"):
        view = player_view(game, player_id)
        assert [t.personality_id for t in view.teams] == ["noir", None]
    assert personalities_in(player_view(game, "player-3")) == {"noir"}


def test_no_round_is_shown_between_the_last_round_and_what_comes_next():
    view = player_view(tied_after_last_round(rounds_per_team=1), "player-1")

    assert view.current_round is None
    assert [t.score for t in view.teams] == [2, 2]


def test_a_player_not_in_the_game_has_no_view():
    with pytest.raises(GameRuleError, match="player-9"):
        player_view(lobby_with_two_teams(), "player-9")
