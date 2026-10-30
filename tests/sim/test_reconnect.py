"""Tests for dropping a bot's connection, rejoining, and restarting the server."""

from collections.abc import Callable
from pathlib import Path

import pytest

from slop.domain.errors import GameNotFoundError
from slop.domain.events import GameCompleted, PlayerReconnected, ScriptReady
from tests.sim.bot import CORRECT, BotScript
from tests.sim.client import InProcessServer
from tests.sim.table import SimulationStalledError, Table

SCRIPTS = (
    BotScript(name="A", team="X", prompts={0: "Penguins open a tiny bakery"}),
    BotScript(name="B", team="Y", guesses={0: CORRECT}),
    BotScript(name="C", team="X"),
    BotScript(name="D", team="Y"),
)


async def seated(server: InProcessServer) -> Table:
    room_code = await server.create_game(rounds_per_team=1)
    return await Table.seat(server, room_code, SCRIPTS)


def script_ready(bot_index: int, round_number: int) -> Callable[[Table], bool]:
    def ready(table: Table) -> bool:
        return round_number in table.bots[bot_index].view().scripts_ready

    return ready


async def test_a_dropped_bot_hears_nothing_and_does_nothing_until_it_rejoins():
    server = InProcessServer.with_stand_ins()
    table = await seated(server)
    await table.step_until(script_ready(2, 0))
    c = table.bots[2]

    await c.drop()
    heard = len(c.inbox())
    await table.step()  # B guesses

    assert not c.connected
    assert len(c.inbox()) == heard
    assert c.socket_id not in server.realtime.members_of(c.room_code)
    with pytest.raises(RuntimeError, match="Not connected"):
        await c.client.submit_guess("anything")


async def test_a_rejoining_bot_resyncs_from_its_view_and_plays_on():
    server = InProcessServer.with_stand_ins()
    table = await seated(server)
    await table.step_until(script_ready(2, 0))
    c = table.bots[2]
    old_socket = c.socket_id
    await c.drop()
    await table.step()  # B guesses while C is away

    snapshot = await c.rejoin()

    assert c.connected and c.socket_id != old_socket
    assert snapshot.current_round is not None
    assert snapshot.current_round.prompt == "Penguins open a tiny bakery"
    assert [g.guess for g in snapshot.current_round.guesses] == ["Penguins open a tiny bakery"]
    assert isinstance(c.inbox()[-1], PlayerReconnected)
    # The guess C missed is in its view, from the snapshot.
    assert [g.guess for g in c.view().guesses[0]] == ["Penguins open a tiny bakery"]
    completed = await table.play()
    assert [e for e in c.inbox() if isinstance(e, GameCompleted)] == [completed]


async def test_play_skips_dropped_bots_and_stalls_if_only_they_could_act():
    server = InProcessServer.with_stand_ins()
    table = await seated(server)
    await table.step_until(script_ready(0, 0))
    for bot in table.bots:
        await bot.drop()

    with pytest.raises(SimulationStalledError, match="No bot can act"):
        await table.play()


async def test_step_until_raises_if_the_game_stalls_first():
    server = InProcessServer.with_stand_ins()
    table = await seated(server)

    with pytest.raises(SimulationStalledError):
        await table.step_until(lambda table: False)


async def test_a_restarted_sqlite_server_keeps_the_game_and_drops_every_connection(
    tmp_path: Path,
):
    server = InProcessServer.on_sqlite(tmp_path / "slop.sqlite3")
    table = await seated(server)
    await table.step_until(script_ready(0, 0))
    before = [len(bot.inbox()) for bot in table.bots]

    await server.restart()

    assert not any(bot.connected for bot in table.bots)
    assert [len(bot.inbox()) for bot in table.bots] == before
    for bot in table.bots:
        await bot.rejoin()
    assert all(isinstance(bot.inbox()[-1], PlayerReconnected) for bot in table.bots)
    assert table.bots[0].view().scripts_ready == {0}
    assert server.realtime.who_received(ScriptReady) == frozenset()  # nothing replayed
    await table.play()


async def test_restarting_an_in_memory_server_loses_the_game():
    server = InProcessServer.with_stand_ins()
    table = await seated(server)

    await server.restart()

    with pytest.raises(GameNotFoundError):
        await table.bots[0].rejoin()


async def test_a_bot_that_rejoins_in_the_lobby_still_forms_its_team():
    server = InProcessServer.with_stand_ins()
    table = await seated(server)
    d = table.bots[3]
    await d.drop()
    # The host waits for D to pick a team, so the game can't start without D.
    with pytest.raises(SimulationStalledError):
        await table.play()

    await d.rejoin()

    assert not d.view().selecting_personalities
    assert d.view().teams.keys() == table.bots[0].view().teams.keys()
    await table.play()
    assert d.view().team_id == table.team_id_named("Y")
