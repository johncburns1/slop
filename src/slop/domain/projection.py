"""Rebuild game state from domain events.

``apply_event`` is the only place that turns an event into a state change, and
``replay`` folds a whole log through it. Both are pure: the input game is never
mutated. Use cases emit events and let this module apply them, so a snapshot
and a replay of the same log always agree.

To add an event type, define it in ``slop.domain.events`` and add a ``case``
to ``apply_event``.
"""

from collections.abc import Iterable
from copy import deepcopy

from slop.domain.events import (
    GameCompleted,
    GameCreated,
    GameEvent,
    GameRestarted,
    GuessAccepted,
    GuessSubmitted,
    NoGuessAccepted,
    PersonalityAssigned,
    PersonalityGuessSubmitted,
    PersonalityPicked,
    PersonalityRevealed,
    PersonalitySelectionStarted,
    PlayerJoined,
    PlayerJoinedTeam,
    PlayerLeft,
    PlayerReconnected,
    PromptSubmitted,
    RoleAssigned,
    RoundCompleted,
    RoundStarted,
    ScoresUpdated,
    ScriptGenerated,
    ScriptGenerationFailed,
    ScriptReady,
    TeamDisbanded,
    TeamFormed,
    TiebreakerStarted,
)
from slop.domain.game import ContentTone, Game, GameSettings, GameStatus, Tiebreaker
from slop.domain.player import Player
from slop.domain.round import Guess, Round
from slop.domain.script import Role, Script
from slop.domain.team import Team


class ProjectionError(Exception):
    """An event can't be applied to the game, so the event log is inconsistent.

    This is a bug or corrupt data, not a rejected command: use cases check
    the rules (raising ``GameRuleError``) before they emit anything.
    """


def replay(events: Iterable[GameEvent]) -> Game:
    """Rebuild a game from its full event log, which must start with ``GameCreated``."""
    game: Game | None = None
    for event in events:
        game = apply_event(game, event)
    if game is None:
        raise ProjectionError("Cannot replay an empty log: it must start with GameCreated")
    return game


