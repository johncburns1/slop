"""Use cases: players form teams in the lobby, then the host moves the game on.

A player creates a team (and is put on it) or joins one, which switches them
off any team they were on. The host can instead shuffle everyone into random,
balanced teams, and moves on to personality selection once the teams are
ready. The host is the player who created the game (the first to join).
"""

import random
from dataclasses import dataclass

from slop.application.engine import GameDeps, commit, load_game
from slop.domain.errors import GameRuleError
from slop.domain.events import (
    GameEvent,
    PersonalitySelectionStarted,
    PlayerJoinedTeam,
    TeamDisbanded,
    TeamFormed,
)
from slop.domain.game import Game, GameStatus
from slop.domain.player import Player

MAX_TEAM_NAME_LENGTH = 20
MIN_TEAMS = 2
# Shuffled teams are named "Team 1", "Team 2", ... and colored in this order.
SHUFFLE_COLORS = (
    "#E53935",
    "#1E88E5",
    "#43A047",
    "#FDD835",
    "#8E24AA",
    "#FB8C00",
    "#00ACC1",
    "#D81B60",
    "#6D4C41",
    "#3949AB",
    "#7CB342",
    "#546E7A",
)


@dataclass(frozen=True)
class CreateTeam:
    """Command for ``player_id`` to create a team and join it."""

    game_id: str
    player_id: str
    team_name: str
    color: str


@dataclass(frozen=True)
class NewTeam:
    """The game after the team was created, and the id the team was given."""

    game: Game
    team_id: str


@dataclass(frozen=True)
class JoinTeam:
    """Command for ``player_id`` to join ``team_id``, leaving any team they're on."""

    game_id: str
    player_id: str
    team_id: str


@dataclass(frozen=True)
class ShuffleTeams:
    """Command for the host to deal everyone into random teams.

    Pass ``seed`` for a repeatable shuffle; None shuffles differently each time.
    """

    game_id: str
    player_id: str
    seed: int | None = None


@dataclass(frozen=True)
class StartPersonalitySelection:
    """Command for the host to close the lobby and move on to personalities."""

    game_id: str
    player_id: str


async def create_team(deps: GameDeps, command: CreateTeam) -> NewTeam:
    """Create a team with the player on it, and tell the room.

    Names and colors are trimmed, and must be unique whatever the case.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the game has left the lobby, the player isn't in it,
            or the name or color is blank, too long, or already taken
    """
    game = await load_game(deps, command.game_id)
    player = _lobby_player(game, command.player_id)
    name = command.team_name.strip()
    color = command.color.strip()
    if not name:
        raise GameRuleError("Team name can't be blank")
    if len(name) > MAX_TEAM_NAME_LENGTH:
        raise GameRuleError(f"Team name must be at most {MAX_TEAM_NAME_LENGTH} characters")
    if any(team.name.casefold() == name.casefold() for team in game.teams):
        raise GameRuleError(f"The team name {name} is already taken in this game")
    if not color:
        raise GameRuleError("Team color can't be blank")
    if any(team.color.casefold() == color.casefold() for team in game.teams):
        raise GameRuleError(f"The color {color} is already taken in this game")

    team_id = deps.ids.new_id()
    game = await commit(
        deps,
        game,
        [
            TeamFormed(game_id=game.id, team_id=team_id, team_name=name, color=color),
            PlayerJoinedTeam(game_id=game.id, player_id=player.id, team_id=team_id),
        ],
    )
    return NewTeam(game=game, team_id=team_id)


async def join_team(deps: GameDeps, command: JoinTeam) -> Game:
    """Put the player on the team (moving them off their old one), and tell the room.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the game has left the lobby, the player isn't in it,
            or the team doesn't exist, is full, or is already theirs
    """
    game = await load_game(deps, command.game_id)
    player = _lobby_player(game, command.player_id)
    team = next((t for t in game.teams if t.id == command.team_id), None)
    if team is None:
        raise GameRuleError("No such team in this game")
    if player.team_id == team.id:
        raise GameRuleError(f"You are already on {team.name}")
    if team.is_full():
        raise GameRuleError(f"{team.name} is full")

    return await commit(
        deps, game, [PlayerJoinedTeam(game_id=game.id, player_id=player.id, team_id=team.id)]
    )


async def shuffle_teams(deps: GameDeps, command: ShuffleTeams) -> Game:
    """Replace every team with the fewest random teams that fit everyone, and tell the room.

    There are always at least ``MIN_TEAMS`` teams, and their sizes differ by
    at most one.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the game has left the lobby, the player isn't the
            host, or there are too few players for ``MIN_TEAMS`` teams
    """
    game = await load_game(deps, command.game_id)
    _check_host(_lobby_player(game, command.player_id))
    if len(game.players) < MIN_TEAMS:
        raise GameRuleError(f"Shuffling needs at least {MIN_TEAMS} players")

    per_team = game.settings.max_players_per_team
    team_count = max(MIN_TEAMS, -(-len(game.players) // per_team))
    player_ids = [player.id for player in game.players]
    random.Random(command.seed).shuffle(player_ids)
    team_ids = [deps.ids.new_id() for _ in range(team_count)]

    events: list[GameEvent] = [TeamDisbanded(game_id=game.id, team_id=t.id) for t in game.teams]
    events += [
        TeamFormed(
            game_id=game.id,
            team_id=team_id,
            team_name=f"Team {number}",
            color=SHUFFLE_COLORS[(number - 1) % len(SHUFFLE_COLORS)],
        )
        for number, team_id in enumerate(team_ids, start=1)
    ]
    # Deal the shuffled players round the teams like cards, so sizes stay balanced.
    events += [
        PlayerJoinedTeam(game_id=game.id, player_id=player_id, team_id=team_ids[i % team_count])
        for i, player_id in enumerate(player_ids)
    ]
    return await commit(deps, game, events)


async def start_personality_selection(deps: GameDeps, command: StartPersonalitySelection) -> Game:
    """Close the lobby and move on to personality selection, and tell the room.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the game has left the lobby, the player isn't the
            host, there are fewer than ``MIN_TEAMS`` teams, a player has no
            team, or a team has no players
    """
    game = await load_game(deps, command.game_id)
    _check_host(_lobby_player(game, command.player_id))
    _check_teams_ready(game)

    return await commit(deps, game, [PersonalitySelectionStarted(game_id=game.id)])


def _lobby_player(game: Game, player_id: str) -> Player:
    player = next((p for p in game.players if p.id == player_id), None)
    if player is None:
        raise GameRuleError("That player is not in this game")
    if game.status != GameStatus.LOBBY:
        raise GameRuleError("Teams can only change in the lobby")
    return player


def _check_host(player: Player) -> None:
    if not player.is_creator:
        raise GameRuleError("Only the host can do that")


def _check_teams_ready(game: Game) -> None:
    if len(game.teams) < MIN_TEAMS:
        raise GameRuleError(f"You need at least {MIN_TEAMS} teams")
    unassigned = [p.name for p in game.players if p.team_id is None]
    if unassigned:
        raise GameRuleError(f"Not on a team yet: {', '.join(unassigned)}")
    empty = [t.name for t in game.teams if not t.player_ids]
    if empty:
        raise GameRuleError(f"Teams with no players: {', '.join(empty)}")
