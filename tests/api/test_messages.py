"""Tests for the client messages, played by real Socket.IO clients on a running server."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from slop.adapters.clock import FixedClock
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import SocketIORealtime
from slop.api import create_app
from slop.api.app import EXPIRY_TASK
from slop.api.rate_limit import RateLimit
from slop.domain.events import GameEvent, GuessingEnded, ScriptReady
from slop.domain.game import GameStatus
from slop.domain.personalities import PERSONALITIES
from tests.socketio_clients import Listener, serving


@dataclass
class Table:
    """A running server, its storage, and connected players by name."""

    realtime: SocketIORealtime
    storage: InMemoryStorage
    url: str
    players: dict[str, Listener]

    async def connect(self, *names: str) -> None:
        for name in names:
            listener = Listener()
            await listener.connect(self.url)
            self.players[name] = listener

    async def send(self, name: str, message: str, payload: dict[str, Any] | None = None) -> Any:
        """Send a message from this player and return the server's ack."""
        return await self.players[name].client.call(message, payload or {}, timeout=5)

    async def received(self, name: str) -> list[GameEvent]:
        return await self.players[name].received(self.realtime)

    async def types(self, name: str) -> list[str]:
        return [event.event_type for event in await self.received(name)]

    async def errors(self, name: str) -> list[dict[str, Any]]:
        await self.received(name)  # flush, so every error sent so far has arrived
        return list(self.players[name].errors)


@asynccontextmanager
async def table(**app_options: Any) -> AsyncIterator[Table]:
    realtime, storage = SocketIORealtime(), InMemoryStorage()
    async with serving(create_app(realtime, storage=storage, **app_options)) as url:
        seated = Table(realtime, storage, url, {})
        try:
            yield seated
        finally:
            for listener in seated.players.values():
                await listener.client.disconnect()


async def lobby(t: Table, *names: str, **settings: Any) -> str:
    """The first player creates a game, then everyone joins it. Returns the room code."""
    await t.connect(*names)
    created = await t.send(names[0], "create_game", {"content_tone": "family", **settings})
    for name in names:
        joined = await t.send(
            name, "join_game", {"room_code": created["room_code"], "player_name": name}
        )
        assert joined["game_id"] == created["game_id"]
    return str(created["room_code"])


async def two_teams_with_personalities(t: Table, **settings: Any) -> str:
    """alice and bob are Red, carol and dave are Blue, and both have personalities.

    Red picks noir for Blue, and Blue picks melodrama for Red. Returns the room code.
    """
    room_code = await lobby(t, "alice", "bob", "carol", "dave", **settings)
    red = await t.send("alice", "create_team", {"team_name": "Red", "color": "#f00"})
    await t.send("bob", "join_team", {"team_id": red["team_id"]})
    blue = await t.send("carol", "create_team", {"team_name": "Blue", "color": "#00f"})
    await t.send("dave", "join_team", {"team_id": blue["team_id"]})
    await t.send("alice", "start_personality_selection")
    await t.send("alice", "assign_personality", {"personality_id": "noir"})
    await t.send("carol", "assign_personality", {"personality_id": "melodrama"})
    return room_code


