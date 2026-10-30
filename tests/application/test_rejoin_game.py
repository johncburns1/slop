"""Tests for a player reconnecting to a game they are already in."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, load_game
from slop.application.guess_and_score import SubmitGuess, submit_guess
from slop.application.rejoin_game import RejoinGame, rejoin_game
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain import Game, PlayerJoined, PlayerReconnected, RoleAssigned
from slop.domain.errors import GameNotFoundError, GameRuleError
from tests.builders import waiting_for_prompt

PROMPT = "a haunted vending machine"


async def mid_round(deps: GameDeps, realtime: RecordingRealtime) -> Game:
    """Team 1 (players 1 and 2) has its script and team 2 (players 3 and 4) has guessed."""
    game = waiting_for_prompt()
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    await submit_prompt(deps, SubmitPrompt(game.id, "player-1", PROMPT))
    return await submit_guess(deps, SubmitGuess(game.id, "player-3", "a cursed snack machine"))


async def test_an_acting_player_rejoins_mid_round_and_gets_the_script(
    deps: GameDeps, realtime: RecordingRealtime, storage: InMemoryStorage
):
    game = await mid_round(deps, realtime)

    rejoined = await rejoin_game(deps, RejoinGame(" abcd ", "player-2", "socket-2b"))

    view = rejoined.view
    assert (view.game_id, view.player_id, view.team_id) == (game.id, "player-2", "team-1")
    assert view.current_round is not None
    assert view.current_round.phase == "guessing"
    assert view.current_round.prompt == PROMPT
    assert view.current_round.script is not None
    assert [r.player_id for r in view.current_round.script.roles] == ["player-1", "player-2"]
    assert [g.guess for g in view.current_round.guesses] == ["a cursed snack machine"]
    assert "noir" not in repr(view)  # team 1's own personality, still secret from it
    assert rejoined.game.get_player("player-2").socket_id == "socket-2b"
    assert await load_game(deps, game.id) == rejoined.game
    assert realtime.members_of(game.room_code) >= {"socket-2b"}
    events = await storage.get_events(game.id)
    assert isinstance(events[-1], PlayerReconnected)
    assert not any(isinstance(e, PlayerJoined) for e in events)


async def test_a_guessing_player_rejoins_mid_round_without_the_script(
    deps: GameDeps, realtime: RecordingRealtime
):
    await mid_round(deps, realtime)

    view = (await rejoin_game(deps, RejoinGame("ABCD", "player-4", "socket-4b"))).view

    assert view.current_round is not None
    assert (view.current_round.acting_team_id, view.current_round.phase) == ("team-1", "guessing")
    assert view.current_round.prompt is None
    assert view.current_round.script is None
    assert PROMPT not in repr(view)
    assert "melodrama" not in repr(view)  # team 2's own personality
    assert view.my_pick is not None
    assert (view.my_pick.team_id, view.my_pick.personality_id) == ("team-1", "noir")


async def test_the_room_hears_the_player_is_back_on_their_new_socket(
    deps: GameDeps, realtime: RecordingRealtime
):
    await mid_round(deps, realtime)

    await rejoin_game(deps, RejoinGame("ABCD", "player-4", "socket-4b"))

    assert realtime.who_received(PlayerReconnected) >= {"socket-1", "socket-3", "socket-4b"}
    (event,) = [e for e in realtime.received_by("socket-4b") if isinstance(e, PlayerReconnected)]
    assert (event.player_id, event.socket_id) == ("player-4", "socket-4b")


async def test_private_events_follow_the_player_to_their_new_socket(
    deps: GameDeps, realtime: RecordingRealtime
):
    game = waiting_for_prompt()
    await deps.storage.save_snapshot(game)

    await rejoin_game(deps, RejoinGame("ABCD", "player-2", "socket-2b"))
    await submit_prompt(deps, SubmitPrompt(game.id, "player-1", PROMPT))

    assert "socket-2b" in realtime.who_received(RoleAssigned)
    assert "socket-2" not in realtime.who_received(RoleAssigned)


async def test_an_unknown_room_code_is_rejected(deps: GameDeps, realtime: RecordingRealtime):
    with pytest.raises(GameNotFoundError, match="ZZZZ"):
        await rejoin_game(deps, RejoinGame("ZZZZ", "player-1", "socket-x"))

    assert realtime.rooms_of("socket-x") == frozenset()


async def test_an_unknown_player_is_rejected_without_emitting_anything(
    deps: GameDeps, realtime: RecordingRealtime, storage: InMemoryStorage
):
    game = await mid_round(deps, realtime)
    before = await storage.get_events(game.id)

    with pytest.raises(GameRuleError, match="player-9"):
        await rejoin_game(deps, RejoinGame("ABCD", "player-9", "socket-x"))

    assert await storage.get_events(game.id) == before
    assert realtime.rooms_of("socket-x") == frozenset()
