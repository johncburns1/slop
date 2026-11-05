"""Use case: the host removes a player from the game, in any phase.

The removed player hears it privately (``RemovedFromGame``), then the room
gets ``PlayerKicked`` and the player's connection leaves the room. They are off
their team, lose any role in the round in play, and can't rejoin as that
player. In the lobby they can join again as a new player, like anyone else.

A team left with no players drops out of the turn order (see
``slop.domain.game_end``) but keeps its score. What else follows depends on
when the kick happens:

- If it empties the acting team mid-round, or leaves fewer than two teams with
  players, the round ends with no points (``RoundCompleted``) and
  ``finish_or_continue`` moves on: the next team's turn, or the end of the game.
- While teams pick personalities, the ring of picks closes up around an empty
  team. The game ends if fewer than two teams have players, and starts if every
  team still playing now has its personality.
"""

from dataclasses import dataclass

from slop.application.engine import GameDeps, Private, commit, locked_game
from slop.application.finish_or_continue import give_awards_if_finished, move_on
from slop.application.host import check_host
from slop.domain.errors import GameRuleError
from slop.domain.events import (
    GameCompleted,
    GameEvent,
    PlayerKicked,
    PromptRevealed,
    RemovedFromGame,
    RoundCompleted,
    RoundStarted,
)
from slop.domain.game import Game, GameStatus
from slop.domain.game_end import MIN_TEAMS_IN_PLAY, end_of_game, next_regular_team
from slop.domain.player import Player


@dataclass(frozen=True)
class KickPlayer:
    """Command for the host ``player_id`` to remove ``kicked_player_id`` from the game."""

    game_id: str
    player_id: str
    kicked_player_id: str


async def kick_player(deps: GameDeps, command: KickPlayer) -> Game:
    """Remove the player, tell them and the room, and carry the game on without them.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the sender isn't the host, either player isn't in
            the game, or the host tries to remove themself
    """
    async with locked_game(deps, command.game_id) as game:
        host = check_host(game, command.player_id)
        kicked = _player(game, command.kicked_player_id)
        if kicked.id == host.id:
            raise GameRuleError("You can't remove yourself")

        game = await commit(
            deps,
            game,
            [
                Private(RemovedFromGame(game_id=game.id, player_id=kicked.id), (kicked.id,)),
                PlayerKicked(game_id=game.id, player_id=kicked.id),
            ],
        )
        await deps.realtime.leave_room(kicked.socket_id, game.room_code)
        game = await _carry_on(deps, game)
    return await give_awards_if_finished(deps, game)


async def _carry_on(deps: GameDeps, game: Game) -> Game:
    """Emit whatever the game needs now that the player is gone. The caller holds the lock."""
    in_play = game.teams_in_play()
    if game.status == GameStatus.PLAYING:
        current = next((r for r in game.rounds if r.round_number == game.current_round), None)
        acting_gone = current is not None and current.acting_team_id not in {t.id for t in in_play}
        if current is not None and (acting_gone or len(in_play) < MIN_TEAMS_IN_PLAY):
            events: list[GameEvent] = []
            if current.prompt is not None:
                events.append(
                    PromptRevealed(
                        game_id=game.id, round_number=current.round_number, prompt=current.prompt
                    )
                )
            events.append(
                RoundCompleted(
                    game_id=game.id,
                    round_number=current.round_number,
                    final_scores={team.id: team.score for team in game.teams},
                )
            )
            game = await commit(deps, game, events)
            current = None
        return await move_on(deps, game) if current is None else game

    if game.status == GameStatus.PERSONALITY_SELECTION:
        if len(in_play) < MIN_TEAMS_IN_PLAY:
            return await commit(
                deps,
                game,
                [
                    GameCompleted(
                        game_id=game.id,
                        final_scores={team.id: team.score for team in game.teams},
                        winner_team_id=end_of_game(game).winner_team_id,
                    )
                ],
            )
        first = next_regular_team(game)
        if first is not None and all(t.assigned_personality is not None for t in in_play):
            return await commit(
                deps,
                game,
                [
                    RoundStarted(
                        game_id=game.id, round_number=game.current_round, acting_team_id=first.id
                    )
                ],
            )
    return game


def _player(game: Game, player_id: str) -> Player:
    try:
        return game.get_player(player_id)
    except ValueError:
        raise GameRuleError(f"Player {player_id} is not in this game") from None
