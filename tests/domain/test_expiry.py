"""Tests for when a game expires."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from slop.domain import Game, GameStatus
from slop.domain.expiry import ExpiryPolicy, is_expired

LAST_EVENT = datetime(2026, 1, 1, 20, 0, tzinfo=UTC)
POLICY = ExpiryPolicy(idle=timedelta(hours=2), after_finish=timedelta(minutes=30))


def game(status: GameStatus = GameStatus.LOBBY) -> Game:
    return Game(id="game-1", room_code="ABCD", status=status, last_event_at=LAST_EVENT)


def test_defaults_are_two_hours_idle_and_thirty_minutes_after_finishing() -> None:
    assert ExpiryPolicy() == POLICY


@pytest.mark.parametrize(
    "status", [GameStatus.LOBBY, GameStatus.PERSONALITY_SELECTION, GameStatus.PLAYING]
)
def test_an_unfinished_game_expires_once_idle_for_the_idle_period(status: GameStatus) -> None:
    assert not is_expired(game(status), LAST_EVENT + timedelta(hours=2, seconds=-1), POLICY)
    assert is_expired(game(status), LAST_EVENT + timedelta(hours=2), POLICY)


def test_a_finished_game_expires_after_the_shorter_period() -> None:
    finished = game(GameStatus.FINISHED)

    assert not is_expired(finished, LAST_EVENT + timedelta(minutes=29), POLICY)
    assert is_expired(finished, LAST_EVENT + timedelta(minutes=30), POLICY)


def test_a_game_with_a_recent_event_has_not_expired() -> None:
    assert not is_expired(game(), LAST_EVENT, POLICY)
    assert not is_expired(game(), LAST_EVENT - timedelta(days=1), POLICY)  # clock behind


def test_the_policy_is_configurable() -> None:
    quick = replace(POLICY, idle=timedelta(minutes=5))

    assert is_expired(game(), LAST_EVENT + timedelta(minutes=5), quick)


@pytest.mark.parametrize(
    ("idle", "after_finish"),
    [(timedelta(0), timedelta(minutes=1)), (timedelta(hours=1), timedelta(0))],
)
def test_periods_must_be_positive(idle: timedelta, after_finish: timedelta) -> None:
    with pytest.raises(ValueError):
        ExpiryPolicy(idle=idle, after_finish=after_finish)
