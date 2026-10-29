"""Stand-in dependencies for use case tests.

Request ``deps`` to run a use case, and the stand-ins themselves to inspect
what it stored and who it told.
"""

from datetime import UTC, datetime

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.ids import SequentialIds
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps

NOW = datetime(2026, 1, 1, 20, 0, tzinfo=UTC)


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def realtime() -> RecordingRealtime:
    return RecordingRealtime()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def ids() -> SequentialIds:
    return SequentialIds()


@pytest.fixture
def deps(
    storage: InMemoryStorage, realtime: RecordingRealtime, clock: FixedClock, ids: SequentialIds
) -> GameDeps:
    return GameDeps(storage=storage, realtime=realtime, clock=clock, ids=ids)
