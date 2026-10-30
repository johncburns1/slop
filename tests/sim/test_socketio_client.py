"""Tests for the game client that plays over Socket.IO against a real server."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from slop.domain.errors import GameNotFoundError, GameRuleError
from slop.domain.events import (
    GameCompleted,
    PlayerJoined,
    PlayerJoinedTeam,
    PlayerReconnected,
    TeamFormed,
)
from tests.sim.bot import CORRECT, BotScript
from tests.sim.socketio_client import SocketIOServer
from tests.sim.table import Table

pytestmark = pytest.mark.asyncio(loop_scope="module")

PROMPT = "Penguins open a tiny bakery"
SCRIPTS = (
    BotScript(name="A", team="X", prompts={0: PROMPT}),
    BotScript(name="B", team="Y", guesses={0: CORRECT}),
    BotScript(name="C", team="X"),
    BotScript(name="D", team="Y"),
)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def server() -> AsyncIterator[SocketIOServer]:
    async with SocketIOServer.running() as running:
        yield running


async def test_each_inbox_is_what_that_connection_received(server: SocketIOServer):
    room_code = await server.create_game()
    alice, bob = await server.connect_player(1), await server.connect_player(2)

    alice_id = await alice.join_game(room_code, "Alice")
    bob_id = await bob.join_game(room_code, "Bob")
    await alice.create_team("Red", "#f00")
    await bob.caught_up()

    assert alice.socket_id != bob.socket_id
    formed = [TeamFormed, PlayerJoinedTeam]
    assert [type(e) for e in alice.inbox()] == [PlayerJoined, PlayerJoined, *formed]
    # Bob joined second, so he never heard Alice join.
    assert [type(e) for e in bob.inbox()] == [PlayerJoined, *formed]
    assert [e.player_id for e in bob.inbox() if isinstance(e, PlayerJoined)] == [bob_id]
    assert alice.inbox()[0].player_id == alice_id  # type: ignore[attr-defined]


async def test_a_rejected_message_raises_and_stays_out_of_the_inbox(server: SocketIOServer):
    room_code = await server.create_game()
    alice = await server.connect_player(1)
    await alice.join_game(room_code, "Alice")

    with pytest.raises(GameRuleError, match="at least 2 teams"):
        await alice.start_personality_selection()  # no teams yet
    with pytest.raises(GameNotFoundError):
        await (await server.connect_player(2)).join_game("ZZZZ", "Bob")

    await alice.caught_up()
    assert [type(e) for e in alice.inbox()] == [PlayerJoined]
    assert [e["request"] for e in alice.errors] == ["start_personality_selection"]


async def test_a_bot_drops_and_rejoins_on_a_new_connection_and_plays_on(
    server: SocketIOServer,
):
    room_code = await server.create_game()
    table = await Table.seat(server, room_code, SCRIPTS)
    await table.step_until(lambda t: 0 in t.bots[2].view().scripts_ready)
    c = table.bots[2]
    old_socket = c.socket_id
    await c.drop()
    heard = len(c.inbox())
    await table.step()  # B guesses while C is away

    assert not c.connected
    assert len(c.inbox()) == heard
    with pytest.raises(RuntimeError, match="Not connected"):
        await c.client.submit_guess("anything")

    snapshot = await c.rejoin()
    await table.caught_up()

    assert c.connected and c.socket_id != old_socket
    assert snapshot.current_round is not None
    assert [g.guess for g in snapshot.current_round.guesses] == [PROMPT]
    assert isinstance(c.inbox()[-1], PlayerReconnected)
    assert [g.guess for g in c.view().guesses[0]] == [PROMPT]
    completed = await table.play()
    assert [e for e in c.inbox() if isinstance(e, GameCompleted)] == [completed]


async def test_bots_play_a_whole_game_over_the_network(server: SocketIOServer):
    room_code = await server.create_game()
    table = await Table.seat(
        server,
        room_code,
        [BotScript(name=n, team=t) for n, t in (("A", "X"), ("B", "Y"), ("C", "X"), ("D", "Y"))],
    )

    completed = await table.play()

    x, y = table.team_id_named("X"), table.team_id_named("Y")
    assert completed.final_scores == {x: 3, y: 3}
    assert all(bot.view().completed == completed for bot in table.bots)
