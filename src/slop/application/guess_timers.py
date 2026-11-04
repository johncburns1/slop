"""The timers that close guessing at each round's deadline.

The deadline itself lives in the round, so these tasks are only a convenience:
if one is lost, the next late guess or rejoin closes the round anyway (see
``guess_and_score``), and ``restore`` picks up where a stopped server left off.
Nothing is emitted here beyond what ``close_guessing_if_due`` emits.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from slop.application.engine import GameDeps
from slop.application.guess_and_score import (
    CloseGuessingIfDue,
    close_guessing_if_due,
    round_open_for_guessing,
)
from slop.domain.errors import GameNotFoundError
from slop.domain.game import Game

TASK_NAME = "slop.guess_timer"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Timer:
    round_number: int
    task: asyncio.Task[None]


class GuessTimers:
    """Runs one task per game whose round is taking guesses.

    ``sleep`` is how a timer waits; tests replace it to run with a fixed clock.
    """

    def __init__(
        self, deps: GameDeps, *, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    ) -> None:
        self._deps = deps
        self._sleep = sleep
        self._timers: dict[str, _Timer] = {}

    @property
    def running(self) -> int:
        """How many timers are running."""
        return len(self._timers)

    def track(self, game: Game) -> None:
        """Bring the game's timer in line with its current round.

        Call this after anything that may open or end guessing. A round taking
        guesses gets a timer unless it has one, and any other timer is cancelled.
        """
        current = round_open_for_guessing(game)
        running = self._timers.get(game.id)
        if current is None or current.guess_deadline is None:
            if running is not None:
                self._cancel(game.id, running)
            return
        if running is not None:
            if running.round_number == current.round_number:
                return
            self._cancel(game.id, running)
        task = asyncio.create_task(
            self._run(game.id, current.guess_deadline), name=f"{TASK_NAME}.{game.id}"
        )
        self._timers[game.id] = _Timer(current.round_number, task)
        task.add_done_callback(lambda done: self._forget(game.id, done))

    async def restore(self) -> None:
        """Close the rounds that ran out of time while no server was up, and time the rest.

        A failure only leaves those rounds to be closed by a late guess or a rejoin.
        """
        try:
            games = await self._deps.storage.list_games()
        except Exception:
            logger.exception("Restoring guess timers failed")
            return
        for game in games:
            if round_open_for_guessing(game) is None:
                continue
            closed = await self._close(game.id)
            self.track(closed if closed is not None else game)

    async def stop(self) -> None:
        """Cancel every timer and wait for them to finish."""
        timers = list(self._timers.items())
        for game_id, timer in timers:
            self._cancel(game_id, timer)
        await asyncio.gather(*(timer.task for _, timer in timers), return_exceptions=True)

    async def _run(self, game_id: str, deadline: datetime) -> None:
        while (left := (deadline - self._deps.clock.now()).total_seconds()) > 0:
            await self._sleep(left)
        await self._close(game_id)

    async def _close(self, game_id: str) -> Game | None:
        """Close guessing if it is due. On failure return None: a rejoin can still close it."""
        try:
            return await close_guessing_if_due(self._deps, CloseGuessingIfDue(game_id))
        except GameNotFoundError:
            return None  # the game expired while the timer ran
        except Exception:
            logger.exception("Closing guessing failed for game %s", game_id)
            return None

    def _cancel(self, game_id: str, timer: _Timer) -> None:
        del self._timers[game_id]
        timer.task.cancel()

    def _forget(self, game_id: str, done: asyncio.Task[None]) -> None:
        timer = self._timers.get(game_id)
        if timer is not None and timer.task is done:
            del self._timers[game_id]