async def test_players_create_join_form_teams_and_assign_personalities() -> None:
    """Every player hears the room's events, picks reach only the picking team,
    and a broken rule is reported to the player who broke it and no one else."""
    async with table() as t:
        await lobby(t, "alice", "bob", "carol", "dave")
        red = await t.send("alice", "create_team", {"team_name": "Red", "color": "#f00"})
        await t.send("bob", "join_team", {"team_id": red["team_id"]})
        blue = await t.send("carol", "create_team", {"team_name": "Blue", "color": "#00f"})
        await t.send("dave", "join_team", {"team_id": blue["team_id"]})

        error = await t.send("bob", "start_personality_selection")

        assert error == {
            "code": "rule_broken",
            "message": "Only the host can do that",
            "request": "start_personality_selection",
        }
        assert await t.errors("bob") == [error]
        for name in ("alice", "carol", "dave"):
            assert await t.errors(name) == []

        assert await t.send("alice", "start_personality_selection") is None
        await t.send("alice", "assign_personality", {"personality_id": "noir"})
        await t.send("carol", "assign_personality", {"personality_id": "melodrama"})

        teams = ["TeamFormed", "PlayerJoinedTeam", "PlayerJoinedTeam"] * 2
        red_picks = ["PersonalityAssigned", "PersonalityPicked", "PersonalityPicked"]
        blue_picks = ["PersonalityPicked", "PersonalityAssigned", "PersonalityPicked"]
        after_lobby = ["PersonalitySelectionStarted"]
        assert await t.types("alice") == [
            *["PlayerJoined"] * 4,
            *teams,
            *after_lobby,
            *red_picks,
            "RoundStarted",
        ]
        assert await t.types("bob") == [
            *["PlayerJoined"] * 3,
            *teams,
            *after_lobby,
            *red_picks,
            "RoundStarted",
        ]
        assert await t.types("carol") == [
            *["PlayerJoined"] * 2,
            *teams,
            *after_lobby,
            *blue_picks,
            "RoundStarted",
        ]
        assert await t.types("dave") == [
            "PlayerJoined",
            *teams,
            *after_lobby,
            *blue_picks,
            "RoundStarted",
        ]
        red_pick = next(e for e in await t.received("bob") if e.event_type == "PersonalityAssigned")
        assert red_pick.model_dump()["personality_id"] == "noir"


async def test_acting_team_plays_a_round_over_socketio() -> None:
    async with table() as t:
        await two_teams_with_personalities(t)

        await t.send("bob", "submit_prompt", {"prompt": "a haunted vending machine"})
        await t.send("carol", "submit_guess", {"guess": "possessed snack machine"})
        await t.send("alice", "pick_winning_guess", {"guess_index": 0})
        await t.send("bob", "guess_personality", {"personality_id": "melodrama"})

        script_for_actors = ["PromptSubmitted", "ScriptGenerated", "RoleAssigned", "RoleAssigned"]
        scoring = [
            "GuessSubmitted",
            "GuessAccepted",
            "PersonalityGuessSubmitted",
            "PersonalityRevealed",
            "PromptRevealed",
            "ScoresUpdated",
            "RoundCompleted",
            "RoundStarted",
        ]
        round_types = (await t.types("alice"))[-13:]
        assert round_types == [*script_for_actors, "ScriptReady", *scoring]
        carol_types = await t.types("carol")
        assert carol_types[carol_types.index("ScriptReady") :] == ["ScriptReady", *scoring]
        assert "ScriptGenerated" not in carol_types
        for name in t.players:
            assert await t.errors(name) == []


async def test_host_plays_again_once_the_game_is_over() -> None:
    async with table() as t:
        await two_teams_with_personalities(t, rounds_per_team=1)
        # Red is guessed and names its personality; Blue isn't guessed. Red wins 2-1.
        await t.send("bob", "submit_prompt", {"prompt": "a haunted vending machine"})
        await t.send("carol", "submit_guess", {"guess": "possessed snack machine"})
        await t.send("alice", "pick_winning_guess", {"guess_index": 0})
        await t.send("bob", "guess_personality", {"personality_id": "melodrama"})
        await t.send("dave", "submit_prompt", {"prompt": "penguins unionize"})
        await t.send("carol", "pick_winning_guess", {"guess_index": None})
        await t.send("dave", "guess_personality", {"personality_id": "absurdist"})
        assert (await t.types("alice"))[-2:] == ["GameCompleted", "AwardsGiven"]

        refused = await t.send("bob", "play_again")
        assert await t.send("alice", "play_again") is None

        assert refused["message"] == "Only the host can do that"
        for name in t.players:
            assert (await t.types(name))[-1] == "GameRestarted"


