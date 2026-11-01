"""Use case: delete every game that has expired, so its room code stops resolving.

Unlike the other use cases this emits no event: history is session-only, so
an expired game's events and snapshot are deleted outright (see
``slop.domain.expiry`` for when that is). The server runs it periodically.
"""

from slop.application.engine import GameDeps
from slop.domain.expiry import ExpiryPolicy, is_expired


async def expire_games(deps: GameDeps, policy: ExpiryPolicy) -> list[str]:
    """Delete the games that have expired by now, and return their ids."""
    now = deps.clock.now()
    expired = [game.id for game in await deps.storage.list_games() if is_expired(game, now, policy)]
    for game_id in expired:
        await deps.storage.delete_game(game_id)
    return expired
