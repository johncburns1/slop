"""Tests for guessing the prompt, judging the guesses, and scoring the round."""

import json
from functools import reduce

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application import guess_and_score
from slop.application.engine import GameDeps, load_game
from slop.application.guess_and_score import (
    GuessPersonality,
    PickWinningGuess,
    SubmitGuess,
    guess_personality,
    pick_winning_guess,
    submit_guess,
)
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain import (
    Game,
    GameCompleted,
    GameStatus,
    GuessAccepted,
    GuessSubmitted,
    NoGuessAccepted,
    PersonalityGuessSubmitted,
    PersonalityRevealed,
    RoundCompleted,
    RoundStarted,
    ScoresUpdated,
)
from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.domain.projection import apply_event
from tests.builders import (
    in_guessing_phase,
    in_last_round_guessing_phase,
    personalities_assigned,
    waiting_for_prompt,
)
from tests.evidence import write_evidence

# In the builders, team 1 (players 1 and 2) acts first and team 2 (players 3 and 4) guesses.
ACTING_SOCKETS = {"socket-1", "socket-2"}
OTHER_SOCKETS = {"socket-3", "socket-4"}
ALL_SOCKETS = ACTING_SOCKETS | OTHER_SOCKETS


async def start(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game and put every player's socket in its room."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return game


async def play_out(
    deps: GameDeps, game: Game, *, winning_guess: int | None, personality: str
) -> Game:
    """Have team 1 judge the guesses, then guess its personality."""
    game = await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", winning_guess))
    return await guess_personality(deps, GuessPersonality(game.id, "player-2", personality))


# Guessing the prompt


async def test_any_number_of_guesses_from_other_teams_go_to_the_whole_room(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase(guesses=()))

    for player_id, text in [("player-3", "Aliens attack"), ("player-4", "Hero"), ("player-3", "x")]:
        game = await submit_guess(deps, SubmitGuess(game.id, player_id, text))

    (current,) = game.rounds
    assert [(g.team_id, g.guess) for g in current.prompt_guesses] == [
        ("team-2", "Aliens attack"),
        ("team-2", "Hero"),
        ("team-2", "x"),
    ]
    events = await storage.get_events(game.id)
    assert [type(e) for e in events] == [GuessSubmitted] * 3
    for socket_id in ALL_SOCKETS:
        assert realtime.received_by(socket_id) == events
    assert await load_game(deps, game.id) == game


async def test_a_guess_is_trimmed(deps: GameDeps, realtime: RecordingRealtime):
    game = await start(deps, realtime, in_guessing_phase(guesses=()))

    game = await submit_guess(deps, SubmitGuess(game.id, "player-3", "  Aliens \t attack \n"))

    assert game.rounds[0].prompt_guesses[0].guess == "Aliens attack"


@pytest.mark.parametrize("player_id", ["player-1", "player-2"])
async def test_the_acting_team_cannot_guess_its_own_prompt(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, player_id: str
):
    game = await start(deps, realtime, in_guessing_phase(guesses=()))

    with pytest.raises(GameRuleError, match="acting team can't guess"):
        await submit_guess(deps, SubmitGuess(game.id, player_id, "Superhero saves city"))

    assert await storage.get_events(game.id) == []
    assert realtime.who_received(GuessSubmitted) == frozenset()


@pytest.mark.parametrize(
    ("player_id", "guess", "message"),
    [
        ("player-3", "   ", "can't be blank"),
        ("player-9", "Aliens", "not in this game"),
    ],
)
async def test_bad_guesses_are_rejected(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, player_id, guess, message
):
    game = await start(deps, realtime, in_guessing_phase(guesses=()))

    with pytest.raises(GameRuleError, match=message):
        await submit_guess(deps, SubmitGuess(game.id, player_id, guess))

    assert await storage.get_events(game.id) == []


async def test_guessing_waits_for_the_script(deps: GameDeps, realtime: RecordingRealtime):
    game = await start(deps, realtime, waiting_for_prompt())

    with pytest.raises(GameRuleError, match="doesn't have its script yet"):
        await submit_guess(deps, SubmitGuess(game.id, "player-3", "Aliens"))


async def test_guessing_needs_a_round_in_progress(deps: GameDeps, realtime: RecordingRealtime):
    game = await start(deps, realtime, personalities_assigned())

    with pytest.raises(GameRuleError, match="No round is in progress"):
        await submit_guess(deps, SubmitGuess(game.id, "player-3", "Aliens"))


async def test_guessing_closes_once_the_acting_team_has_judged(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", None))

    with pytest.raises(GameRuleError, match="Guessing is over"):
        await submit_guess(deps, SubmitGuess(game.id, "player-3", "Too late"))


async def test_guessing_in_an_unknown_game_fails(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await submit_guess(deps, SubmitGuess("nope", "player-3", "Aliens"))


# Judging the guesses


async def test_the_acting_team_picks_the_winning_guess_and_the_room_hears_it(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())

    game = await pick_winning_guess(deps, PickWinningGuess(game.id, "player-2", 0))

    (current,) = game.rounds
    assert [g.accepted for g in current.prompt_guesses] == [True, False]
    assert (current.prompt_winner_team_id, current.guessing_closed) == ("team-2", True)
    (accepted,) = await storage.get_events(game.id)
    assert isinstance(accepted, GuessAccepted)
    assert (accepted.team_id, accepted.guess_index) == ("team-2", 0)
    assert realtime.who_received(GuessAccepted) == ALL_SOCKETS
    assert game.teams[1].score == 0, "points are scored when the round completes"


async def test_the_acting_team_can_say_nobody_got_it(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())

    game = await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", None))

    (current,) = game.rounds
    assert not any(g.accepted for g in current.prompt_guesses)
    assert (current.prompt_winner_team_id, current.guessing_closed) == (None, True)
    assert [type(e) for e in await storage.get_events(game.id)] == [NoGuessAccepted]
    assert realtime.who_received(NoGuessAccepted) == ALL_SOCKETS


async def test_nobody_got_it_works_with_no_guesses_at_all(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase(guesses=()))

    game = await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", None))

    assert game.rounds[0].guessing_closed


@pytest.mark.parametrize(
    ("player_id", "guess_index", "message"),
    [
        ("player-3", 0, "not on the acting team"),
        ("player-9", 0, "not in this game"),
        ("player-1", 2, "No guess 2"),
        ("player-1", -1, "No guess -1"),
    ],
)
async def test_bad_picks_are_rejected(
    deps: GameDeps,
    storage: InMemoryStorage,
    realtime: RecordingRealtime,
    player_id,
    guess_index,
    message,
):
    game = await start(deps, realtime, in_guessing_phase())

    with pytest.raises(GameRuleError, match=message):
        await pick_winning_guess(deps, PickWinningGuess(game.id, player_id, guess_index))

    assert await storage.get_events(game.id) == []


async def test_the_guesses_can_only_be_judged_once(deps: GameDeps, realtime: RecordingRealtime):
    game = await start(deps, realtime, in_guessing_phase())
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", 0))

    with pytest.raises(GameRuleError, match="Guessing is over"):
        await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", 1))


async def test_judging_waits_for_the_script(deps: GameDeps, realtime: RecordingRealtime):
    game = await start(deps, realtime, waiting_for_prompt())

    with pytest.raises(GameRuleError, match="doesn't have its script yet"):
        await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", None))


# Guessing the personality and scoring


@pytest.mark.parametrize(
    ("winning_guess", "personality", "expected_changes"),
    [
        # Prompt guessed: +1 to the guessing team and +1 to the acting team.
        # Personality identified: +1 more to the acting team.
        (0, "noir", {"team-1": 2, "team-2": 1}),
        (0, "melodrama", {"team-1": 1, "team-2": 1}),
        (None, "noir", {"team-1": 1}),
        (None, "melodrama", {}),
    ],
    ids=["guessed+identified", "guessed-only", "identified-only", "neither"],
)
async def test_each_row_of_the_scoring_table(
    deps: GameDeps,
    storage: InMemoryStorage,
    realtime: RecordingRealtime,
    winning_guess: int | None,
    personality: str,
    expected_changes: dict[str, int],
):
    game = await start(deps, realtime, in_guessing_phase())

    game = await play_out(deps, game, winning_guess=winning_guess, personality=personality)

    totals = {
        "team-1": expected_changes.get("team-1", 0),
        "team-2": expected_changes.get("team-2", 0),
    }
    assert {team.id: team.score for team in game.teams} == totals
    current = game.rounds[0]
    assert current.round_score == expected_changes
    assert current.personality_guess == personality
    assert current.personality_correct is (personality == "noir")
    events = await storage.get_events(game.id)
    scores = next(e for e in events if isinstance(e, ScoresUpdated))
    completed = next(e for e in events if isinstance(e, RoundCompleted))
    assert scores.score_changes == expected_changes
    assert (completed.round_number, completed.final_scores) == (0, totals)


async def test_the_round_completes_and_the_turn_passes_to_the_next_team(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", 1))

    game = await guess_personality(deps, GuessPersonality(game.id, "player-2", "noir"))

    events = (await storage.get_events(game.id))[1:]
    assert [type(e) for e in events] == [
        PersonalityGuessSubmitted,
        PersonalityRevealed,
        ScoresUpdated,
        RoundCompleted,
        RoundStarted,
    ]
    started = events[-1]
    assert isinstance(started, RoundStarted)
    assert (started.round_number, started.acting_team_id) == (1, "team-2")
    assert game.current_round == 1
    assert game.get_acting_team().id == "team-2"
    assert [(r.round_number, r.acting_team_id, r.prompt) for r in game.rounds] == [
        (0, "team-1", "Superhero saves city from angry aliens"),
        (1, "team-2", None),
    ]
    for socket_id in ALL_SOCKETS:
        assert realtime.received_by(socket_id)[-5:] == events
    assert await load_game(deps, game.id) == game
    write_evidence(
        "guess-and-score/who-received-what.json",
        json.dumps(
            {
                socket_id: [e.event_type for e in realtime.received_by(socket_id)]
                for socket_id in sorted(ALL_SOCKETS)
            },
            indent=2,
        ),
    )
    write_evidence(
        "guess-and-score/events.jsonl",
        "".join(e.model_dump_json() + "\n" for e in await storage.get_events(game.id)),
    )


async def test_the_personality_is_revealed_to_the_room_after_the_acting_team_guesses(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())

    await play_out(deps, game, winning_guess=None, personality="melodrama")

    for socket_id in ALL_SOCKETS:
        received = realtime.received_by(socket_id)
        types = [type(e) for e in received]
        assert types.index(PersonalityGuessSubmitted) < types.index(PersonalityRevealed)
        (revealed,) = [e for e in received if isinstance(e, PersonalityRevealed)]
        assert (revealed.team_id, revealed.personality_id) == ("team-1", "noir")


async def test_the_reveal_can_be_kept_to_the_acting_team(
    deps: GameDeps, realtime: RecordingRealtime, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(guess_and_score, "REVEAL_PERSONALITY_TO_ROOM", False)
    game = await start(deps, realtime, in_guessing_phase())

    await play_out(deps, game, winning_guess=0, personality="noir")

    assert realtime.who_received(PersonalityRevealed) == ACTING_SOCKETS
    assert realtime.who_received(RoundCompleted) == ALL_SOCKETS


async def test_the_last_regular_round_hands_off_to_the_end_of_the_game(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_last_round_guessing_phase(rounds_per_team=1))
    # Team 2 (players 3 and 4) acts with melodrama in the last round; team 1 guessed.
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-3", 0))

    game = await guess_personality(deps, GuessPersonality(game.id, "player-4", "melodrama"))

    events = await storage.get_events(game.id)
    assert [type(e) for e in events][-3:] == [ScoresUpdated, RoundCompleted, GameCompleted]
    assert realtime.who_received(RoundStarted) == frozenset()
    completed, ended = events[-2:]
    assert isinstance(completed, RoundCompleted)
    assert completed.final_scores == {"team-1": 2, "team-2": 3}
    assert isinstance(ended, GameCompleted)
    assert (ended.final_scores, ended.winner_team_id) == (completed.final_scores, "team-2")
    assert game.status == GameStatus.FINISHED
    assert len(game.rounds) == 2
    assert await load_game(deps, game.id) == game


async def test_a_tie_after_the_last_round_is_played_off_round_by_round(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_last_round_guessing_phase(rounds_per_team=1))
    # Nobody gets team 2's prompt and it misses its personality: still 1-1.
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-3", None))
    game = await guess_personality(deps, GuessPersonality(game.id, "player-4", "noir"))

    assert game.tiebreaker is not None
    assert (game.tiebreaker.cycle, game.tiebreaker.team_ids) == (1, ["team-1", "team-2"])
    assert (game.current_round, game.rounds[-1].acting_team_id) == (2, "team-1")

    # Team 1 acts first in the tiebreaker: team 2 gets it, and team 1 names noir.
    await submit_prompt(deps, SubmitPrompt(game.id, "player-1", "Cat steals the moon"))
    await submit_guess(deps, SubmitGuess(game.id, "player-3", "A cat heist"))
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", 0))
    game = await guess_personality(deps, GuessPersonality(game.id, "player-2", "noir"))
    assert (game.status, game.current_round, game.rounds[-1].acting_team_id) == (
        GameStatus.PLAYING,
        3,
        "team-2",
    )

    # Team 2 acts next and scores nothing, so team 1 wins 3-2.
    await submit_prompt(deps, SubmitPrompt(game.id, "player-3", "Dog runs for mayor"))
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-3", None))
    game = await guess_personality(deps, GuessPersonality(game.id, "player-4", "noir"))

    ended = (await storage.get_events(game.id))[-1]
    assert isinstance(ended, GameCompleted)
    assert (ended.final_scores, ended.winner_team_id) == ({"team-1": 3, "team-2": 2}, "team-1")
    assert game.status == GameStatus.FINISHED
    assert realtime.broadcasts_to(game.room_code)[-1] == ended


@pytest.mark.parametrize(
    ("player_id", "personality", "message"),
    [
        ("player-3", "noir", "not on the acting team"),
        ("player-1", "pirate", "Unknown personality pirate"),
    ],
)
async def test_bad_personality_guesses_are_rejected(
    deps: GameDeps,
    storage: InMemoryStorage,
    realtime: RecordingRealtime,
    player_id,
    personality,
    message,
):
    game = await start(deps, realtime, in_guessing_phase())
    await pick_winning_guess(deps, PickWinningGuess(game.id, "player-1", None))

    with pytest.raises(GameRuleError, match=message):
        await guess_personality(deps, GuessPersonality(game.id, player_id, personality))

    assert [type(e) for e in await storage.get_events(game.id)] == [NoGuessAccepted]


async def test_the_personality_is_guessed_after_the_guesses_are_judged(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())

    with pytest.raises(GameRuleError, match="Pick the winning guess"):
        await guess_personality(deps, GuessPersonality(game.id, "player-1", "noir"))

    assert await storage.get_events(game.id) == []


async def test_a_whole_round_replays_to_the_saved_snapshot(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase(guesses=()))
    before = await load_game(deps, game.id)
    await submit_guess(deps, SubmitGuess(game.id, "player-3", "Aliens attack"))
    await submit_guess(deps, SubmitGuess(game.id, "player-4", "Hero saves city"))
    game = await play_out(deps, game, winning_guess=1, personality="noir")

    assert reduce(apply_event, await storage.get_events(game.id), before) == game
