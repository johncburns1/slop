"""Tests for the HTTP request and response models."""

import pytest
from pydantic import ValidationError

from slop.api.schemas import HealthResponse, PlayerViewReply
from slop.application.player_view import player_view
from slop.domain import Award
from slop.domain.game import Tiebreaker
from tests.builders import scored_after_last_round, tied_after_last_round


def test_health_response_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({"status": "broken", "version": "0.1.0"})


def test_health_response_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        HealthResponse.model_validate({"status": "ok", "version": "0.1.0", "extra": 1})


def test_the_rejoin_reply_carries_the_awards_of_a_finished_game() -> None:
    game = scored_after_last_round(scores=(4, 2))
    game.finish()
    game.awards = [Award(title="Champions", recipient="Red Team", reason="For winning.")]

    reply = PlayerViewReply.model_validate(player_view(game, "player-3"))

    assert reply.model_dump()["awards"] == [
        {"title": "Champions", "recipient": "Red Team", "reason": "For winning."}
    ]


def test_the_rejoin_reply_carries_the_tiebreaker_in_play() -> None:
    game = tied_after_last_round(rounds_per_team=1)
    game.tiebreaker = Tiebreaker(cycle=1, team_ids=["team-1", "team-2"], first_round=2)

    reply = PlayerViewReply.model_validate(player_view(game, "player-3"))

    assert reply.model_dump()["tiebreaker"] == {
        "cycle": 1,
        "team_ids": ["team-1", "team-2"],
        "first_round": 2,
    }
