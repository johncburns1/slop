"""What a player can do, and what they have received: the interface simulated players use.

``GameClient`` is everything a player's device can do in a game. Bots talk only
to it, so the same bot can later drive a real server over Socket.IO.
``InProcessClient`` implements it by calling the application use cases
directly, with the stand-ins from ``InProcessServer``; its inbox is whatever the
recording realtime stand-in delivered to its sockets while they were connected.

A client can ``disconnect`` and later ``rejoin_game`` on a new socket, and an
``InProcessServer`` on SQLite can ``restart``: it drops every connection and
comes back on the same database file with nothing kept in memory.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from slop.adapters.clock import FixedClock
from slop.adapters.ids import RandomIds, SequentialIds
from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.storage import InMemoryStorage, SQLiteStorage
from slop.adapters.websocket import RecordingRealtime
from slop.api.schemas import PlayerViewReply
from slop.application.assign_personality import AssignPersonality, assign_personality
from slop.application.create_game import CreateGame, create_game
from slop.application.engine import GameDeps
from slop.application.form_teams import (
    CreateTeam,
    JoinTeam,
    StartPersonalitySelection,
    create_team,
    join_team,
    start_personality_selection,
)
from slop.application.guess_and_score import (
    GuessPersonality,
    PickWinningGuess,
    SubmitGuess,
    guess_personality,
    pick_winning_guess,
    submit_guess,
)
from slop.application.join_game import JoinGame, join_game
from slop.application.rejoin_game import RejoinGame, rejoin_game
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain.events import GameEvent
from slop.domain.game import ContentTone
from tests.application.conftest import NOW


class GameClient(Protocol):
    """One player's connection to a game.

    Actions raise ``GameRuleError`` when the server rejects them. Results reach
    the player only as events in their inbox, as they would over the network.
    """

    @property
    def socket_id(self) -> str:
        """The connection this client receives events on, or last received them on."""
        ...

    @property
    def connected(self) -> bool: ...

    async def join_game(self, room_code: str, player_name: str) -> str:
        """Join the game in the lobby and return the player id it gave us."""
        ...

    async def create_team(self, team_name: str, color: str) -> None: ...

    async def join_team(self, team_id: str) -> None: ...

    async def start_personality_selection(self) -> None:
        """Host only: close the lobby."""
        ...

    async def assign_personality(self, personality_id: str) -> None:
        """Pick the personality the next team round the table performs with."""
        ...

    async def submit_prompt(self, prompt: str) -> None: ...

    async def submit_guess(self, guess: str) -> None: ...

    async def pick_winning_guess(self, guess_index: int | None) -> None:
        """Accept the guess at ``guess_index``, or None for nobody got it."""
        ...

    async def guess_personality(self, personality_id: str) -> None: ...

    async def disconnect(self) -> None:
        """Drop the connection. The player stays in the game but hears nothing until rejoining."""
        ...

    async def rejoin_game(self, room_code: str, player_id: str) -> PlayerViewReply:
        """Come back on a new connection as ``player_id`` and return the game as they may see it."""
        ...

    def inbox(self) -> list[GameEvent]:
        """Every event this player has received, on any connection, in order."""
        ...


Boot = Callable[[RecordingRealtime], GameDeps]
"""Builds a server's dependencies around a fresh realtime stand-in."""


class InProcessServer:
    """A game server made of the use cases and stand-ins, with nothing on the network."""

    def __init__(self, boot: Boot) -> None:
        self._boot = boot
        self._clients: list[InProcessClient] = []
        self.realtime = RecordingRealtime()
        self.deps = boot(self.realtime)

    @classmethod
    def with_stand_ins(cls) -> "InProcessServer":
        """In-memory storage, recording realtime, stand-in LLM, fixed clock, sequential ids."""
        return cls(
            lambda realtime: GameDeps(
                storage=InMemoryStorage(),
                realtime=realtime,
                clock=FixedClock(NOW),
                ids=SequentialIds(),
                llm=StandInLLMAdapter(),
            )
        )

    @classmethod
    def on_sqlite(cls, path: Path) -> "InProcessServer":
        """Like ``with_stand_ins``, but games are kept in the SQLite file at ``path``.

        Ids are random, as on the real server, so a restarted server never
        hands out an id the game already uses.
        """
        return cls(
            lambda realtime: GameDeps(
                storage=SQLiteStorage(path),
                realtime=realtime,
                clock=FixedClock(NOW),
                ids=RandomIds(),
                llm=StandInLLMAdapter(),
            )
        )

    async def restart(self) -> None:
        """Stop the server and start it again, as after a crash.

        Every connection drops, and the new server starts with only what its
        storage kept: nothing for in-memory storage, every game for SQLite.
        """
        for client in self._clients:
            client.dropped()
        self.realtime = RecordingRealtime()
        self.deps = self._boot(self.realtime)

    async def create_game(
        self, *, rounds_per_team: int = 1, content_tone: ContentTone = ContentTone.FAMILY
    ) -> str:
        """Create a game and return its room code."""
        command = CreateGame(content_tone=content_tone, rounds_per_team=rounds_per_team)
        return (await create_game(self.deps, command)).room_code

    def connect(self, socket_id: str) -> "InProcessClient":
        client = InProcessClient(self, socket_id)
        self._clients.append(client)
        return client


