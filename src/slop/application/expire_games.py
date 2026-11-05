"""Use case: delete every game that has expired, so its room code stops resolving.

Unlike the other use cases this emits no event: history is session-only, so
an expired game's events and snapshot are deleted outright (see
``slop.domain.expiry`` for when that is). The server runs it periodically.
"""

from slop.application.engine import GameDeps
from slop.domain.expiry import ExpiryPolicy, is_expired


async def expire_games(deps: GameDeps, policy: ExpiryPolicy) -> list[str]:
    """Delete the games that have expired by now, and return their ids.

    Each game is checked again under its lock, so an event that arrives just
    in time keeps it alive, and a command that was waiting finds it gone.
    """
    now = deps.clock.now()
    candidates = [g.id for g in await deps.storage.list_games() if is_expired(g, now, policy)]
    expired = []
    for game_id in candidates:
        async with deps.locks.hold(game_id):
            game = await deps.storage.get_snapshot(game_id)
            if game is not None and is_expired(game, now, policy):
                await deps.storage.delete_game(game_id)
                expired.append(game_id)
    return expired
