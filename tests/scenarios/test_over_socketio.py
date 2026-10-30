"""Play the full-game scenario over Socket.IO, against a real server.

Each bot has its own connection, and decides only on what that connection
received. One server serves every test in this module.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from scripts.validate import MAX_EMBED_BYTES
from tests.evidence import write_evidence
from tests.scenarios.library import FULL_GAME
from tests.scenarios.scenario import outcome_of, play, report
from tests.sim.socketio_client import SocketIOServer

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def server() -> AsyncIterator[SocketIOServer]:
    async with SocketIOServer.running() as running:
        yield running


async def test_full_game_plays_out_as_expected_over_socketio(server: SocketIOServer):
    played = await play(FULL_GAME, server)
    text = report(FULL_GAME, played)
    write_evidence(f"scenarios/{FULL_GAME.slug}-socketio.md", text)

    assert len(text.encode()) < MAX_EMBED_BYTES
    assert played.transport == "Socket.IO (real server)"
    assert outcome_of(played) == FULL_GAME.expected
