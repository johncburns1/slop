"""Use case: a player joins a game in the lobby by its room code."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, find_game
from slop.domain.errors import GameRuleError
from slop.domain.events import PlayerJoined
from slop.domain.game import Game, GameStatus

MIN_NAME_LENGTH = 1
MAX_NAME_LENGTH = 20


@dataclass(frozen=True)
class JoinGame:
    """Command to join the game with this room code under a display name."""

    room_code: str
    name: str
    socket_id: str


@dataclass(frozen=True)
class JoinedGame:
    """The game after the join, and the new player's id."""

    game: Game
    player_id: str


async def join_game(deps: GameDeps, command: JoinGame) -> JoinedGame:
    """Add a player to a game in the lobby and put their connection in its room.

    The room code matches in any case. The name is trimmed and must be
    ``MIN_NAME_LENGTH`` to ``MAX_NAME_LENGTH`` characters and unique in the
    game, ignoring case. The new connection joins the room before the event
    is broadcast, so the player hears their own join too.

    Raises:
        GameNotFoundError: If no game has this room code
        GameRuleError: If the game has started or is full, or the name is
            blank, too long, or taken
    """
    game = await find_game(deps, command.room_code.strip().upper())
    name = command.name.strip()
    _check_can_join(game, name)

    event = PlayerJoined(
        game_id=game.id,
        player_id=deps.ids.new_id(),
        player_name=name,
        socket_id=command.socket_id,
    )
    await deps.realtime.join_room(command.socket_id, game.room_code)
    game = await commit(deps, game, [event])
    return JoinedGame(game=game, player_id=event.player_id)


def _check_can_join(game: Game, name: str) -> None:
    if game.status != GameStatus.LOBBY:
        raise GameRuleError("This game has already started")
    if len(game.players) >= game.settings.max_players:
        raise GameRuleError(f"This game is full ({game.settings.max_players} players)")
    if not MIN_NAME_LENGTH <= len(name) <= MAX_NAME_LENGTH:
        raise GameRuleError(f"Name must be {MIN_NAME_LENGTH}-{MAX_NAME_LENGTH} characters")
    if any(player.name.casefold() == name.casefold() for player in game.players):
        raise GameRuleError(f"The name {name} is already taken in this game")
