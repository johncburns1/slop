"""Tests for running bots at a table."""

import pytest

from tests.sim.bot import BotScript
from tests.sim.client import InProcessServer
from tests.sim.table import SimulationStalledError, Table


async def test_play_raises_when_no_bot_can_move_the_game_on():
    server = InProcessServer.with_stand_ins()
    room_code = await server.create_game()
    # Everyone on one team, so the host can never close the lobby.
    table = await Table.seat(
        server, room_code, [BotScript(name="A", team="Solo"), BotScript(name="B", team="Solo")]
    )

    with pytest.raises(SimulationStalledError, match="No bot can act"):
        await table.play()


async def test_each_bot_inbox_is_what_the_realtime_stand_in_delivered_to_its_socket():
    server = InProcessServer.with_stand_ins()
    room_code = await server.create_game()
    table = await Table.seat(
        server, room_code, [BotScript(name=n, team=t) for n, t in (("A", "X"), ("B", "Y"))]
    )
    await table.play()

    for bot in table.bots:
        assert bot.inbox() == server.realtime.received_by(bot.socket_id)
        assert bot.inbox()
