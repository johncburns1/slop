"""Use case: the acting team submits its prompt and gets a script to perform."""

from dataclasses import dataclass

from slop.application.engine import GameDeps, Private, commit, load_game
from slop.domain.ai_personality import AIPersonality
from slop.domain.errors import GameRuleError
from slop.domain.events import (
    GameEvent,
    PromptSubmitted,
    RoleAssigned,
    ScriptGenerated,
    ScriptGenerationFailed,
    ScriptReady,
)
from slop.domain.game import Game
from slop.domain.personalities import get_personality
from slop.domain.round import Round
from slop.domain.script import Script
from slop.domain.team import Team
from slop.ports.llm import LLMError

MAX_PROMPT_WORDS = 6
SCRIPT_ATTEMPTS = 2  # the first try plus one retry


@dataclass(frozen=True)
class SubmitPrompt:
    """Command for a player on the acting team to submit the round's prompt."""

    game_id: str
    player_id: str
    prompt: str


async def submit_prompt(deps: GameDeps, command: SubmitPrompt) -> Game:
    """Generate the round's script from the prompt and hand out one role per acting player.

    Only the acting team receives the prompt, script, and roles; the room is
    told only that the script is ready. If the LLM fails ``SCRIPT_ATTEMPTS``
    times, the round stays waiting for a prompt and only the acting team is
    told (``ScriptGenerationFailed``) so they can submit again.

    Raises:
        GameNotFoundError: If there is no such game
        GameRuleError: If the round isn't waiting for a prompt, the player
            isn't on the acting team, or the prompt isn't 1 to 6 words
    """
    game = await load_game(deps, command.game_id)
    current = _round_waiting_for_prompt(game)
    team = game.get_team(current.acting_team_id)
    _check_player_is_acting(game, team, command.player_id)
    prompt = _normalized_prompt(command.prompt)
    if team.assigned_personality is None:
        raise GameRuleError(f"{team.name} has no personality yet")
    personality = get_personality(team.assigned_personality)

    acting = tuple(team.player_ids)
    script = await _generate(deps, prompt, personality, num_roles=len(acting))
    if script is None:
        failed = ScriptGenerationFailed(
            game_id=game.id, round_number=current.round_number, team_id=team.id
        )
        return await commit(deps, game, [Private(failed, acting)])

    private: list[GameEvent] = [
        PromptSubmitted(
            game_id=game.id,
            round_number=current.round_number,
            prompt=prompt,
            submitted_by=command.player_id,
        ),
        ScriptGenerated(
            game_id=game.id,
            round_number=current.round_number,
            script_content=script.content,
            personality_id=script.personality,
            roles=[
                {"name": role.name, "description": role.description, "lines": role.lines}
                for role in script.roles
            ],
            word_count=script.word_count,
            estimated_duration=script.estimated_duration,
        ),
        *(
            RoleAssigned(
                game_id=game.id,
                round_number=current.round_number,
                player_id=player_id,
                role_name=role.name,
                character_description=role.description,
            )
            for player_id, role in zip(acting, script.roles, strict=True)
        ),
    ]
    ready = ScriptReady(game_id=game.id, round_number=current.round_number, acting_team_id=team.id)
    return await commit(deps, game, [*(Private(e, acting) for e in private), ready])


def _round_waiting_for_prompt(game: Game) -> Round:
    for candidate in game.rounds:
        if candidate.round_number == game.current_round and candidate.prompt is None:
            return candidate
    raise GameRuleError("The round is not waiting for a prompt")


def _check_player_is_acting(game: Game, team: Team, player_id: str) -> None:
    if all(player.id != player_id for player in game.players):
        raise GameRuleError(f"Player {player_id} is not in this game")
    if player_id not in team.player_ids:
        raise GameRuleError(f"Player {player_id} is not on the acting team")


def _normalized_prompt(prompt: str) -> str:
    words = prompt.split()
    if not 1 <= len(words) <= MAX_PROMPT_WORDS:
        raise GameRuleError(f"A prompt must be 1 to {MAX_PROMPT_WORDS} words")
    return " ".join(words)


async def _generate(
    deps: GameDeps, prompt: str, personality: AIPersonality, *, num_roles: int
) -> Script | None:
    """Return a script with exactly ``num_roles`` roles, or None if every attempt failed."""
    for _ in range(SCRIPT_ATTEMPTS):
        try:
            script = await deps.llm.generate_script(prompt, personality, num_roles)
        except LLMError:
            continue
        if len(script.roles) == num_roles:
            return script
    return None
