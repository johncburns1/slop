"""Tests for rebuilding game state from events."""

import pytest

from slop.domain import (
    ContentTone,
    GameCompleted,
    GameEvent,
    GameStatus,
    Guess,
    GuessAccepted,
    GuessSubmitted,
    PersonalityGuessSubmitted,
    PersonalityRevealed,
    PersonalitySelectionStarted,
    PlayerJoinedTeam,
    PlayerLeft,
    PromptSubmitted,
    Role,
    RoleAssigned,
    RoundCompleted,
    TeamDisbanded,
)
from slop.domain.projection import ProjectionError, apply_event, replay
from tests.event_logs import (
    GAME_ID,
    T0,
    at,
    created,
    lobby_events,
    round_one_unguessed_events,
    round_zero_events,
    round_zero_scored_events,
)


def test_game_created_starts_a_lobby_with_its_settings():
    game = replay([created(content_tone="adult", max_players=8, rounds_per_team=2)])

    assert game.id == GAME_ID
    assert game.room_code == "ABCD"
    assert game.status == GameStatus.LOBBY
    assert game.created_at == T0
    assert game.settings.content_tone == ContentTone.ADULT
    assert game.settings.max_players == 8
    assert game.settings.rounds_per_team == 2


def test_players_join_and_the_first_one_is_the_creator():
    game = replay(lobby_events()[:3])

    assert [p.id for p in game.players] == ["player-1", "player-2"]
    first, second = game.players
    assert (first.name, first.socket_id, first.joined_at) == ("Player 1", "socket-1", at(1))
    assert first.is_creator is True
    assert second.is_creator is False


def test_teams_form_with_the_per_team_limit_and_players_join_them():
    game = replay(lobby_events())

    assert [t.id for t in game.teams] == ["team-1", "team-2"]
    red = game.get_team("team-1")
    assert (red.name, red.color, red.max_players) == ("Red", "#F00", 3)
    assert red.player_ids == ["player-1", "player-2"]
    assert game.get_player("player-3").team_id == "team-2"


def test_joining_another_team_moves_the_player():
    game = replay(
        [*lobby_events(), PlayerJoinedTeam(game_id=GAME_ID, player_id="player-1", team_id="team-2")]
    )

    assert game.get_team("team-1").player_ids == ["player-2"]
    assert game.get_team("team-2").player_ids == ["player-3", "player-4", "player-1"]
    assert game.get_player("player-1").team_id == "team-2"


def test_a_player_who_leaves_is_removed_from_the_game_and_their_team():
    game = replay([*lobby_events(), PlayerLeft(game_id=GAME_ID, player_id="player-2")])

    assert [p.id for p in game.players] == ["player-1", "player-3", "player-4"]
    assert game.get_team("team-1").player_ids == ["player-1"]


def test_a_disbanded_team_is_removed_and_its_players_have_no_team():
    game = replay([*lobby_events(), TeamDisbanded(game_id=GAME_ID, team_id="team-1")])

    assert [t.id for t in game.teams] == ["team-2"]
    assert game.get_player("player-1").team_id is None
    assert game.get_player("player-2").team_id is None
    assert game.get_player("player-3").team_id == "team-2"


def test_personality_selection_started_closes_the_lobby():
    game = replay([*lobby_events(), PersonalitySelectionStarted(game_id=GAME_ID)])

    assert game.status == GameStatus.PERSONALITY_SELECTION


def test_personality_selection_can_only_start_from_the_lobby():
    started = PersonalitySelectionStarted(game_id=GAME_ID)
    game = replay([*lobby_events(), started])

    with pytest.raises(ProjectionError, match="not in the lobby"):
        apply_event(game, started)


def test_personality_assigned_records_who_picked_it():
    game = replay([*lobby_events(), *round_zero_events()[:1]])

    team = game.get_team("team-1")
    assert (team.assigned_personality, team.personality_assigned_by) == ("noir", "team-2")


def test_a_round_fills_in_as_its_events_arrive():
    game = replay([*lobby_events(), *round_zero_events()])

    assert game.status == GameStatus.PLAYING
    assert game.current_round == 0
    (current,) = game.rounds
    assert (current.id, current.round_number, current.acting_team_id) == ("round-0", 0, "team-1")
    assert current.timestamp == at(10)
    assert (current.prompt, current.submitted_by) == ("Cat steals the moon", "player-1")
    assert current.script is not None
    assert current.script.content == "Night. A cat eyes the moon."
    assert current.script.personality == "noir"
    assert current.script.roles == [
        Role(name="Cat", description="A cunning cat", lines=["Mine."]),
        Role(name="Moon", description="A worried moon"),
    ]
    assert (current.script.word_count, current.script.estimated_duration) == (6, 3)
    assert current.script.generated_at == at(12)
    assert current.role_assignments == {"player-1": 0, "player-2": 1}
    assert current.get_role_for_player("player-2").name == "Moon"


