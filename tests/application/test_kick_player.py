"""Tests for the host removing a player from the game."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.assign_personality import AssignPersonality, assign_personality
from slop.application.engine import GameDeps, load_game
from slop.application.join_game import JoinGame, join_game
from slop.application.kick_player import KickPlayer, kick_player
from slop.application.rejoin_game import RejoinGame, rejoin_game
from slop.application.restart_game import RestartGame, restart_game
from slop.application.skip_turn import SkipTurn, skip_turn
from slop.domain import (
    AwardsGiven,
    Game,
    GameCompleted,
    GameStatus,
    PlayerKicked,
    RemovedFromGame,
    Round,
    RoundCompleted,
    RoundStarted,
)
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.builders import (
    in_guessing_phase,
    lobby_with_two_teams,
    scored_after_last_round,
    selecting_personalities,
)


async def seated(deps: GameDeps, realtime: RecordingRealtime, game: Game) -> Game:
    """Store the game and put every player's socket in its room."""
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return game


def three_teams_mid_round() -> Game:
    """Three teams of one with personalities; team 2 (player-2) is acting in round 0.

    player-1, on team 1, is the host.
    """
    game = scored_after_last_round(scores=(0, 0, 0), players_per_team=1)
    game.rounds = [Round(id="round-0", round_number=0, acting_team_id="team-2")]
    game.current_round = 0
    return game


async def test_the_host_removes_a_player_in_the_lobby_and_everyone_hears(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, lobby_with_two_teams())

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-3"))

    assert [p.id for p in after.players] == ["player-1", "player-2", "player-4"]
    assert after.get_team("team-2").player_ids == ["player-4"]
    assert after.kicked_player_ids == ["player-3"]
    assert await load_game(deps, game.id) == after
    assert [type(e) for e in (await storage.get_events(game.id))] == [
        RemovedFromGame,
        PlayerKicked,
    ]
    assert realtime.who_received(RemovedFromGame) == {"socket-3"}
    assert realtime.who_received(PlayerKicked) == {f"socket-{n}" for n in range(1, 5)}
    assert [type(e) for e in realtime.received_by("socket-3")] == [RemovedFromGame, PlayerKicked]
    assert realtime.members_of(game.room_code) == {"socket-1", "socket-2", "socket-4"}


async def test_a_player_removed_in_the_lobby_can_join_again_as_someone_new(deps: GameDeps):
    game = lobby_with_two_teams()
    await deps.storage.save_snapshot(game)
    await kick_player(deps, KickPlayer(game.id, "player-1", "player-3"))

    again = await join_game(deps, JoinGame(game.room_code, "Player 3b", "socket-3b"))

    assert again.player_id != "player-3"
    assert "Player 3b" in [p.name for p in again.game.players]


async def test_a_removed_player_cannot_rejoin(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, in_guessing_phase())
    await kick_player(deps, KickPlayer(game.id, "player-1", "player-3"))
    before = await storage.get_events(game.id)

    with pytest.raises(GameRuleError, match="removed you from this game"):
        await rejoin_game(deps, RejoinGame(game.room_code, "player-3", "socket-3b"))

    assert await storage.get_events(game.id) == before
    assert realtime.rooms_of("socket-3b") == frozenset()


async def test_an_actor_removed_mid_round_loses_their_role_and_the_round_goes_on(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, in_guessing_phase())
    roles_before = dict(game.rounds[0].role_assignments)

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-2"))

    current = after.rounds[0]
    assert current.role_assignments == {"player-1": roles_before["player-1"]}
    assert current.prompt_guesses == game.rounds[0].prompt_guesses
    assert after.current_round == 0
    assert after.status == GameStatus.PLAYING
    assert realtime.who_received(RoundCompleted) == frozenset()


async def test_a_guesser_removed_mid_round_leaves_the_round_going_on(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, in_guessing_phase())

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-4"))

    assert after.get_team("team-2").player_ids == ["player-3"]
    assert after.rounds[0].guessing_open
    assert after.current_round == 0
    assert realtime.who_received(RoundCompleted) == frozenset()


async def test_emptying_the_acting_team_ends_its_round_without_points_and_passes_the_turn(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, three_teams_mid_round())

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-2"))

    events = (await storage.get_events(game.id))[2:]
    assert [type(e) for e in events] == [RoundCompleted, RoundStarted]
    assert isinstance(events[0], RoundCompleted)
    assert events[0].final_scores == {"team-1": 0, "team-2": 0, "team-3": 0}
    assert after.current_round == 1
    assert after.rounds[-1].acting_team_id == "team-3"
    assert after.teams_in_play() == [after.get_team("team-1"), after.get_team("team-3")]
    assert "socket-2" not in realtime.who_received(RoundStarted)