async def test_bad_payload_and_messages_before_joining_are_errors_to_the_sender() -> None:
    async with table() as t:
        await lobby(t, "alice")
        await t.connect("stranger")

        bad = await t.send("alice", "create_team", {"team_name": "Red"})
        not_joined = await t.send("stranger", "create_team", {"team_name": "Red", "color": "#f00"})
        no_game = await t.send("stranger", "join_game", {"room_code": "ZZZZ", "player_name": "S"})

        assert bad["code"] == "invalid_payload"
        assert bad["request"] == "create_team"
        assert not_joined["code"] == "not_in_game"
        assert no_game["code"] == "game_not_found"
        assert await t.errors("alice") == [bad]
        assert await t.errors("stranger") == [not_joined, no_game]


async def test_leaving_removes_the_player_but_disconnecting_does_not() -> None:
    async with table() as t:
        room_code = await lobby(t, "alice", "bob", "carol")

        assert await t.send("bob", "leave_game") is None
        await t.players.pop("carol").client.disconnect()
        after_leaving = await t.send("bob", "create_team", {"team_name": "Red", "color": "#f00"})

        assert after_leaving["code"] == "not_in_game"
        assert (await t.types("alice"))[-1] == "PlayerLeft"
        game = await t.storage.get_game_by_room_code(room_code)
        assert game is not None
        assert game.status == GameStatus.LOBBY
        assert [p.name for p in game.players] == ["alice", "carol"]


async def player_ids(t: Table, room_code: str) -> dict[str, str]:
    game = await t.storage.get_game_by_room_code(room_code)
    assert game is not None
    return {p.name: p.id for p in game.players}


async def reconnect(t: Table, name: str, room_code: str, player_id: str) -> Any:
    """Drop the player's connection, connect again, and rejoin. Returns the ack."""
    await t.players.pop(name).client.disconnect()
    await t.connect(name)
    return await t.send(name, "rejoin_game", {"room_code": room_code, "player_id": player_id})


async def test_players_reconnect_mid_round_and_see_only_what_they_may() -> None:
    async with table() as t:
        room_code = await two_teams_with_personalities(t)
        ids = await player_ids(t, room_code)
        await t.send("alice", "submit_prompt", {"prompt": "a haunted vending machine"})
        await t.send("carol", "submit_guess", {"guess": "possessed snack machine"})

        acting = await reconnect(t, "bob", room_code, ids["bob"])
        guessing = await reconnect(t, "dave", room_code, ids["dave"])

        assert acting["player_id"] == ids["bob"]
        assert acting["status"] == guessing["status"] == "playing"
        for view in (acting, guessing):
            assert view["current_round"]["phase"] == "guessing"
            assert [g["guess"] for g in view["current_round"]["guesses"]] == [
                "possessed snack machine"
            ]
            assert [team["personality_id"] for team in view["teams"]] == [None, None]
        assert acting["current_round"]["prompt"] == "a haunted vending machine"
        assert [r["player_id"] for r in acting["current_round"]["script"]["roles"]] == [
            ids["alice"],
            ids["bob"],
        ]
        assert acting["my_pick"]["personality_id"] == "noir"
        assert "melodrama" not in str(acting)  # Red's own personality
        assert guessing["current_round"]["prompt"] is None
        assert guessing["current_round"]["script"] is None
        assert "haunted" not in str(guessing)
        assert guessing["my_pick"]["personality_id"] == "melodrama"
        assert acting["awards"] == guessing["awards"] == []  # awards come once the game ends
        assert "noir" not in str(guessing)  # Blue's own personality
        assert (await t.types("alice"))[-2:] == ["PlayerReconnected"] * 2
        assert "PlayerJoined" not in await t.types("bob")

        # The rejoined players carry on, and private events reach their new connections.
        assert await t.send("bob", "pick_winning_guess", {"guess_index": 0}) is None
        await t.send("bob", "guess_personality", {"personality_id": "melodrama"})
        await t.send("dave", "submit_prompt", {"prompt": "penguins unionize"})
        assert "ScriptGenerated" in await t.types("dave")
        for name in t.players:
            assert await t.errors(name) == []


