"""Tests for the timers that close guessing at the deadline."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path

import pytest

from slop.adapters.clock import FixedClock
from slop.adapters.storage import InMemoryStorage, SQLiteStorage
from slop.adapters.websocket import RecordingRealtime
from slop.application.engine import GameDeps, load_game
from slop.application.guess_and_score import EndGuessing, end_guessing
from slop.application.guess_timers import GuessTimers
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain import Game, GuessingEnded
from tests.builders import in_guessing_phase, waiting_for_prompt

GUESS_TIMER = timedelta(seconds=60)


@dataclass
class ManualSleep:
    """Stands in for ``asyncio.sleep``: sleepers wait until the test moves the fixed clock."""

    clock: FixedClock
    asked: list[float] = field(default_factory=list)
    _woken: asyncio.Event = field(default_factory=asyncio.Event)

    async def __call__(self, seconds: float) -> None:
        self.asked.append(seconds)
        self._woken.clear()
        await self._woken.wait()

    async def advance(self, delta: timedelta) -> None:
        """Move the clock, wake the sleepers, and let them run."""
        self.clock.advance(delta)
        self._woken.set()
        await settle()


async def settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.fixture
def sleep(clock: FixedClock) -> ManualSleep:
    return ManualSleep(clock)


@pytest.fixture
async def timers(deps: GameDeps, sleep: ManualSleep) -> AsyncIterator[GuessTimers]:
    guess_timers = GuessTimers(deps, sleep=sleep)
    yield guess_timers
    await guess_timers.stop()


async def guessing_open(deps: GameDeps, realtime: RecordingRealtime) -> Game:
    game = waiting_for_prompt()
    await deps.storage.save_snapshot(game)
    for player in game.players:
        await realtime.join_room(player.socket_id, game.room_code)
    return await submit_prompt(deps, SubmitPrompt(game.id, "player-1", "a haunted vending machine"))


async def test_the_timer_sleeps_until_the_deadline_then_moves_the_round_to_judging(
    deps: GameDeps, realtime: RecordingRealtime, timers: GuessTimers, sleep: ManualSleep
):
    game = await guessing_open(deps, realtime)

    timers.track(game)
    await settle()

    assert sleep.asked == [60.0]
    assert (await load_game(deps, game.id)).rounds[0].guessing_open

    await sleep.advance(GUESS_TIMER)

    assert (await load_game(deps, game.id)).rounds[0].guessing_ended
    assert realtime.who_received(GuessingEnded) == {
        "socket-1",
        "socket-2",
        "socket-3",
        "socket-4",
    }
    assert timers.running == 0


async def test_a_timer_woken_early_goes_back_to_sleep(
    deps: GameDeps, realtime: RecordingRealtime, timers: GuessTimers, sleep: ManualSleep
):
    game = await guessing_open(deps, realtime)
    timers.track(game)
    await settle()

    await sleep.advance(timedelta(seconds=45))

    assert sleep.asked == [60.0, 15.0]
    assert (await load_game(deps, game.id)).rounds[0].guessing_open


async def test_tracking_the_same_round_twice_keeps_one_timer(
    deps: GameDeps, realtime: RecordingRealtime, timers: GuessTimers, sleep: ManualSleep
):
    game = await guessing_open(deps, realtime)

    timers.track(game)
    timers.track(game)
    await settle()

    assert timers.running == 1
    assert sleep.asked == [60.0]


async def test_ending_guessing_early_cancels_the_timer(
    deps: GameDeps,
    realtime: RecordingRealtime,
    storage: InMemoryStorage,
    timers: GuessTimers,
    sleep: ManualSleep,
):
    game = await guessing_open(deps, realtime)
    timers.track(game)
    await settle()

    timers.track(await end_guessing(deps, EndGuessing(game.id, "player-1")))
    await settle()

    assert timers.running == 0
    await sleep.advance(GUESS_TIMER)
    ended = [e for e in await storage.get_events(game.id) if isinstance(e, GuessingEnded)]
    assert len(ended) == 1


async def test_stopping_cancels_every_timer(
    deps: GameDeps, realtime: RecordingRealtime, timers: GuessTimers, sleep: ManualSleep
):
    game = await guessing_open(deps, realtime)
    timers.track(game)
    await settle()

    await timers.stop()

    assert timers.running == 0
    await sleep.advance(GUESS_TIMER)
    assert (await load_game(deps, game.id)).rounds[0].guessing_open


async def test_a_game_deleted_while_its_timer_runs_is_ignored(
    deps: GameDeps,
    realtime: RecordingRealtime,
    storage: InMemoryStorage,
    timers: GuessTimers,
    sleep: ManualSleep,
):
    game = await guessing_open(deps, realtime)
    timers.track(game)
    await settle()
    await storage.delete_game(game.id)

    await sleep.advance(GUESS_TIMER)

    assert timers.running == 0


async def test_a_round_with_no_deadline_gets_no_timer(deps: GameDeps, timers: GuessTimers):
    """A round already running when the server was upgraded never ran out of time."""
    game = in_guessing_phase()

    timers.track(game)

    assert timers.running == 0


async def test_startup_closes_overdue_rounds_and_restarts_timers_for_the_rest(
    deps: GameDeps,
    realtime: RecordingRealtime,
    clock: FixedClock,
    sleep: ManualSleep,
):
    """A new server finds the games the last one left, with no timers of their own."""
    overdue = await guessing_open(deps, realtime)
    clock.advance(timedelta(seconds=50))
    running = in_guessing_phase()
    running.id = "game-2"
    running.room_code = "WXYZ"
    running.rounds[0].guess_deadline = clock.now() + timedelta(seconds=30)
    await deps.storage.save_snapshot(running)
    clock.advance(timedelta(seconds=10))

    timers = GuessTimers(deps, sleep=sleep)
    await timers.restore()
    await settle()

    assert (await load_game(deps, overdue.id)).rounds[0].guessing_ended
    assert (await load_game(deps, running.id)).rounds[0].guessing_open
    assert timers.running == 1
    assert sleep.asked == [20.0]

    await sleep.advance(timedelta(seconds=20))

    assert (await load_game(deps, running.id)).rounds[0].guessing_ended
    await timers.stop()


async def test_a_failing_close_is_logged_and_does_not_stop_startup(
    deps: GameDeps,
    realtime: RecordingRealtime,
    storage: InMemoryStorage,
    clock: FixedClock,
    sleep: ManualSleep,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    await guessing_open(deps, realtime)
    clock.advance(GUESS_TIMER)
    failing: Callable[..., object] = _raises(RuntimeError("disk full"))
    monkeypatch.setattr(storage, "save_event", failing)

    timers = GuessTimers(deps, sleep=sleep)
    await timers.restore()

    assert "Closing guessing failed" in caplog.text
    await timers.stop()


def _raises(error: Exception) -> Callable[..., object]:
    async def fail(*args: object) -> None:
        raise error

    return fail


async def test_failing_to_list_the_games_does_not_stop_startup(
    deps: GameDeps,
    storage: InMemoryStorage,
    sleep: ManualSleep,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    monkeypatch.setattr(storage, "list_games", _raises(OSError("disk hiccup")))

    await GuessTimers(deps, sleep=sleep).restore()

    assert "Restoring guess timers failed" in caplog.text


async def test_a_new_server_on_the_same_database_closes_the_overdue_round(
    deps: GameDeps,
    realtime: RecordingRealtime,
    clock: FixedClock,
    sleep: ManualSleep,
    tmp_path: Path,
):
    """The deadline survives a restart in the stored snapshot, and nothing else is needed."""
    stored = replace(deps, storage=SQLiteStorage(tmp_path / "slop.sqlite3"))
    game = await guessing_open(stored, realtime)
    clock.advance(GUESS_TIMER)

    restarted = replace(stored, storage=SQLiteStorage(tmp_path / "slop.sqlite3"))
    await GuessTimers(restarted, sleep=sleep).restore()

    current = (await load_game(restarted, game.id)).rounds[0]
    assert current.guessing_ended
    assert current.guess_deadline is not None
