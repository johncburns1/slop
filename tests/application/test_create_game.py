"""Tests for the create game use case."""

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.ids import SequentialIds
from slop.adapters.llm import StandInLLMAdapter
from slop.adapters.storage import InMemoryStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.create_game import (
    ROOM_CODE_ATTEMPTS,
    CreateGame,
    RoomCodesExhaustedError,
    create_game,
)
from slop.application.engine import GameDeps, find_game
from slop.domain import ContentTone, GameCreated, GameSettings, GameStatus
from slop.domain.errors import GameRuleError
from tests.application.conftest import NOW
from tests.evidence import write_evidence


async def test_creating_a_game_stores_it_and_tells_the_room(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    game = await create_game(deps, CreateGame(content_tone=ContentTone.ADULT, rounds_per_team=2))

    assert (game.id, game.room_code, game.status) == ("id-1", "ROOM1", GameStatus.LOBBY)
    assert game.settings == GameSettings(rounds_per_team=2, content_tone=ContentTone.ADULT)
    assert game.created_at == NOW
    assert await find_game(deps, "ROOM1") == game
    assert await storage.get_snapshot(game.id) == game
    (event,) = await storage.get_events(game.id)
    assert isinstance(event, GameCreated)
    assert (event.room_code, event.content_tone, event.rounds_per_team) == ("ROOM1", "adult", 2)
    assert realtime.broadcasts_to("ROOM1") == [event]
    write_evidence("create-game/events.jsonl", event.model_dump_json() + "\n")


async def test_every_setting_is_kept(deps: GameDeps):
    command = CreateGame(
        content_tone=ContentTone.FAMILY,
        rounds_per_team=4,
        guess_timer_seconds=45,
        max_players_per_team=2,
        max_players=8,
    )

    game = await create_game(deps, command)

    assert game.settings == GameSettings(
        rounds_per_team=4,
        guess_timer_seconds=45,
        max_players_per_team=2,
        content_tone=ContentTone.FAMILY,
        max_players=8,
    )


async def test_a_taken_room_code_is_skipped(
    storage: InMemoryStorage, realtime: RecordingRealtime, clock: FixedClock
):
    ids = SequentialIds(["ABCD", "ABCD", "WXYZ"])
    deps = GameDeps(
        storage=storage, realtime=realtime, clock=clock, ids=ids, llm=StandInLLMAdapter()
    )
    first = await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))

    second = await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))

    assert (first.room_code, second.room_code) == ("ABCD", "WXYZ")
    assert (await find_game(deps, "ABCD")).id == first.id
    assert (await find_game(deps, "WXYZ")).id == second.id


async def test_it_gives_up_when_every_room_code_is_taken(
    storage: InMemoryStorage, realtime: RecordingRealtime, clock: FixedClock
):
    ids = SequentialIds(["ABCD"] * (ROOM_CODE_ATTEMPTS + 1))
    deps = GameDeps(
        storage=storage, realtime=realtime, clock=clock, ids=ids, llm=StandInLLMAdapter()
    )
    await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))

    with pytest.raises(RoomCodesExhaustedError):
        await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY))


async def test_unplayable_settings_are_rejected_without_storing_anything(
    deps: GameDeps, storage: InMemoryStorage, realtime: RecordingRealtime
):
    with pytest.raises(GameRuleError, match="rounds_per_team"):
        await create_game(deps, CreateGame(content_tone=ContentTone.FAMILY, rounds_per_team=0))

    assert await storage.get_game_by_room_code("ROOM1") is None
    assert realtime.broadcasts_to("ROOM1") == []
