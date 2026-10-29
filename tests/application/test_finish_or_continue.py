"""Tests for the finish or continue use case: what happens once a round is over."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, commit, load_game
from slop.application.finish_or_continue import FinishOrContinue, finish_or_continue
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain import (
    Game,
    GameCompleted,
    GameStatus,
    RoundCompleted,
    RoundStarted,
    ScoresUpdated,
    TiebreakerStarted,
)
from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.domain.game_end import MAX_TIEBREAKER_CYCLES
from tests.builders import in_guessing_phase, scored_after_last_round, tied_after_last_round
from tests.evidence import write_evidence


async def start(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game and put every player's socket in its room."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return game


async def complete_round(deps: GameDeps, game: Game, points: dict[str, int]) -> Game:
    """Score the current round with ``points`` and complete it, as scoring will."""
    totals = {team.id: team.score + points.get(team.id, 0) for team in game.teams}
    return await commit(
        deps,
        game,
        [
            ScoresUpdated(game_id=game.id, round_number=game.current_round, score_changes=points),
            RoundCompleted(game_id=game.id, round_number=game.current_round, final_scores=totals),
        ],
    )


async def play_out(
    deps: GameDeps, game: Game, points_by_round: list[dict[str, int]]
) -> tuple[Game, list[str]]:
    """Complete one round per entry in ``points_by_round``, calling the use case after each.

    Returns the game and the acting team of each round played.
    """
    acting: list[str] = []
    for points in points_by_round:
        acting.append(game.rounds[-1].acting_team_id)
        game = await complete_round(deps, game, points)
        game = await finish_or_continue(deps, FinishOrContinue(game.id))
    return game, acting


def broadcast(realtime: RecordingRealtime, game: Game) -> list[type]:
    return [type(e) for e in realtime.broadcasts_to(game.room_code)]


async def test_after_a_regular_round_the_next_team_starts_the_next_round(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())
    game = await complete_round(deps, game, {"team-2": 1, "team-1": 1})

    game = await finish_or_continue(deps, FinishOrContinue(game.id))

    assert (game.status, game.current_round) == (GameStatus.PLAYING, 1)
    assert game.rounds[-1].acting_team_id == "team-2"
    assert broadcast(realtime, game)[-1] is RoundStarted
    assert await load_game(deps, game.id) == game


async def test_a_clear_winner_after_the_last_round_ends_the_game(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, scored_after_last_round(scores=(4, 2)))

    game = await finish_or_continue(deps, FinishOrContinue(game.id))

    assert game.status == GameStatus.FINISHED
    assert game.tiebreaker is None
    (completed,) = await storage.get_events(game.id)
    assert isinstance(completed, GameCompleted)
    assert (completed.final_scores, completed.winner_team_id) == (
        {"team-1": 4, "team-2": 2},
        "team-1",
    )
    assert realtime.broadcasts_to(game.room_code) == [completed]
    assert await load_game(deps, game.id) == game


async def test_a_tie_is_broken_by_a_tiebreaker_cycle_and_the_tied_team_can_play_it(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, tied_after_last_round())
    first_tiebreaker_round = game.current_round

    game = await finish_or_continue(deps, FinishOrContinue(game.id))

    started, round_started = await storage.get_events(game.id)
    assert isinstance(started, TiebreakerStarted)
    assert (started.cycle, started.team_ids, started.first_round) == (
        1,
        ["team-1", "team-2"],
        first_tiebreaker_round,
    )
    assert isinstance(round_started, RoundStarted)
    assert (round_started.round_number, round_started.acting_team_id) == (
        first_tiebreaker_round,
        "team-1",
    )
    # The tiebreaker round is an ordinary round to the acting team.
    game = await submit_prompt(deps, SubmitPrompt(game.id, "player-1", "Cat steals the moon"))
    assert game.rounds[-1].script is not None

    # Team 1 scores nothing; team 2 names its personality and wins.
    game, acting = await play_out(deps, game, [{}, {"team-2": 1}])

    assert acting == ["team-1", "team-2"]
    assert game.status == GameStatus.FINISHED
    completed = (await storage.get_events(game.id))[-1]
    assert isinstance(completed, GameCompleted)
    assert completed.winner_team_id == "team-2"
    assert completed.final_scores == {"team-1": 6, "team-2": 7}
    events = await storage.get_events(game.id)
    write_evidence(
        "finish-or-continue/tiebreaker-events.jsonl",
        "".join(e.model_dump_json() + "\n" for e in events),
    )


async def test_only_the_teams_tied_for_first_act_in_the_tiebreaker(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, scored_after_last_round(scores=(2, 5, 5)))

    game = await finish_or_continue(deps, FinishOrContinue(game.id))
    assert game.tiebreaker is not None
    assert game.tiebreaker.team_ids == ["team-2", "team-3"]
    # Team 1 guesses team 3's prompt, but only the tied teams can win.
    game, acting = await play_out(deps, game, [{}, {"team-1": 1, "team-3": 1}])

    assert acting == ["team-2", "team-3"]
    completed = (await storage.get_events(game.id))[-1]
    assert isinstance(completed, GameCompleted)
    assert completed.winner_team_id == "team-3"


async def test_a_tie_that_survives_every_tiebreaker_cycle_is_a_draw(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, tied_after_last_round())

    game = await finish_or_continue(deps, FinishOrContinue(game.id))
    game, acting = await play_out(deps, game, [{}] * (2 * MAX_TIEBREAKER_CYCLES))

    assert acting == ["team-1", "team-2"] * MAX_TIEBREAKER_CYCLES
    events = await storage.get_events(game.id)
    cycles = [e.cycle for e in events if isinstance(e, TiebreakerStarted)]
    assert cycles == list(range(1, MAX_TIEBREAKER_CYCLES + 1))
    assert game.status == GameStatus.FINISHED
    completed = events[-1]
    assert isinstance(completed, GameCompleted)
    assert completed.winner_team_id is None
    assert completed.final_scores == {"team-1": 6, "team-2": 6}
    assert broadcast(realtime, game)[-1] is GameCompleted
    write_evidence(
        "finish-or-continue/draw-events.jsonl",
        "".join(e.model_dump_json() + "\n" for e in events),
    )


async def test_a_round_still_in_play_cannot_be_moved_past(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await start(deps, realtime, in_guessing_phase())

    with pytest.raises(GameRuleError, match="still in play"):
        await finish_or_continue(deps, FinishOrContinue(game.id))

    assert await storage.get_events(game.id) == []


async def test_a_finished_game_does_not_continue(deps: GameDeps, realtime: RecordingRealtime):
    game = await start(deps, realtime, scored_after_last_round(scores=(4, 2)))
    await finish_or_continue(deps, FinishOrContinue(game.id))

    with pytest.raises(GameRuleError, match="not being played"):
        await finish_or_continue(deps, FinishOrContinue(game.id))


async def test_an_unknown_game_is_not_found(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await finish_or_continue(deps, FinishOrContinue("no-such-game"))
