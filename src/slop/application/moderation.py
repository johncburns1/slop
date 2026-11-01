"""Content moderation for the use cases: player text before it is accepted.

The game's content setting decides what is allowed (see
``slop.ports.moderation``). AI text is checked where it is generated, in
``submit_prompt`` and ``awards``.
"""

from slop.application.engine import GameDeps
from slop.domain.errors import ContentBlockedError
from slop.domain.game import Game


async def check_player_text(deps: GameDeps, game: Game, text: str, what: str) -> None:
    """Reject ``text``, which a player wants to use as ``what`` (such as "That name").

    Raises:
        ContentBlockedError: If moderation blocks the text for this game
    """
    result = await deps.moderation.check(text, game.settings.content_tone)
    if not result.allowed:
        raise ContentBlockedError(f"{what} isn't allowed in this game. Try something else.")
