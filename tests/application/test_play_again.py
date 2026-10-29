"""Tests for the play again use case."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.assign_personality import AssignPersonality, assign_personality
from slop.application.engine import GameDeps, load_game
from slop.application.finish_or_continue import FinishOrContinue, finish_or_continue
from slop.application.play_again import PlayAgain, play_again
from slop.domain import Game, GameRestarted, GameStatus
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.builders import scored_after_last_round, tied_after_last_round


async def finished(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game, seat every player in its room, and let the game end."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return await finish_or_continue(deps, FinishOrContinue(game.id))


async def test_play_again_keeps_players_and_teams_and_resets_scores_and_personalities(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))
    assert game.status == GameStatus.FINISHED
    before = await storage.get_events(game.id)

    new_game = await play_again(deps, PlayAgain(game.id, "player-1"))

    assert (new_game.id, new_game.room_code) == (game.id, game.room_code)
    assert new_game.status == GameStatus.PERSONALITY_SELECTION
    assert new_game.players == game.players
    assert [(t.id, t.name, t.player_ids) for t in new_game.teams] == [
        (t.id, t.name, t.player_ids) for t in game.teams
    ]
    assert [(t.score, t.assigned_personality) for t in new_game.teams] == [(0, None), (0, None)]
    assert (new_game.rounds, new_game.current_round, new_game.tiebreaker) == ([], 0, None)
    (restarted,) = (await storage.get_events(game.id))[len(before) :]
    assert isinstance(restarted, GameRestarted)
    assert realtime.broadcasts_to(game.room_code)[-1] == restarted
    assert await load_game(deps, game.id) == new_game


async def test_the_new_game_starts_once_teams_pick_personalities_again(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))
    await play_again(deps, PlayAgain(game.id, "player-1"))

    await assign_personality(deps, AssignPersonality(game.id, "player-1", "absurdist"))
    game = await assign_personality(deps, AssignPersonality(game.id, "player-3", "noir"))

    assert game.status == GameStatus.PLAYING
    assert [(r.round_number, r.acting_team_id) for r in game.rounds] == [(0, "team-1")]
    assert [t.assigned_personality for t in game.teams] == ["noir", "absurdist"]


async def test_only_the_host_can_play_again(deps: GameDeps, realtime: RecordingRealtime):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))

    with pytest.raises(GameRuleError, match="host"):
        await play_again(deps, PlayAgain(game.id, "player-3"))


async def test_a_player_not_in_the_game_cannot_play_again(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await finished(deps, realtime, scored_after_last_round(scores=(4, 2)))

    with pytest.raises(GameRuleError, match="not in this game"):
        await play_again(deps, PlayAgain(game.id, "player-99"))


async def test_a_game_still_being_played_cannot_restart(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await finished(deps, realtime, tied_after_last_round())
    assert game.status == GameStatus.PLAYING  # a tiebreaker is under way

    with pytest.raises(GameRuleError, match="has not finished"):
        await play_again(deps, PlayAgain(game.id, "player-1"))


async def test_an_unknown_game_is_not_found(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await play_again(deps, PlayAgain("no-such-game", "player-1"))