class InProcessClient:
    """``GameClient`` that calls the use cases directly.

    Each connection gets its own socket id: ``socket-1``, then ``socket-1.2``
    after the first rejoin, and so on. Once a connection drops, nothing sent
    to its socket counts as received.
    """

    def __init__(self, server: InProcessServer, socket_id: str) -> None:
        self._server = server
        self._first_socket_id = socket_id
        self._socket_id = socket_id
        self._connections = 1
        self._connected = True
        self._earlier: list[GameEvent] = []  # received on connections that have dropped
        self._game_id: str | None = None
        self._room_code: str | None = None
        self._player_id: str | None = None

    @property
    def socket_id(self) -> str:
        return self._socket_id

    @property
    def connected(self) -> bool:
        return self._connected

    async def join_game(self, room_code: str, player_name: str) -> str:
        self._check_connected()
        joined = await join_game(
            self._server.deps, JoinGame(room_code, player_name, self._socket_id)
        )
        self._game_id, self._player_id = joined.game.id, joined.player_id
        self._room_code = joined.game.room_code
        return joined.player_id

    async def create_team(self, team_name: str, color: str) -> None:
        game_id, player_id = self._ids()
        await create_team(self._server.deps, CreateTeam(game_id, player_id, team_name, color))

    async def join_team(self, team_id: str) -> None:
        await join_team(self._server.deps, JoinTeam(*self._ids(), team_id))

    async def start_personality_selection(self) -> None:
        await start_personality_selection(
            self._server.deps, StartPersonalitySelection(*self._ids())
        )

    async def assign_personality(self, personality_id: str) -> None:
        await assign_personality(self._server.deps, AssignPersonality(*self._ids(), personality_id))

    async def submit_prompt(self, prompt: str) -> None:
        await submit_prompt(self._server.deps, SubmitPrompt(*self._ids(), prompt))

    async def submit_guess(self, guess: str) -> None:
        await submit_guess(self._server.deps, SubmitGuess(*self._ids(), guess))

    async def pick_winning_guess(self, guess_index: int | None) -> None:
        await pick_winning_guess(self._server.deps, PickWinningGuess(*self._ids(), guess_index))

    async def guess_personality(self, personality_id: str) -> None:
        await guess_personality(self._server.deps, GuessPersonality(*self._ids(), personality_id))

    async def disconnect(self) -> None:
        """Drop the connection, as when a phone loses signal: the socket leaves the room."""
        if not self._connected:
            return
        self.dropped()
        if self._room_code is not None:
            await self._server.realtime.leave_room(self._socket_id, self._room_code)

    async def rejoin_game(self, room_code: str, player_id: str) -> PlayerViewReply:
        if self._connected:
            await self.disconnect()
        self._connections += 1
        self._socket_id = f"{self._first_socket_id}.{self._connections}"
        self._connected = True
        try:
            rejoined = await rejoin_game(
                self._server.deps, RejoinGame(room_code, player_id, self._socket_id)
            )
        except Exception:
            self.dropped()
            raise
        self._game_id, self._player_id = rejoined.game.id, player_id
        self._room_code = rejoined.game.room_code
        return PlayerViewReply.model_validate(rejoined.view)

    def dropped(self) -> None:
        """Note that the connection is gone, keeping what it received until now."""
        if self._connected:
            self._earlier = self.inbox()
            self._connected = False

    def inbox(self) -> list[GameEvent]:
        if not self._connected:
            return list(self._earlier)
        return self._earlier + self._server.realtime.received_by(self._socket_id)

    def _check_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("Not connected")

    def _ids(self) -> tuple[str, str]:
        self._check_connected()
        if self._game_id is None or self._player_id is None:
            raise RuntimeError("Join a game first")
        return self._game_id, self._player_id
