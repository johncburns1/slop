"""Reusable contract tests for RealtimePort adapters.

The port only sends; it has no way to ask what a client received. So besides
the adapter, each subclass supplies a `received` fixture that reports what a
socket has been delivered so far, in order. For the recording stand-in that
reads its log; for a real WebSocket adapter it would read from connected test
clients:

    class TestSocketIORealtime(RealtimePortContract):
        @pytest.fixture
        def realtime(self, server) -> RealtimePort:
            return SocketIORealtime(server)

        @pytest.fixture
        def received(self, clients) -> Received:
            return clients.received_by

This module is not named `test_*.py`, so pytest only collects the contract
through those subclasses.
"""

from collections.abc import Awaitable, Callable

import pytest

from slop.domain import GameCreated, RoundStarted, ScriptGenerated
from slop.domain.events import GameEvent
from slop.ports import RealtimePort

Received = Callable[[str], Awaitable[list[GameEvent]]]


def make_game_created(game_id: str = "game-1", room_code: str = "ABCD") -> GameCreated:
    return GameCreated(
        game_id=game_id,
        room_code=room_code,
        content_tone="family",
        max_players=12,
        rounds_per_team=3,
    )


def make_round_started(round_number: int = 1) -> RoundStarted:
    return RoundStarted(game_id="game-1", round_number=round_number, acting_team_id="team-1")


def make_script_generated() -> ScriptGenerated:
    return ScriptGenerated(
        game_id="game-1",
        round_number=1,
        script_content="To be or not to be.",
        personality_id="shakespeare",
        roles=[{"name": "Hamlet", "description": "A brooding prince"}],
        word_count=6,
        estimated_duration=3,
    )


class RealtimePortContract:
    """Behavior every RealtimePort adapter must provide."""

    @pytest.fixture
    def realtime(self) -> RealtimePort:
        """Return a fresh adapter with no rooms. Subclasses must override this."""
        raise NotImplementedError("Override the `realtime` fixture in the adapter's test class")

    @pytest.fixture
    def received(self) -> Received:
        """Return what a socket has received so far. Subclasses must override this."""
        raise NotImplementedError("Override the `received` fixture in the adapter's test class")

    # Direct messages

    async def test_a_new_socket_has_received_nothing(self, received: Received) -> None:
        assert await received("socket-1") == []

    async def test_message_to_a_player_reaches_only_that_player(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.join_room("socket-1", "ABCD")
        await realtime.join_room("socket-2", "ABCD")
        script = make_script_generated()

        await realtime.send_to_player("socket-1", script)

        assert await received("socket-1") == [script]
        assert await received("socket-2") == []

    async def test_message_to_a_player_does_not_need_a_room(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        event = make_round_started()

        await realtime.send_to_player("socket-1", event)

        assert await received("socket-1") == [event]

    # Room broadcasts

    async def test_broadcast_reaches_everyone_in_the_room(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        for socket_id in ("socket-1", "socket-2", "socket-3"):
            await realtime.join_room(socket_id, "ABCD")
        event = make_game_created()

        await realtime.broadcast_to_room("ABCD", event)

        for socket_id in ("socket-1", "socket-2", "socket-3"):
            assert await received(socket_id) == [event]

    async def test_broadcast_skips_players_outside_the_room(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.join_room("socket-1", "ABCD")
        await realtime.join_room("socket-2", "WXYZ")

        await realtime.broadcast_to_room("ABCD", make_game_created())

        assert await received("socket-2") == []

    async def test_broadcast_skips_players_who_left_the_room(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.join_room("socket-1", "ABCD")
        await realtime.join_room("socket-2", "ABCD")
        before = make_round_started(round_number=1)
        await realtime.broadcast_to_room("ABCD", before)

        await realtime.leave_room("socket-2", "ABCD")
        after = make_round_started(round_number=2)
        await realtime.broadcast_to_room("ABCD", after)

        assert await received("socket-1") == [before, after]
        assert await received("socket-2") == [before]

    async def test_broadcast_to_an_empty_room_reaches_no_one(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.join_room("socket-1", "WXYZ")

        await realtime.broadcast_to_room("ABCD", make_game_created())

        assert await received("socket-1") == []

    async def test_broadcast_does_not_reach_players_who_join_later(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.broadcast_to_room("ABCD", make_game_created())

        await realtime.join_room("socket-1", "ABCD")

        assert await received("socket-1") == []

    # Membership

    async def test_joining_a_room_twice_delivers_broadcasts_once(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.join_room("socket-1", "ABCD")
        await realtime.join_room("socket-1", "ABCD")
        event = make_game_created()

        await realtime.broadcast_to_room("ABCD", event)

        assert await received("socket-1") == [event]

    async def test_leaving_a_room_never_joined_is_ignored(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.leave_room("socket-1", "ABCD")

        assert await received("socket-1") == []

    async def test_leaving_one_room_keeps_the_others(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.join_room("socket-1", "ABCD")
        await realtime.join_room("socket-1", "WXYZ")
        await realtime.leave_room("socket-1", "ABCD")
        event = make_game_created(room_code="WXYZ")

        await realtime.broadcast_to_room("ABCD", make_game_created())
        await realtime.broadcast_to_room("WXYZ", event)

        assert await received("socket-1") == [event]

    async def test_messages_arrive_in_the_order_sent(
        self, realtime: RealtimePort, received: Received
    ) -> None:
        await realtime.join_room("socket-1", "ABCD")
        first, second, third = make_game_created(), make_round_started(), make_script_generated()

        await realtime.broadcast_to_room("ABCD", first)
        await realtime.send_to_player("socket-1", second)
        await realtime.broadcast_to_room("ABCD", third)

        assert await received("socket-1") == [first, second, third]
