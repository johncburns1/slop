"""Tests for the client messages, played by real Socket.IO clients on a running server."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import SocketIORealtime
from slop.api import create_app
from slop.domain.events import GameEvent
from slop.domain.game import GameStatus
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
async def table() -> AsyncIterator[Table]:
    realtime, storage = SocketIORealtime(), InMemoryStorage()
    async with serving(create_app(realtime, storage=storage)) as url:
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


async def two_teams_with_personalities(t: Table, **settings: Any) -> None:
    """alice and bob are Red, carol and dave are Blue, and both have personalities.

    Red picks noir for Blue, and Blue picks melodrama for Red.
    """
    await lobby(t, "alice", "bob", "carol", "dave", **settings)
    red = await t.send("alice", "create_team", {"team_name": "Red", "color": "#f00"})
    await t.send("bob", "join_team", {"team_id": red["team_id"]})
    blue = await t.send("carol", "create_team", {"team_name": "Blue", "color": "#00f"})
    await t.send("dave", "join_team", {"team_id": blue["team_id"]})
    await t.send("alice", "start_personality_selection")
    await t.send("alice", "assign_personality", {"personality_id": "noir"})
    await t.send("carol", "assign_personality", {"personality_id": "melodrama"})


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
            "ScoresUpdated",
            "RoundCompleted",
            "RoundStarted",
        ]
        round_types = (await t.types("alice"))[-12:]
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
        assert (await t.types("alice"))[-1] == "GameCompleted"

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