def test_guessing_and_scoring_a_round():
    events = [*lobby_events(), *round_zero_events(), *round_zero_scored_events()[:-1]]

    game = replay(events)

    (current,) = game.rounds
    assert current.prompt_guesses == [
        Guess(team_id="team-2", guess="Cat crime", timestamp=at(20).timestamp()),
        Guess(team_id="team-2", guess="Moon heist", timestamp=at(21).timestamp(), accepted=True),
    ]
    assert current.prompt_winner_team_id == "team-2"
    assert current.guessing_closed is True
    assert current.personality_guess == "noir"
    assert current.personality_correct is True
    assert current.round_score == {"team-1": 2, "team-2": 1}
    assert [t.score for t in game.teams] == [2, 1]


def team_2_guesses(*texts: str) -> list[GameEvent]:
    return [
        GuessSubmitted(
            game_id=GAME_ID, timestamp=at(20 + i), round_number=0, team_id="team-2", guess=t
        )
        for i, t in enumerate(texts)
    ]


def test_accepting_a_guess_by_index_marks_that_guess():
    accepted = GuessAccepted(game_id=GAME_ID, round_number=0, team_id="team-2", guess_index=0)
    events = [*lobby_events(), *round_zero_events(), *team_2_guesses("Cat crime", "Moon heist")]

    (current,) = replay([*events, accepted]).rounds

    assert [g.accepted for g in current.prompt_guesses] == [True, False]
    assert (current.prompt_winner_team_id, current.guessing_closed) == ("team-2", True)


@pytest.mark.parametrize(
    ("team_id", "guess_index", "message"),
    [("team-2", 2, "no guess 2"), ("team-1", 0, "not from team team-1")],
)
def test_accepting_a_guess_that_does_not_match_is_rejected(team_id, guess_index, message):
    accepted = GuessAccepted(
        game_id=GAME_ID, round_number=0, team_id=team_id, guess_index=guess_index
    )
    events = [*lobby_events(), *round_zero_events(), *team_2_guesses("Cat crime", "Moon heist")]

    with pytest.raises(ProjectionError, match=message):
        replay([*events, accepted])


def test_no_guess_accepted_closes_guessing_without_a_winner():
    events = [*lobby_events(), *round_zero_events(), *round_one_unguessed_events()]

    game = replay(events)

    assert [(r.round_number, r.guessing_closed) for r in game.rounds] == [(0, False), (1, True)]
    assert game.rounds[1].prompt_winner_team_id is None


def test_personality_revealed_is_a_notification_only():
    before = replay([*lobby_events(), *round_zero_events()])
    revealed = PersonalityRevealed(
        game_id=GAME_ID, round_number=0, team_id="team-1", personality_id="noir"
    )

    assert apply_event(before, revealed) == before


def test_a_wrong_personality_guess_is_marked_incorrect():
    events = [
        *lobby_events(),
        *round_zero_events(),
        PersonalityGuessSubmitted(game_id=GAME_ID, round_number=0, personality_guess="melodrama"),
    ]

    assert replay(events).rounds[0].personality_correct is False


def test_round_completed_moves_to_the_next_round_and_checkpoints_scores():
    events = [
        *lobby_events(),
        *round_zero_events(),
        RoundCompleted(game_id=GAME_ID, round_number=0, final_scores={"team-1": 2, "team-2": 1}),
    ]

    game = replay(events)

    assert game.current_round == 1
    assert game.get_acting_team().id == "team-2"
    assert [t.score for t in game.teams] == [2, 1]


def test_game_completed_finishes_the_game_with_final_scores():
    events = [
        *lobby_events(),
        GameCompleted(
            game_id=GAME_ID, final_scores={"team-1": 4, "team-2": 3}, winner_team_id="team-1"
        ),
    ]

    game = replay(events)

    assert game.status == GameStatus.FINISHED
    assert [t.score for t in game.teams] == [4, 3]


def test_apply_event_does_not_mutate_its_input():
    before = replay(lobby_events())

    after = apply_event(before, PlayerLeft(game_id=GAME_ID, player_id="player-1"))

    assert len(before.players) == 4
    assert len(after.players) == 3


def test_replay_needs_game_created_first():
    with pytest.raises(ProjectionError, match="GameCreated"):
        replay(lobby_events()[1:])
    with pytest.raises(ProjectionError, match="GameCreated"):
        replay([])


def test_game_created_cannot_apply_to_an_existing_game():
    with pytest.raises(ProjectionError, match="already exists"):
        apply_event(replay([created()]), created())


def test_events_for_another_game_are_rejected():
    with pytest.raises(ProjectionError, match="game-2"):
        apply_event(replay([created()]), PlayerLeft(game_id="game-2", player_id="player-1"))


def test_events_for_a_round_that_has_not_started_are_rejected():
    event = PromptSubmitted(game_id=GAME_ID, round_number=5, prompt="x", submitted_by="player-1")

    with pytest.raises(ProjectionError, match="Round 5"):
        apply_event(replay(lobby_events()), event)


def test_a_role_not_in_the_script_is_rejected():
    event = RoleAssigned(
        game_id=GAME_ID,
        round_number=0,
        player_id="player-1",
        role_name="Dog",
        character_description="Not in the script",
    )

    with pytest.raises(ProjectionError, match="Dog"):
        replay([*lobby_events(), *round_zero_events(), event])


def test_unknown_event_types_are_rejected():
    class Mystery(GameEvent):
        event_type: str = "Mystery"

    with pytest.raises(ProjectionError, match="Mystery"):
        apply_event(replay([created()]), Mystery(game_id=GAME_ID))
