"""Use case: a player joins a game in the lobby with its room code."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, find_game
from slop.domain.errors import GameRuleError
from slop.domain.events import PlayerJoined
from slop.domain.game import Game, GameStatus

MAX_NAME_LENGTH = 20


@dataclass(frozen=True)
class JoinGame:
    """Command to join the game with ``room_code`` from the socket ``socket_id``."""

    room_code: str
    player_name: str
    socket_id: str


@dataclass(frozen=True)
class Joined:
    """The game after the join, and the id the new player was given."""

    game: Game
    player_id: str


async def join_game(deps: GameDeps, command: JoinGame) -> Joined:
    """Add a player to the lobby and tell the room, including the new player.

    Room codes match whatever the case, and names are trimmed.

    Raises:
        GameNotFoundError: If no game has this room code
        GameRuleError: If the game has started or is full, or the name is
            blank, too long, or already taken in this game (whatever the case)
    """
    game = await find_game(deps, command.room_code.strip().upper())
    name = command.player_name.strip()
    if game.status != GameStatus.LOBBY:
        raise GameRuleError("This game has already started")
    if len(game.players) >= game.settings.max_players:
        raise GameRuleError("This game is full")
    if not name:
        raise GameRuleError("Name can't be blank")
    if len(name) > MAX_NAME_LENGTH:
        raise GameRuleError(f"Name must be at most {MAX_NAME_LENGTH} characters")
    if any(player.name.casefold() == name.casefold() for player in game.players):
        raise GameRuleError(f"The name {name} is already taken in this game")

    player_id = deps.ids.new_id()
    event = PlayerJoined(
        game_id=game.id, player_id=player_id, player_name=name, socket_id=command.socket_id
    )
    # Join the room first so the new player also hears the broadcast.
    await deps.realtime.join_room(command.socket_id, game.room_code)
    try:
        game = await commit(deps, game, [event])
    except Exception:
        await deps.realtime.leave_room(command.socket_id, game.room_code)
        raise
    return Joined(game=game, player_id=player_id)
