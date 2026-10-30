"""What one player may see of a game, for a player who (re)connects mid-game.

``player_view`` rebuilds from the game state what the player would have
learned from the events sent to them so far: whatever went to the whole room,
plus what went privately to their team. So:

- Everyone sees the players, teams, scores, settings, and the current round's
  phase and guesses, and which teams have picked a personality.
- Only the acting team's players see the round's prompt, script, and roles.
- A team's own personality is shown only once it has been revealed, after
  the team's first personality guess. The script never names it.
- A team's pick for the next team is shown only to that team.
"""

from dataclasses import dataclass
from typing import Literal

from slop.application.guess_and_score import REVEAL_PERSONALITY_TO_ROOM
from slop.domain.errors import GameRuleError
from slop.domain.game import ContentTone, Game, GameStatus
from slop.domain.player import Player
from slop.domain.round import Round
from slop.domain.script import Script
from slop.domain.team import Team

RoundPhase = Literal["waiting_for_prompt", "guessing", "guessing_personality"]


@dataclass(frozen=True)
class SettingsView:
    rounds_per_team: int
    guess_timer_seconds: int
    max_players_per_team: int
    content_tone: ContentTone
    max_players: int


@dataclass(frozen=True)
class PlayerSummary:
    id: str
    name: str
    team_id: str | None
    is_host: bool


@dataclass(frozen=True)
class TeamView:
    """A team as everyone sees it. ``personality_id`` is None until the viewer may see it."""

    id: str
    name: str
    color: str
    player_ids: tuple[str, ...]
    score: int
    has_picked: bool  # whether this team has picked the next team's personality
    personality_id: str | None


@dataclass(frozen=True)
class PersonalityPick:
    """The personality the viewer's team picked for ``team_id``."""

    team_id: str
    personality_id: str


@dataclass(frozen=True)
class GuessView:
    team_id: str
    guess: str
    accepted: bool


@dataclass(frozen=True)
class RoleView:
    """A role in the script, and the acting player playing it (None if nobody yet)."""

    name: str
    description: str
    lines: tuple[str, ...]
    player_id: str | None


@dataclass(frozen=True)
class ScriptView:
    content: str
    roles: tuple[RoleView, ...]
    estimated_duration: int
    word_count: int


@dataclass(frozen=True)
class RoundView:
    """The round in progress. ``prompt`` and ``script`` are None unless the viewer is acting."""

    round_number: int
    acting_team_id: str
    phase: RoundPhase
    guesses: tuple[GuessView, ...]
    prompt_winner_team_id: str | None
    prompt: str | None
    script: ScriptView | None


@dataclass(frozen=True)
class PlayerView:
    """Everything ``player_id`` may see of the game right now."""

    game_id: str
    room_code: str
    status: GameStatus
    settings: SettingsView
    player_id: str
    team_id: str | None
    players: tuple[PlayerSummary, ...]
    teams: tuple[TeamView, ...]
    current_round: RoundView | None  # None outside a round
    my_pick: PersonalityPick | None


def player_view(game: Game, player_id: str) -> PlayerView:
    """Return the game as ``player_id`` may see it.

    Raises:
        GameRuleError: If the player isn't in the game
    """
    viewer = _player(game, player_id)
    picked_by_viewer = next(
        (
            t
            for t in game.teams
            if viewer.team_id is not None and t.personality_assigned_by == viewer.team_id
        ),
        None,
    )
    return PlayerView(
        game_id=game.id,
        room_code=game.room_code,
        status=game.status,
        settings=SettingsView(
            rounds_per_team=game.settings.rounds_per_team,
            guess_timer_seconds=game.settings.guess_timer_seconds,
            max_players_per_team=game.settings.max_players_per_team,
            content_tone=game.settings.content_tone,
            max_players=game.settings.max_players,
        ),
        player_id=viewer.id,
        team_id=viewer.team_id,
        players=tuple(
            PlayerSummary(id=p.id, name=p.name, team_id=p.team_id, is_host=p.is_creator)
            for p in game.players
        ),
        teams=tuple(_team_view(game, team, viewer) for team in game.teams),
        current_round=_round_view(game, viewer),
        my_pick=(
            PersonalityPick(picked_by_viewer.id, picked_by_viewer.assigned_personality)
            if picked_by_viewer is not None and picked_by_viewer.assigned_personality is not None
            else None
        ),
    )


def _player(game: Game, player_id: str) -> Player:
    try:
        return game.get_player(player_id)
    except ValueError:
        raise GameRuleError(f"Player {player_id} is not in this game") from None


def _team_view(game: Game, team: Team, viewer: Player) -> TeamView:
    revealed = any(
        r.acting_team_id == team.id and r.personality_guess is not None for r in game.rounds
    )
    visible = revealed and (REVEAL_PERSONALITY_TO_ROOM or viewer.team_id == team.id)
    return TeamView(
        id=team.id,
        name=team.name,
        color=team.color,
        player_ids=tuple(team.player_ids),
        score=team.score,
        has_picked=any(t.personality_assigned_by == team.id for t in game.teams),
        personality_id=team.assigned_personality if visible else None,
    )


def _round_view(game: Game, viewer: Player) -> RoundView | None:
    if game.status != GameStatus.PLAYING:
        return None
    current = next((r for r in game.rounds if r.round_number == game.current_round), None)
    if current is None:
        return None
    acting = viewer.team_id == current.acting_team_id
    return RoundView(
        round_number=current.round_number,
        acting_team_id=current.acting_team_id,
        phase=_phase(current),
        guesses=tuple(GuessView(g.team_id, g.guess, g.accepted) for g in current.prompt_guesses),
        prompt_winner_team_id=current.prompt_winner_team_id,
        prompt=current.prompt if acting else None,
        script=_script_view(current, current.script) if acting and current.script else None,
    )


def _phase(current: Round) -> RoundPhase:
    if current.script is None:
        return "waiting_for_prompt"
    if not current.guessing_closed:
        return "guessing"
    return "guessing_personality"


def _script_view(current: Round, script: Script) -> ScriptView:
    players_by_role = {index: player_id for player_id, index in current.role_assignments.items()}
    return ScriptView(
        content=script.content,
        roles=tuple(
            RoleView(
                name=role.name,
                description=role.description,
                lines=tuple(role.lines),
                player_id=players_by_role.get(index),
            )
            for index, role in enumerate(script.roles)
        ),
        estimated_duration=script.estimated_duration,
        word_count=script.word_count,
    )