async def test_a_team_left_empty_gets_no_more_turns(deps: GameDeps, realtime: RecordingRealtime):
    game = await seated(deps, realtime, three_teams_mid_round())

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-3"))

    assert after.current_round == 0  # team 2's round goes on
    assert after.get_team("team-3").score == 0  # and team 3 stays on the scoreboard
    assert [t.id for t in after.teams_in_play()] == ["team-1", "team-2"]


async def test_fewer_than_two_teams_with_players_ends_the_game_normally(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = in_guessing_phase()
    game.get_team("team-2").score = 2
    game = await seated(deps, realtime, game)
    await kick_player(deps, KickPlayer(game.id, "player-1", "player-3"))

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-4"))

    assert after.status == GameStatus.FINISHED
    events = await storage.get_events(game.id)
    assert [type(e) for e in events[-3:]] == [RoundCompleted, GameCompleted, AwardsGiven]
    completed = events[-2]
    assert isinstance(completed, GameCompleted)
    assert completed.final_scores == {"team-1": 0, "team-2": 2}
    assert completed.winner_team_id == "team-1"
    assert after.awards


async def test_emptying_a_team_while_picking_personalities_re_forms_the_ring(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, selecting_personalities(num_teams=3, players_per_team=1))
    # Team 1 picks for team 2, and team 3 for team 1, so only team 2's pick for team 3 is left.
    await assign_personality(deps, AssignPersonality(game.id, "player-1", "noir"))
    await assign_personality(deps, AssignPersonality(game.id, "player-3", "melodrama"))

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-3"))

    # Without team 3, team 2's pick is the one for team 1, which it already has.
    assert after.status == GameStatus.PLAYING
    assert after.rounds[-1].acting_team_id == "team-1"
    assert isinstance((await storage.get_events(game.id))[-1], RoundStarted)


async def test_one_team_left_while_picking_personalities_ends_the_game(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, selecting_personalities(players_per_team=1))

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-2"))

    assert after.status == GameStatus.FINISHED
    assert GameCompleted in [type(e) for e in await storage.get_events(game.id)]


async def test_a_player_can_be_removed_once_the_game_has_finished(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = scored_after_last_round(scores=(1, 2))
    game.finish()
    game = await seated(deps, realtime, game)

    after = await kick_player(deps, KickPlayer(game.id, "player-1", "player-4"))

    assert after.status == GameStatus.FINISHED
    assert [p.id for p in after.players] == ["player-1", "player-2", "player-3"]


async def test_only_the_host_can_remove_players(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, lobby_with_two_teams())

    with pytest.raises(GameRuleError, match="Only the host"):
        await kick_player(deps, KickPlayer(game.id, "player-2", "player-3"))

    assert await storage.get_events(game.id) == []
    assert realtime.who_received(PlayerKicked) == frozenset()


async def test_the_host_cannot_remove_themself(deps: GameDeps, storage: InMemoryStorage):
    game = lobby_with_two_teams()
    await storage.save_snapshot(game)

    with pytest.raises(GameRuleError, match="can't remove yourself"):
        await kick_player(deps, KickPlayer(game.id, "player-1", "player-1"))


async def test_removing_someone_not_in_the_game_is_rejected(
    deps: GameDeps, storage: InMemoryStorage
):
    game = lobby_with_two_teams()
    await storage.save_snapshot(game)

    with pytest.raises(GameRuleError, match="not in this game"):
        await kick_player(deps, KickPlayer(game.id, "player-1", "player-9"))
    with pytest.raises(GameRuleError, match="not in this game"):
        await kick_player(deps, KickPlayer(game.id, "player-9", "player-2"))


async def test_an_unknown_game_is_not_found(deps: GameDeps):
    with pytest.raises(GameNotFoundError):
        await kick_player(deps, KickPlayer("missing", "player-1", "player-2"))


async def test_a_player_removed_mid_round_stays_gone_after_the_host_restarts(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = await seated(deps, realtime, in_guessing_phase())
    await kick_player(deps, KickPlayer(game.id, "player-1", "player-4"))

    after = await restart_game(deps, RestartGame(game.id, "player-1"))

    assert after.status == GameStatus.LOBBY
    assert [p.id for p in after.players] == ["player-1", "player-2", "player-3"]
    assert after.get_team("team-2").player_ids == ["player-3"]
    with pytest.raises(GameRuleError, match="removed you"):
        await rejoin_game(deps, RejoinGame(game.room_code, "player-4", "socket-4b"))


async def test_a_turn_skipped_after_a_team_dropped_out_passes_to_a_team_still_playing(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = three_teams_mid_round()  # team 2 acting, waiting for its prompt
    game = await seated(deps, realtime, game)
    await kick_player(deps, KickPlayer(game.id, "player-1", "player-3"))  # team 3 drops out

    after = await skip_turn(deps, SkipTurn(game.id, "player-1"))

    assert after.rounds[-1].acting_team_id == "team-1"
