"""Use case: a host creates a game and gets a room code to share."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, commit
from slop.domain.events import GameCreated
from slop.domain.game import ContentTone, Game, GameSettings

ROOM_CODE_ATTEMPTS = 20


class RoomCodesExhaustedError(Exception):
    """No unused room code was found after ``ROOM_CODE_ATTEMPTS`` tries."""


@dataclass(frozen=True)
class CreateGame:
    """Command to create a game. Anything left out uses the default setting."""

    content_tone: ContentTone
    rounds_per_team: int = 3
    guess_timer_seconds: int = 60
    max_players_per_team: int = 3
    max_players: int = 12


async def create_game(deps: GameDeps, command: CreateGame) -> Game:
    """Create a game in the lobby with an unused room code, and return it.

    Raises:
        GameRuleError: If the settings are not playable
        RoomCodesExhaustedError: If every candidate room code was taken
    """
    settings = GameSettings(
        rounds_per_team=command.rounds_per_team,
        guess_timer_seconds=command.guess_timer_seconds,
        max_players_per_team=command.max_players_per_team,
        content_tone=command.content_tone,
        max_players=command.max_players,
    )
    settings.check()
    room_code = await _unused_room_code(deps)

    event = GameCreated(
        game_id=deps.ids.new_id(),
        room_code=room_code,
        content_tone=settings.content_tone.value,
        max_players=settings.max_players,
        rounds_per_team=settings.rounds_per_team,
        guess_timer_seconds=settings.guess_timer_seconds,
        max_players_per_team=settings.max_players_per_team,
    )
    return await commit(deps, None, [event])


async def _unused_room_code(deps: GameDeps) -> str:
    for _ in range(ROOM_CODE_ATTEMPTS):
        code = deps.ids.new_room_code()
        if await deps.storage.get_game_by_room_code(code) is None:
            return code
    raise RoomCodesExhaustedError(f"No unused room code after {ROOM_CODE_ATTEMPTS} attempts")
