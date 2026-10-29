"""Typed request and response models for the HTTP and Socket.IO API.

These are the API's wire format. They stay in the API layer and are never
passed into the domain.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from slop.domain.game import ContentTone


class HealthResponse(BaseModel):
    """Body of `GET /health`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    version: str


# Socket.IO messages: see `slop.api.messages` for the protocol.


class Request(BaseModel):
    """A client message's payload. Unknown fields are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class NoPayload(Request):
    """Payload of a message that needs nothing beyond who sent it."""


class CreateGameRequest(Request):
    """Payload of `create_game`. Settings left out use the game's defaults."""

    content_tone: ContentTone
    rounds_per_team: int | None = None
    guess_timer_seconds: int | None = None
    max_players_per_team: int | None = None
    max_players: int | None = None


class JoinGameRequest(Request):
    room_code: str
    player_name: str


class CreateTeamRequest(Request):
    team_name: str
    color: str


class JoinTeamRequest(Request):
    team_id: str


class PersonalityRequest(Request):
    """Payload of `assign_personality` and `guess_personality`."""

    personality_id: str


class SubmitPromptRequest(Request):
    prompt: str


class SubmitGuessRequest(Request):
    guess: str


class PickWinningGuessRequest(Request):
    """Payload of `pick_winning_guess`. A null `guess_index` says nobody got it."""

    guess_index: int | None


class Reply(BaseModel):
    """The ack a message gets back when it succeeds."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class GameCreatedReply(Reply):
    game_id: str
    room_code: str


class JoinedReply(Reply):
    game_id: str
    player_id: str


class TeamCreatedReply(Reply):
    team_id: str


ErrorCode = Literal["invalid_payload", "not_in_game", "game_not_found", "rule_broken"]


class ErrorMessage(BaseModel):
    """Sent only to the sender when its message is rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ErrorCode
    message: str
    request: str