async def test_anyone_connected_can_list_the_personalities_without_their_system_prompts() -> None:
    async with table() as t:
        await t.connect("alice")

        reply = await t.send("alice", "list_personalities")

        assert reply["personalities"] == [
            {"id": p.id, "name": p.name, "description": p.description}
            for p in PERSONALITIES.values()
        ]
        assert await t.errors("alice") == []


async def test_rejoining_an_unknown_room_or_player_is_an_error_to_the_sender() -> None:
    async with table() as t:
        room_code = await lobby(t, "alice")
        await t.connect("stranger")

        no_game = await t.send("stranger", "rejoin_game", {"room_code": "ZZZZ", "player_id": "x"})
        no_player = await t.send(
            "stranger", "rejoin_game", {"room_code": room_code, "player_id": "x"}
        )
        still_out = await t.send("stranger", "create_team", {"team_name": "R", "color": "#f00"})

        assert no_game["code"] == "game_not_found"
        assert (no_player["code"], no_player["request"]) == ("rule_broken", "rejoin_game")
        assert still_out["code"] == "not_in_game"
        assert await t.errors("stranger") == [no_game, no_player, still_out]
        assert await t.errors("alice") == []


async def test_a_flooding_client_is_rate_limited_alone() -> None:
    """The clock stands still, so no tokens come back until the test moves it."""
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    async with table(clock=clock, rate_limit=RateLimit(per_second=10, burst=20)) as t:
        await t.connect("flooder")
        lookup = {"room_code": "ZZZZ", "player_name": "F"}

        flood = [await t.send("flooder", "join_game", lookup) for _ in range(25)]

        assert [reply["code"] for reply in flood] == ["game_not_found"] * 20 + ["rate_limited"] * 5
        assert flood[-1] == {
            "code": "rate_limited",
            "message": "Too many messages, slow down",
            "request": "join_game",
        }
        assert await t.errors("flooder") == flood
        room_code = await lobby(t, "alice")
        assert await t.send("alice", "create_team", {"team_name": "Red", "color": "#f00"})
        assert await t.errors("alice") == []
        assert (await t.types("alice"))[-1] == "PlayerJoinedTeam"
        still_flooding = await t.send("flooder", "join_game", {**lookup, "room_code": room_code})
        assert still_flooding["code"] == "rate_limited"
        assert await t.types("alice") == ["PlayerJoined", "TeamFormed", "PlayerJoinedTeam"]

        clock.advance(timedelta(seconds=1))
        joined = await t.send("flooder", "join_game", {**lookup, "room_code": room_code})
        assert "player_id" in joined


async def test_text_moderation_blocks_is_an_error_to_the_sender_only() -> None:
    """With the server's stand-in moderation, a family game refuses a mature name and guess."""
    async with table() as t:
        room_code = await lobby(t, "alice", "bob", "carol", "dave")
        await t.connect("eve")
        name = await t.send("eve", "join_game", {"room_code": room_code, "player_name": "Sexy Eve"})
        red = await t.send("alice", "create_team", {"team_name": "Red", "color": "#f00"})
        await t.send("bob", "join_team", {"team_id": red["team_id"]})
        blue = await t.send("carol", "create_team", {"team_name": "Blue", "color": "#00f"})
        await t.send("dave", "join_team", {"team_id": blue["team_id"]})
        await t.send("alice", "start_personality_selection")
        await t.send("alice", "assign_personality", {"personality_id": "noir"})
        await t.send("carol", "assign_personality", {"personality_id": "melodrama"})
        await t.send("bob", "submit_prompt", {"prompt": "a haunted vending machine"})

        guess = await t.send("carol", "submit_guess", {"guess": "a damn snack machine"})

        assert name == {
            "code": "content_blocked",
            "message": "That name isn't allowed in this game. Try something else.",
            "request": "join_game",
        }
        assert guess["code"] == "content_blocked"
        assert guess["request"] == "submit_guess"
        assert await t.errors("eve") == [name]
        assert await t.errors("carol") == [guess]
        for other in ("alice", "bob", "dave"):
            assert await t.errors(other) == []
            types = await t.types(other)
            assert types.count("PlayerJoined") <= 4
            assert "GuessSubmitted" not in types


