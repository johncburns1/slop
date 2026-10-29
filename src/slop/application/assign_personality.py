"""Use case: a team secretly picks the AI personality another team will perform with."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, Private, commit, load_game
from slop.domain.errors import GameRuleError
from slop.domain.events import GameEvent, PersonalityAssigned, PersonalityPicked, RoundStarted
from slop.domain.game import Game, GameStatus
from slop.domain.personalities import get_personality
from slop.domain.team import Team

MIN_TEAMS = 2  # with one team, the ring would have it pick for itself


@dataclass(frozen=True)
class AssignPersonality:
    """Command for a player to pick ``personality_id`` on behalf of their team."""

    game_id: str
    player_id: str
    personality_id: str


def target_team(game: Game, picking_team_id: str) -> Team:
    """Return the team that ``picking_team_id`` picks a personality for.

    Teams form a ring in the order they were formed: team ``i`` picks for team
    ``i + 1``, and the last team picks for the first. So every team gets
    exactly one personality and no team picks for itself.
    """
    index = next(i for i, team in enumerate(game.teams) if team.id == picking_team_id)
    return game.teams[(index + 1) % len(game.teams)]


async def assign_personality(deps: GameDeps, command: AssignPersonality) -> Game:
    """Give the picking team's target its personality, and start the game once all have one.

    Only the picking team's players receive the pick (``PersonalityAssigned``);
    the room hears only that the team has picked (``PersonalityPicked``). When
    this pick is the last one, the game starts with the first team acting in
    the first round (``RoundStarted``).

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the game isn't picking personalities or has fewer
            than two teams, the player isn't in the game or on a team, the
            team has already picked, or the personality is unknown
    """
    game = await load_game(deps, command.game_id)
    if game.status != GameStatus.PERSONALITY_SELECTION:
        raise GameRuleError("The game is not picking personalities")
    if len(game.teams) < MIN_TEAMS:
        raise GameRuleError(f"Picking personalities needs at least {MIN_TEAMS} teams")
    picking = _picking_team(game, command.player_id)
    target = target_team(game, picking.id)
    if target.assigned_personality is not None:
        raise GameRuleError(f"{picking.name} has already picked a personality")
    personality = get_personality(command.personality_id)

    assigned = PersonalityAssigned(
        game_id=game.id,
        team_id=target.id,
        personality_id=personality.id,
        assigned_by_team_id=picking.id,
    )
    events: list[GameEvent | Private] = [
        Private(assigned, tuple(picking.player_ids)),
        PersonalityPicked(game_id=game.id, picked_by_team_id=picking.id),
    ]
    still_waiting = [t for t in game.teams if t.assigned_personality is None and t is not target]
    if not still_waiting:
        events.append(
            RoundStarted(
                game_id=game.id,
                round_number=game.current_round,
                acting_team_id=game.get_acting_team().id,
            )
        )
    return await commit(deps, game, events)


def _picking_team(game: Game, player_id: str) -> Team:
    try:
        player = game.get_player(player_id)
    except ValueError:
        raise GameRuleError(f"Player {player_id} is not in this game") from None
    if player.team_id is None:
        raise GameRuleError(f"{player.name} is not on a team")
    return game.get_team(player.team_id)
