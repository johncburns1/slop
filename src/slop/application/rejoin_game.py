"""Use case: a player already in a game comes back on a new connection."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, find_game
from slop.application.player_view import PlayerView, player_view
from slop.domain.errors import GameRuleError
from slop.domain.events import PlayerReconnected
from slop.domain.game import Game


@dataclass(frozen=True)
class RejoinGame:
    """Command for ``player_id`` to rejoin the game with ``room_code`` from ``socket_id``."""

    room_code: str
    player_id: str
    socket_id: str


@dataclass(frozen=True)
class Rejoined:
    """The game after the rejoin, and the player's view of it."""

    game: Game
    view: PlayerView


async def rejoin_game(deps: GameDeps, command: RejoinGame) -> Rejoined:
    """Move the player to their new socket, put it in the room, and return their view.

    Works in any phase of the game. The player keeps their place: this emits
    ``PlayerReconnected``, not ``PlayerJoined``, so later private events reach
    the new socket. Room codes match whatever the case.

    Raises:
        GameNotFoundError: If no game has this room code
        GameRuleError: If the player isn't in the game
    """
    game = await find_game(deps, command.room_code.strip().upper())
    if all(player.id != command.player_id for player in game.players):
        raise GameRuleError(f"Player {command.player_id} is not in this game")

    event = PlayerReconnected(
        game_id=game.id, player_id=command.player_id, socket_id=command.socket_id
    )
    # Join the room first so the player also hears they are back.
    await deps.realtime.join_room(command.socket_id, game.room_code)
    try:
        game = await commit(deps, game, [event])
    except Exception:
        await deps.realtime.leave_room(command.socket_id, game.room_code)
        raise
    return Rejoined(game=game, view=player_view(game, command.player_id))