async def test_the_server_deletes_expired_games_and_their_room_codes_stop_resolving() -> None:
    """The server sweeps for expired games every few milliseconds, on a clock the test moves."""
    clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
    options = {"clock": clock, "expire_every": timedelta(milliseconds=10)}
    async with table(**options) as t:
        old_room = await lobby(t, "alice")
        old_ids = await player_ids(t, old_room)
        old_game = await t.storage.get_game_by_room_code(old_room)
        assert old_game is not None
        clock.advance(timedelta(hours=2))
        await t.players.pop("alice").client.disconnect()
        new_room = await lobby(t, "bob")

        for _ in range(500):
            if await t.storage.get_snapshot(old_game.id) is None:
                break
            await asyncio.sleep(0.01)

        assert await t.storage.get_snapshot(old_game.id) is None
        assert await t.storage.get_events(old_game.id) == []
        await t.connect("alice")
        rejoin = {"room_code": old_room, "player_id": old_ids["alice"]}
        assert (await t.send("alice", "rejoin_game", rejoin))["code"] == "game_not_found"
        join = {"room_code": old_room, "player_name": "alice"}
        assert (await t.send("alice", "join_game", join))["code"] == "game_not_found"
        assert "player_id" in await t.send("alice", "join_game", {**join, "room_code": new_room})
        new_game = await t.storage.get_game_by_room_code(new_room)
        assert new_game is not None
        assert [p.name for p in new_game.players] == ["bob", "alice"]


async def test_the_expiry_sweep_stops_with_the_server() -> None:
    async with table(expire_every=timedelta(milliseconds=10)):
        assert [t for t in asyncio.all_tasks() if t.get_name() == EXPIRY_TASK]

    assert not [t for t in asyncio.all_tasks() if t.get_name() == EXPIRY_TASK]


async def test_time_running_out_moves_everyone_to_judging_over_the_wire() -> None:
    """The server's own timer closes guessing, and a late guess gets a friendly error."""
    async with table() as t:
        await two_teams_with_personalities(t, guess_timer_seconds=1)
        await t.send("alice", "submit_prompt", {"prompt": "a haunted vending machine"})
        carol_events = await t.received("carol")
        ready = next(e for e in carol_events if isinstance(e, ScriptReady))
        assert ready.guess_deadline is not None
        assert await t.send("carol", "submit_guess", {"guess": "cursed snacks"}) is None

        for _ in range(300):
            if any(isinstance(e, GuessingEnded) for e in await t.received("carol")):
                break
            await asyncio.sleep(0.01)

        assert any(isinstance(e, GuessingEnded) for e in await t.received("alice"))
        assert await t.send("dave", "submit_guess", {"guess": "too late"}) == {
            "code": "rule_broken",
            "message": "Guessing is over for this round",
            "request": "submit_guess",
        }
        assert await t.send("alice", "pick_winning_guess", {"guess_index": 0}) is None


async def test_the_acting_team_ends_guessing_early_over_the_wire() -> None:
    async with table() as t:
        await two_teams_with_personalities(t)
        await t.send("alice", "submit_prompt", {"prompt": "a haunted vending machine"})

        refused = await t.send("carol", "end_guessing")
        assert refused is not None and refused["code"] == "rule_broken"

        assert await t.send("bob", "end_guessing") is None

        heard = await t.received("carol")
        assert any(isinstance(e, GuessingEnded) for e in heard)
        game = await t.storage.get_snapshot(heard[-1].game_id)
        assert game is not None and game.rounds[0].guessing_ended
