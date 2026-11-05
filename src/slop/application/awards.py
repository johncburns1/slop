"""End-of-game awards: the LLM writes a few funny awards once a game has ended.

``finish_or_continue`` calls ``give_awards`` straight after ``GameCompleted``.
The LLM gets a ``GameSummary`` built here from the game, with teams and
players by name, never the domain objects themselves. Awards are a bonus: if
the LLM fails or writes something unusable, the game just ends without them.
Each award is moderated before it is shown, and one that is blocked is dropped.
"""

from slop.application.engine import GameDeps, commit, locked_game
from slop.domain.award import Award
from slop.domain.events import AwardsGiven
from slop.domain.game import ContentTone, Game, GameStatus
from slop.domain.personalities import PERSONALITIES
from slop.domain.round import Round
from slop.ports.llm import (
    AWARD_COUNT,
    GameSummary,
    GuessSummary,
    LLMError,
    RoundSummary,
    TeamSummary,
)


async def give_awards(deps: GameDeps, game: Game) -> Game:
    """Ask the LLM for awards for the finished ``game`` and give them to the room.

    Emits ``AwardsGiven`` only if the LLM returns ``AWARD_COUNT`` awards, each
    filled in and going to a team or player in the game, and the game is still
    finished with no awards once they arrive. Awards that moderation blocks are
    left out of it, and if that leaves none it isn't emitted either. When
    nothing is emitted, nobody is told. Returns the game as it is afterwards.
    """
    summary = summarize(game)
    try:
        awards = await deps.llm.generate_awards(summary)
    except LLMError:
        return game
    if not _usable(awards, summary):
        return game
    awards = [award for award in awards if await _allowed(deps, award, summary.content_tone)]
    if not awards:
        return game

    # The LLM takes a while, so pick up anything that happened meanwhile.
    async with locked_game(deps, game.id) as game:
        if game.status != GameStatus.FINISHED or game.awards:
            return game
        return await commit(deps, game, [AwardsGiven(game_id=game.id, awards=awards)])


def summarize(game: Game) -> GameSummary:
    """The game as the LLM sees it: who played, what was prompted and guessed, and the scores."""
    team_names = {team.id: team.name for team in game.teams}
    players = {player.id: player.name for player in game.players}
    top = max((team.score for team in game.teams), default=0)
    leaders = [team.name for team in game.teams if team.score == top]
    return GameSummary(
        content_tone=game.settings.content_tone,
        teams=tuple(
            TeamSummary(
                name=team.name,
                players=tuple(players[p] for p in team.player_ids if p in players),
                score=team.score,
                personality=_personality_name(team.assigned_personality),
            )
            for team in game.teams
        ),
        rounds=tuple(
            _round_summary(r, team_names) for r in game.rounds if r.acting_team_id in team_names
        ),
        winner=leaders[0] if len(leaders) == 1 else None,
    )


def _round_summary(current: Round, team_names: dict[str, str]) -> RoundSummary:
    return RoundSummary(
        number=current.round_number,
        acting_team=team_names[current.acting_team_id],
        prompt=current.prompt,
        guesses=tuple(
            GuessSummary(team=team_names[g.team_id], guess=g.guess, correct=g.accepted)
            for g in current.prompt_guesses
            if g.team_id in team_names
        ),
        personality_guess=_personality_name(current.personality_guess),
        personality_correct=current.personality_correct,
    )


def _personality_name(personality_id: str | None) -> str | None:
    if personality_id is None:
        return None
    personality = PERSONALITIES.get(personality_id)
    return personality.name if personality is not None else personality_id


async def _allowed(deps: GameDeps, award: Award, tone: ContentTone) -> bool:
    shown = "\n".join((award.title, award.recipient, award.reason))
    return (await deps.moderation.check(shown, tone)).allowed


def _usable(awards: list[Award], summary: GameSummary) -> bool:
    names = summary.names()
    return len(awards) == AWARD_COUNT and all(
        award.title.strip() and award.reason.strip() and award.recipient in names
        for award in awards
    )
