"""Tests for the in-memory storage adapter."""

import pytest

from slop.adapters.storage import InMemoryStorage
from slop.ports import StoragePort
from tests.adapters.storage.contract import StoragePortContract, make_game, make_game_created


class TestInMemoryStorage(StoragePortContract):
    """Run the StoragePort contract against InMemoryStorage."""

    @pytest.fixture
    def storage(self) -> StoragePort:
        return InMemoryStorage()


async def test_instances_do_not_share_state():
    """Separate instances must not share class-level storage."""
    first, second = InMemoryStorage(), InMemoryStorage()
    await first.save_event(make_game_created())
    await first.save_snapshot(make_game())

    assert await second.get_events("game-1") == []
    assert await second.get_snapshot("game-1") is None
