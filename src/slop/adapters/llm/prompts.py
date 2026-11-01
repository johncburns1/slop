"""Prompt text for the Claude LLM adapter, kept in one place so it is easy to edit.

The prompts stay short on purpose: they say what to write and leave comedy and
pacing to the model's judgment. The output's shape is enforced by structured
output (see ``slop.adapters.llm.claude``), so the prompts don't describe JSON.
"""

import json

from slop.domain.ai_personality import AIPersonality
from slop.domain.game import ContentTone
from slop.ports.llm import AWARD_COUNT, GameSummary

SCRIPT_SYSTEM = """\
You write short comic scripts for Slop, a party game. A team of friends performs \
your script out loud, and the other teams try to guess the six-word prompt it came \
from. Make it funny, quick to read aloud, and about 150 words (90 seconds spoken). \
Hint at the prompt without stating it outright.

Give each role a short, memorable name and a one-line description, and give every \
role at least one line. Stage directions have an empty speaker."""

AWARDS_SYSTEM = f"""\
You hand out {AWARD_COUNT} short, funny awards at the end of a game of Slop, a party \
game where teams perform AI-written scripts and the other teams guess the prompt. \
Each award goes to one team or player, named exactly as in the game, and its reason \
is one line that recalls something that really happened: a prompt, a guess, or the \
result. Spread the awards around."""

CONTENT_GUIDANCE: dict[ContentTone, str] = {
    ContentTone.FAMILY: "Keep it family-friendly: no swearing, sex, or gore.",
    ContentTone.ADULT: "Adult humor and mild swearing are fine; nothing hateful or graphic.",
}


def script_request(
    prompt: str, personality: AIPersonality, num_roles: int, content_tone: ContentTone
) -> str:
    """The user message asking for one script."""
    return (
        f"Prompt: {prompt}\n"
        f"Style ({personality.name}): {personality.system_prompt}\n"
        f"Content: {CONTENT_GUIDANCE[content_tone]}\n"
        f"Cast: exactly {num_roles} roles, one per performer."
    )


def awards_request(summary: GameSummary) -> str:
    """The user message asking for the awards, with the game as JSON."""
    game = {
        "teams": [
            {
                "name": team.name,
                "players": list(team.players),
                "score": team.score,
                "ai_personality": team.personality,
            }
            for team in summary.teams
        ],
        "rounds": [
            {
                "acting_team": r.acting_team,
                "prompt": r.prompt,
                "guesses": [
                    {"team": g.team, "guess": g.guess, "correct": g.correct} for g in r.guesses
                ],
            }
            for r in summary.rounds
        ],
        "winner": summary.winner,
    }
    return (
        f"Content: {CONTENT_GUIDANCE[summary.content_tone]}\n"
        f"Write exactly {AWARD_COUNT} awards for this game:\n"
        f"{json.dumps(game)}"
    )