def apply_event(game: Game | None, event: GameEvent) -> Game:
    """Return the game as it is after ``event``. ``game`` is None only for ``GameCreated``."""
    if isinstance(event, GameCreated):
        if game is not None:
            raise ProjectionError(f"Game {game.id} already exists")
        return _created(event)
    if game is None:
        raise ProjectionError(f"{event.event_type} before GameCreated")
    if event.game_id != game.id:
        raise ProjectionError(f"Event for game {event.game_id} applied to game {game.id}")

    game = deepcopy(game)
    match event:
        case PlayerJoined():
            game.add_player(
                Player(
                    id=event.player_id,
                    name=event.player_name,
                    socket_id=event.socket_id,
                    is_creator=not game.players,
                    joined_at=event.timestamp,
                )
            )
        case PlayerReconnected():
            _player(game, event.player_id).update_socket_id(event.socket_id)
        case PlayerLeft():
            player = _player(game, event.player_id)
            if player.team_id is not None:
                _team(game, player.team_id).remove_player(player.id)
            game.remove_player(player.id)
        case TeamFormed():
            game.add_team(
                Team(
                    id=event.team_id,
                    name=event.team_name,
                    color=event.color,
                    max_players=game.settings.max_players_per_team,
                )
            )
        case PlayerJoinedTeam():
            player = _player(game, event.player_id)
            team = _team(game, event.team_id)
            if player.team_id is not None:
                _team(game, player.team_id).remove_player(player.id)
            team.add_player(player.id)
            player.assign_to_team(team.id)
        case TeamDisbanded():
            team = _team(game, event.team_id)
            for player_id in team.player_ids:
                _player(game, player_id).remove_from_team()
            game.remove_team(team.id)
        case PersonalitySelectionStarted():
            if game.status != GameStatus.LOBBY:
                raise ProjectionError(f"Game {game.id} is not in the lobby")
            game.set_personality_selection_phase()
        case PersonalityAssigned():
            _team(game, event.team_id).assign_personality(
                event.personality_id, assigned_by=event.assigned_by_team_id
            )
        case PersonalityPicked():
            # Notification only: the pick itself is in PersonalityAssigned.
            _team(game, event.picked_by_team_id)
        case RoundStarted():
            game.rounds.append(
                Round(
                    id=f"round-{event.round_number}",
                    round_number=event.round_number,
                    acting_team_id=event.acting_team_id,
                    timestamp=event.timestamp,
                )
            )
            game.current_round = event.round_number
            game.status = GameStatus.PLAYING
        case PromptSubmitted():
            current = _round(game, event.round_number)
            current.prompt = event.prompt
            current.submitted_by = event.submitted_by
        case ScriptGenerated():
            _round(game, event.round_number).script = Script(
                content=event.script_content,
                roles=[
                    Role(
                        name=role["name"],
                        description=role["description"],
                        lines=list(role.get("lines", [])),
                    )
                    for role in event.roles
                ],
                personality=event.personality_id,
                estimated_duration=event.estimated_duration,
                word_count=event.word_count,
                generated_at=event.timestamp,
            )
        case ScriptGenerationFailed() | ScriptReady():
            # Notifications only: the round's state is unchanged.
            _round(game, event.round_number)
        case RoleAssigned():
            current = _round(game, event.round_number)
            role_names = [role.name for role in current.script.roles] if current.script else []
            if event.role_name not in role_names:
                raise ProjectionError(
                    f"Role {event.role_name} is not in round {event.round_number}'s script"
                )
            current.role_assignments[event.player_id] = role_names.index(event.role_name)
        case GuessSubmitted():
            _round(game, event.round_number).add_guess(
                Guess(
                    team_id=event.team_id, guess=event.guess, timestamp=event.timestamp.timestamp()
                )
            )
        case GuessAccepted():
            current = _round(game, event.round_number)
            current.set_prompt_winner(event.team_id)
            if event.guess_index is not None:
                _accepted_guess(current, event.guess_index, event.team_id).accept()
            else:
                team_guesses = [g for g in current.prompt_guesses if g.team_id == event.team_id]
                if team_guesses:
                    team_guesses[-1].accept()
        case NoGuessAccepted():
            _round(game, event.round_number).close_guessing()
        case PersonalityGuessSubmitted():
            current = _round(game, event.round_number)
            current.set_personality_guess(event.personality_guess)
            current.check_personality_guess()
        case PersonalityRevealed():
            # Notification only: the guess and its result are in PersonalityGuessSubmitted.
            _team(game, event.team_id)
            _round(game, event.round_number)
        case ScoresUpdated():
            current = _round(game, event.round_number)
            for team_id, points in event.score_changes.items():
                current.add_score_to_team(team_id, points)
                _team(game, team_id).add_score(points)
        case RoundCompleted():
            _round(game, event.round_number)
            _set_scores(game, event.final_scores)
            game.current_round = event.round_number + 1
        case TiebreakerStarted():
            for team_id in event.team_ids:
                _team(game, team_id)
            game.tiebreaker = Tiebreaker(
                cycle=event.cycle, team_ids=list(event.team_ids), first_round=event.first_round
            )
        case GameCompleted():
            _set_scores(game, event.final_scores)
            game.finish()
        case GameRestarted():
            if game.status != GameStatus.FINISHED:
                raise ProjectionError(f"Game {game.id} has not finished")
            for team in game.teams:
                team.score = 0
                team.assigned_personality = None
                team.personality_assigned_by = None
            game.rounds = []
            game.current_round = 0
            game.tiebreaker = None
            game.set_personality_selection_phase()
        case _:
            raise ProjectionError(f"No projection for event type {event.event_type}")
    return game


def _created(event: GameCreated) -> Game:
    return Game(
        id=event.game_id,
        room_code=event.room_code,
        settings=GameSettings(
            rounds_per_team=event.rounds_per_team,
            guess_timer_seconds=event.guess_timer_seconds,
            max_players_per_team=event.max_players_per_team,
            content_tone=ContentTone(event.content_tone),
            max_players=event.max_players,
        ),
        created_at=event.timestamp,
    )


def _player(game: Game, player_id: str) -> Player:
    try:
        return game.get_player(player_id)
    except ValueError as error:
        raise ProjectionError(str(error)) from error


def _team(game: Game, team_id: str) -> Team:
    try:
        return game.get_team(team_id)
    except ValueError as error:
        raise ProjectionError(str(error)) from error


def _round(game: Game, round_number: int) -> Round:
    for candidate in game.rounds:
        if candidate.round_number == round_number:
            return candidate
    raise ProjectionError(f"Round {round_number} has not started")


def _accepted_guess(current: Round, guess_index: int, team_id: str) -> Guess:
    if not 0 <= guess_index < len(current.prompt_guesses):
        raise ProjectionError(f"Round {current.round_number} has no guess {guess_index}")
    guess = current.prompt_guesses[guess_index]
    if guess.team_id != team_id:
        raise ProjectionError(f"Guess {guess_index} is not from team {team_id}")
    return guess


def _set_scores(game: Game, scores: dict[str, int]) -> None:
    for team_id, score in scores.items():
        _team(game, team_id).score = score
