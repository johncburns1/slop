"""Use cases: other teams guess the prompt, then the acting team judges and the round is scored.

Once the acting team has its script, any player on another team can submit
any number of guesses. A player on the acting team then picks the winning
guess, or says nobody got it, which closes guessing. Finally they guess which
personality wrote their script. That guess is revealed, the round is scored
(see ``round_score_changes``), and the turn passes to the next team. After the
last regular round no new round starts; ending the game is a separate step.
"""

from dataclasses import dataclass

from slop.application.engine import GameDeps, Private, commit, load_game
from slop.domain.errors import GameRuleError
from slop.domain.events import (
    GameEvent,
    GuessAccepted,
    GuessSubmitted,
    NoGuessAccepted,
    PersonalityGuessSubmitted,
    PersonalityRevealed,
    RoundCompleted,
    RoundStarted,
    ScoresUpdated,
)
from slop.domain.game import Game, GameStatus
from slop.domain.personalities import get_personality
from slop.domain.player import Player
from slop.domain.round import Round
from slop.domain.team import Team

# Scoring, from PRODUCT.md.
POINTS_FOR_GUESSING_THE_PROMPT = 1  # to the guessing team whose guess was accepted
POINTS_FOR_BEING_GUESSED = 1  # to the acting team, when its prompt was guessed
POINTS_FOR_NAMING_THE_PERSONALITY = 1  # to the acting team
# Whether the whole room learns the acting team's personality once it has guessed,
# or only the acting team does.
REVEAL_PERSONALITY_TO_ROOM = True


@dataclass(frozen=True)
class SubmitGuess:
    """Command for a player on a guessing team to guess the round's prompt."""

    game_id: str
    player_id: str
    guess: str


@dataclass(frozen=True)
class PickWinningGuess:
    """Command for a player on the acting team to accept a guess.

    ``guess_index`` is the guess's position in the round's guesses, in the
    order they were submitted. None says nobody guessed the prompt.
    """

    game_id: str
    player_id: str
    guess_index: int | None


@dataclass(frozen=True)
class GuessPersonality:
    """Command for a player on the acting team to guess which personality wrote the script."""

    game_id: str
    player_id: str
    personality_id: str


async def submit_guess(deps: GameDeps, command: SubmitGuess) -> Game:
    """Add the guess to the round, and tell the room.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If no round is open for guessing, the player isn't in
            the game or is on the acting team, or the guess is blank
    """
    game = await load_game(deps, command.game_id)
    current = _round_open_for_guessing(game)
    player = _player(game, command.player_id)
    if player.team_id is None:
        raise GameRuleError(f"{player.name} is not on a team")
    if player.team_id == current.acting_team_id:
        raise GameRuleError("The acting team can't guess its own prompt")
    guess = " ".join(command.guess.split())
    if not guess:
        raise GameRuleError("A guess can't be blank")

    return await commit(
        deps,
        game,
        [
            GuessSubmitted(
                game_id=game.id,
                round_number=current.round_number,
                team_id=player.team_id,
                guess=guess,
            )
        ],
    )


async def pick_winning_guess(deps: GameDeps, command: PickWinningGuess) -> Game:
    """Accept the guess (or none), close guessing, and tell the room.

    Points are awarded when the round completes, after the personality guess.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If no round is open for guessing, the player isn't on
            the acting team, or there is no guess at ``guess_index``
    """
    game = await load_game(deps, command.game_id)
    current = _round_open_for_guessing(game)
    _check_player_is_acting(game, current, command.player_id)

    event: GameEvent
    if command.guess_index is None:
        event = NoGuessAccepted(game_id=game.id, round_number=current.round_number)
    else:
        if not 0 <= command.guess_index < len(current.prompt_guesses):
            raise GameRuleError(f"No guess {command.guess_index} in this round")
        event = GuessAccepted(
            game_id=game.id,
            round_number=current.round_number,
            team_id=current.prompt_guesses[command.guess_index].team_id,
            guess_index=command.guess_index,
        )
    return await commit(deps, game, [event])


async def guess_personality(deps: GameDeps, command: GuessPersonality) -> Game:
    """Record the guess, reveal the personality, score and complete the round, and start the next.

    The reveal goes to the room, or only to the acting team when
    ``REVEAL_PERSONALITY_TO_ROOM`` is off. ``RoundCompleted`` carries every
    team's total. The next team's round starts unless this was the last
    regular round.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the round's guesses haven't been judged yet, the
            player isn't on the acting team, or the personality is unknown
    """
    game = await load_game(deps, command.game_id)
    current = _current_round(game)
    if not current.guessing_closed:
        raise GameRuleError("Pick the winning guess, or say nobody got it, first")
    acting = _check_player_is_acting(game, current, command.player_id)
    guessed = get_personality(command.personality_id)
    assert current.script is not None  # guessing only closes once there is a script
    actual = current.script.personality

    changes = round_score_changes(
        acting_team_id=acting.id,
        prompt_winner_team_id=current.prompt_winner_team_id,
        personality_correct=guessed.id == actual,
    )
    totals = {team.id: team.score + changes.get(team.id, 0) for team in game.teams}
    revealed = PersonalityRevealed(
        game_id=game.id, round_number=current.round_number, team_id=acting.id, personality_id=actual
    )
    events: list[GameEvent | Private] = [
        PersonalityGuessSubmitted(
            game_id=game.id, round_number=current.round_number, personality_guess=guessed.id
        ),
        revealed if REVEAL_PERSONALITY_TO_ROOM else Private(revealed, tuple(acting.player_ids)),
        ScoresUpdated(game_id=game.id, round_number=current.round_number, score_changes=changes),
        RoundCompleted(game_id=game.id, round_number=current.round_number, final_scores=totals),
    ]
    next_round = current.round_number + 1
    if next_round < game.get_total_rounds():
        events.append(
            RoundStarted(
                game_id=game.id,
                round_number=next_round,
                acting_team_id=game.acting_team_for(next_round).id,
            )
        )
    return await commit(deps, game, events)


def round_score_changes(
    *, acting_team_id: str, prompt_winner_team_id: str | None, personality_correct: bool
) -> dict[str, int]:
    """Return the points each team earns this round. Teams that earn nothing are left out."""
    changes: dict[str, int] = {}
    if prompt_winner_team_id is not None:
        changes[prompt_winner_team_id] = POINTS_FOR_GUESSING_THE_PROMPT
        changes[acting_team_id] = POINTS_FOR_BEING_GUESSED
    if personality_correct:
        changes[acting_team_id] = changes.get(acting_team_id, 0) + POINTS_FOR_NAMING_THE_PERSONALITY
    return changes


def _current_round(game: Game) -> Round:
    if game.status == GameStatus.PLAYING:
        for candidate in game.rounds:
            if candidate.round_number == game.current_round:
                return candidate
    raise GameRuleError("No round is in progress")


def _round_open_for_guessing(game: Game) -> Round:
    current = _current_round(game)
    if current.script is None:
        raise GameRuleError("The acting team doesn't have its script yet")
    if current.guessing_closed:
        raise GameRuleError("Guessing is over for this round")
    return current


def _player(game: Game, player_id: str) -> Player:
    try:
        return game.get_player(player_id)
    except ValueError:
        raise GameRuleError(f"Player {player_id} is not in this game") from None


def _check_player_is_acting(game: Game, current: Round, player_id: str) -> Team:
    player = _player(game, player_id)
    if player.team_id != current.acting_team_id:
        raise GameRuleError(f"{player.name} is not on the acting team")
    return game.get_team(current.acting_team_id)
