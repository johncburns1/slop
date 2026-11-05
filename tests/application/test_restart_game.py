"""Tests for the host restarting the game back to the lobby, at any time."""

from datetime import timedelta

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.assign_personality import AssignPersonality, assign_personality
from slop.application.engine import GameDeps, load_game
from slop.application.form_teams import JoinTeam, join_team
from slop.application.guess_timers import GuessTimers
from slop.application.restart_game import RestartGame, restart_game
from slop.domain import Game, GameReset, GameStatus, GuessingEnded
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.application.test_guess_timers import GUESS_TIMER, ManualSleep, guessing_open, settle
from tests.application.test_play_again import finished
from tests.builders import lobby_with_two_teams, scored_after_last_round, selecting_personalities


async def seated(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game and put every player's socket in its room."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return game


def assert_back_in_the_lobby(before: Game, after: Game) -> None:
    """Same game, players, and teams; nothing left of the game that was under way."""
    assert (after.id, after.room_code, after.status) == (
        before.id,
        before.room_code,
        GameStatus.LOBBY,
    )
    assert after.players == before.players
    assert [(t.id, t.name, t.color, t.player_ids) for t in after.teams] == [
        (t.id, t.name, t.color, t.player_ids) for t in before.teams
    ]
    assert [(t.score, t.assigned_personality, t.personality_assigned_by) for t in after.teams] == [
        (0, None, None) for _ in before.teams
    ]
    assert (after.rounds, after.current_round, after.tiebreaker, after.awards) == ([], 0, None, [])


async def test_restart_during_personality_selection_goes_back_to_the_lobby(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, selecting_personalities())
    game = await assign_personality(deps, AssignPersonality(game.id, "player-1", "noir"))
    assert game.teams[1].assigned_personality == "noir"

    after = await restart_game(deps, RestartGame(game.id, "player-1"))

    assert_back_in_the_lobby(game, after)
    reset = (await storage.get_events(game.id))[-1]
    assert isinstance(reset, GameReset)
    assert realtime.broadcasts_to(game.room_code)[-1] == reset
    assert await load_game(deps, game.id) == after


async def test_restart_mid_round_cancels_the_running_guess_timer(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime, clock: FixedClock
):
    sleep = ManualSleep(clock)
    game = await guessing_open(deps, realtime)
    timers = GuessTimers(deps, sleep=sleep)
    timers.track(game)
    await settle()
    assert timers.running == 1

    after = await restart_game(deps, RestartGame(game.id, "player-1"))
    timers.track(after)
    await settle()

    assert timers.running == 0
    assert_back_in_the_lobby(game, after)
    await sleep.advance(GUESS_TIMER + timedelta(seconds=1))
    assert not any(isinstance(e, GuessingEnded) for e in await storage.get_events(game.id))
    await timers.stop()


async def test_restart_after_the_game_finished_clears_scores_and_awards(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))
    assert game.status == GameStatus.FINISHED and game.awards

    after = await restart_game(deps, RestartGame(game.id, "player-1"))

    assert_back_in_the_lobby(game, after)


async def test_after_a_restart_the_group_can_change_teams_and_start_again(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))
    await restart_game(deps, RestartGame(game.id, "player-1"))

    game = await join_team(deps, JoinTeam(game.id, "player-2", "team-2"))

    assert game.status == GameStatus.LOBBY
    assert game.get_player("player-2").team_id == "team-2"


async def test_only_the_host_can_restart(deps: GameDeps, realtime: RecordingRealtime):
    game = await seated(deps, realtime, selecting_personalities())

    with pytest.raises(GameRuleError, match="Only the host"):
        await restart_game(deps, RestartGame(game.id, "player-3"))
    assert (await load_game(deps, game.id)).status == GameStatus.PERSONALITY_SELECTION


async def test_a_player_not_in_the_game_cannot_restart(deps: GameDeps, realtime: RecordingRealtime):
    game = await seated(deps, realtime, selecting_personalities())

    with pytest.raises(GameRuleError, match="not in this game"):
        await restart_game(deps, RestartGame(game.id, "player-99"))


async def test_a_game_still_in_the_lobby_cannot_restart(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="already in the lobby"):
        await restart_game(deps, RestartGame(game.id, "player-1"))


async def test_an_unknown_game_is_not_found(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await restart_game(deps, RestartGame("no-such-game", "player-1"))
