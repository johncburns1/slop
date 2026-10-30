"""Socket.IO messages: the contract between the server and its clients.

Clients send these messages, each with a JSON object payload (``{}`` if it
has no fields; ``?`` marks optional fields), and get the result in the ack:

- ``create_game {content_tone: "family"|"adult", rounds_per_team?,
  guess_timer_seconds?, max_players_per_team?, max_players?}``
  -> ``{game_id, room_code}``
- ``join_game {room_code, player_name}`` -> ``{game_id, player_id}``
- ``rejoin_game {room_code, player_id}`` -> the player's view (see below)
- ``leave_game {}``
- ``create_team {team_name, color}`` -> ``{team_id}``
- ``join_team {team_id}``
- ``shuffle_teams {}`` (host only)
- ``start_personality_selection {}`` (host only)
- ``assign_personality {personality_id}``
- ``submit_prompt {prompt}``
- ``submit_guess {guess}``
- ``pick_winning_guess {guess_index}`` (an int, or null for "nobody got it")
- ``guess_personality {personality_id}``
- ``play_again {}`` (host only, once the game has finished)

Messages with no ``->`` ack with null.

``create_game`` only creates the game; the host then sends ``join_game`` like
everyone else, and the first player to join is the host. ``join_game`` ties
the connection to the new player, and every later message acts as that
player in that game. Disconnecting unties the connection but leaves the
player in the game.

``rejoin_game`` is how that player comes back, on a new connection or after a
server restart: it ties the connection to the existing player (no new
``PlayerJoined``; the room gets ``PlayerReconnected``) and acks with
``{game_id, room_code, status, settings, player_id, team_id, players, teams,
current_round, my_pick}``, the game as that player may see it (see
``slop.application.player_view``). ``current_round`` holds the round's
``phase`` and ``guesses``, plus its ``prompt`` and ``script`` for the acting
team only. A team's ``personality_id`` stays null until it is revealed, and
``my_pick`` is the personality the player's team picked for another team.

The server sends game events to clients under their ``event_type`` (such as
``PlayerJoined``), with the event as the payload. A rejected message gets
``error`` with ``{code, message, request}``, sent only to its sender, and the
same object as its ack. ``code`` is ``invalid_payload``, ``not_in_game`` (the
connection hasn't joined a game), ``game_not_found``, or ``rule_broken``;
``message`` is safe to show to players and ``request`` is the message name.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from slop.adapters.websocket import SocketIORealtime
from slop.api.schemas import (
    CreateGameRequest,
    CreateTeamRequest,
    ErrorCode,
    ErrorMessage,
    GameCreatedReply,
    JoinedReply,
    JoinGameRequest,
    JoinTeamRequest,
    NoPayload,
    PersonalityRequest,
    PickWinningGuessRequest,
    PlayerViewReply,
    RejoinGameRequest,
    Reply,
    Request,
    SubmitGuessRequest,
    SubmitPromptRequest,
    TeamCreatedReply,
)
from slop.application.assign_personality import AssignPersonality, assign_personality
from slop.application.create_game import CreateGame, create_game
from slop.application.engine import GameDeps
from slop.application.form_teams import (
    CreateTeam,
    JoinTeam,
    ShuffleTeams,
    StartPersonalitySelection,
    create_team,
    join_team,
    shuffle_teams,
    start_personality_selection,
)
from slop.application.guess_and_score import (
    GuessPersonality,
    PickWinningGuess,
    SubmitGuess,
    guess_personality,
    pick_winning_guess,
    submit_guess,
)
from slop.application.join_game import JoinGame, join_game
from slop.application.leave_game import LeaveGame, leave_game
from slop.application.play_again import PlayAgain, play_again
from slop.application.rejoin_game import RejoinGame, rejoin_game
from slop.application.submit_prompt import SubmitPrompt, submit_prompt
from slop.domain.errors import GameNotFoundError, GameRuleError

ERROR = "error"


class NotInGameError(GameRuleError):
    """The connection sent a game message before joining a game."""


@dataclass(frozen=True)
class Seat:
    """The player a connection plays as."""

    game_id: str
    player_id: str


class GameMessages:
    """Turns client messages into use case calls."""

    def __init__(self, deps: GameDeps, realtime: SocketIORealtime) -> None:
        self._deps = deps
        self._realtime = realtime
        self._seats: dict[str, Seat] = {}

    def register(self) -> None:
        """Start handling every client message on the realtime server."""
        self._route("create_game", CreateGameRequest, self.create_game)
        self._route("join_game", JoinGameRequest, self.join_game)
        self._route("rejoin_game", RejoinGameRequest, self.rejoin_game)
        self._route("leave_game", NoPayload, self.leave_game)
        self._route("create_team", CreateTeamRequest, self.create_team)
        self._route("join_team", JoinTeamRequest, self.join_team)
        self._route("shuffle_teams", NoPayload, self.shuffle_teams)
        self._route("start_personality_selection", NoPayload, self.start_personality_selection)
        self._route("assign_personality", PersonalityRequest, self.assign_personality)
        self._route("submit_prompt", SubmitPromptRequest, self.submit_prompt)
        self._route("submit_guess", SubmitGuessRequest, self.submit_guess)
        self._route("pick_winning_guess", PickWinningGuessRequest, self.pick_winning_guess)
        self._route("guess_personality", PersonalityRequest, self.guess_personality)
        self._route("play_again", NoPayload, self.play_again)
        self._realtime.on_disconnect(self.disconnected)

    async def create_game(self, sid: str, request: CreateGameRequest) -> GameCreatedReply:
        game = await create_game(self._deps, CreateGame(**request.model_dump(exclude_none=True)))
        return GameCreatedReply(game_id=game.id, room_code=game.room_code)

    async def join_game(self, sid: str, request: JoinGameRequest) -> JoinedReply:
        joined = await join_game(
            self._deps,
            JoinGame(room_code=request.room_code, player_name=request.player_name, socket_id=sid),
        )
        self._seats[sid] = Seat(game_id=joined.game.id, player_id=joined.player_id)
        return JoinedReply(game_id=joined.game.id, player_id=joined.player_id)

    async def rejoin_game(self, sid: str, request: RejoinGameRequest) -> PlayerViewReply:
        rejoined = await rejoin_game(
            self._deps,
            RejoinGame(room_code=request.room_code, player_id=request.player_id, socket_id=sid),
        )
        self._seats[sid] = Seat(game_id=rejoined.game.id, player_id=request.player_id)
        return PlayerViewReply.model_validate(rejoined.view)

    async def leave_game(self, sid: str, request: NoPayload) -> None:
        seat = self._seat(sid)
        await leave_game(self._deps, LeaveGame(game_id=seat.game_id, player_id=seat.player_id))
        del self._seats[sid]

    async def create_team(self, sid: str, request: CreateTeamRequest) -> TeamCreatedReply:
        seat = self._seat(sid)
        new = await create_team(
            self._deps,
            CreateTeam(seat.game_id, seat.player_id, request.team_name, request.color),
        )
        return TeamCreatedReply(team_id=new.team_id)

    async def join_team(self, sid: str, request: JoinTeamRequest) -> None:
        seat = self._seat(sid)
        await join_team(self._deps, JoinTeam(seat.game_id, seat.player_id, request.team_id))

    async def shuffle_teams(self, sid: str, request: NoPayload) -> None:
        seat = self._seat(sid)
        await shuffle_teams(self._deps, ShuffleTeams(seat.game_id, seat.player_id))

    async def start_personality_selection(self, sid: str, request: NoPayload) -> None:
        seat = self._seat(sid)
        await start_personality_selection(
            self._deps, StartPersonalitySelection(seat.game_id, seat.player_id)
        )

    async def assign_personality(self, sid: str, request: PersonalityRequest) -> None:
        seat = self._seat(sid)
        await assign_personality(
            self._deps, AssignPersonality(seat.game_id, seat.player_id, request.personality_id)
        )

    async def submit_prompt(self, sid: str, request: SubmitPromptRequest) -> None:
        seat = self._seat(sid)
        await submit_prompt(self._deps, SubmitPrompt(seat.game_id, seat.player_id, request.prompt))

    async def submit_guess(self, sid: str, request: SubmitGuessRequest) -> None:
        seat = self._seat(sid)
        await submit_guess(self._deps, SubmitGuess(seat.game_id, seat.player_id, request.guess))

    async def pick_winning_guess(self, sid: str, request: PickWinningGuessRequest) -> None:
        seat = self._seat(sid)
        await pick_winning_guess(
            self._deps, PickWinningGuess(seat.game_id, seat.player_id, request.guess_index)
        )

    async def guess_personality(self, sid: str, request: PersonalityRequest) -> None:
        seat = self._seat(sid)
        await guess_personality(
            self._deps, GuessPersonality(seat.game_id, seat.player_id, request.personality_id)
        )

    async def play_again(self, sid: str, request: NoPayload) -> None:
        seat = self._seat(sid)
        await play_again(self._deps, PlayAgain(seat.game_id, seat.player_id))

    async def disconnected(self, sid: str) -> None:
        """Forget the connection. Its player stays in the game, to reconnect later."""
        self._seats.pop(sid, None)

    def _seat(self, sid: str) -> Seat:
        seat = self._seats.get(sid)
        if seat is None:
            raise NotInGameError("Join a game first")
        return seat

    def _route[R: Request](
        self, name: str, request: type[R], handle: Callable[[str, R], Awaitable[Reply | None]]
    ) -> None:
        async def receive(sid: str, payload: object) -> dict[str, object] | None:
            try:
                reply = await handle(sid, request.model_validate(payload or {}))
            except ValidationError as error:
                rejected = _error("invalid_payload", _describe(error), name)
            except NotInGameError as error:
                rejected = _error("not_in_game", str(error), name)
            except GameNotFoundError as error:
                rejected = _error("game_not_found", str(error), name)
            except GameRuleError as error:
                rejected = _error("rule_broken", str(error), name)
            else:
                return _dump(reply)
            body = rejected.model_dump(mode="json")
            await self._realtime.send_message(sid, ERROR, body)
            return body

        self._realtime.on_message(name, receive)


def _error(code: ErrorCode, message: str, request: str) -> ErrorMessage:
    return ErrorMessage(code=code, message=message, request=request)


def _dump(reply: BaseModel | None) -> dict[str, object] | None:
    return None if reply is None else reply.model_dump(mode="json")


def _describe(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in e['loc']) or 'payload'}: {e['msg']}"
        for e in error.errors()
    )
