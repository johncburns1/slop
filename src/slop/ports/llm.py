"""LLM port interface.

This port defines the contract for AI language model providers
that generate scripts based on prompts and personalities, and the
end-of-game awards based on a summary of the game.
"""

from dataclasses import dataclass
from typing import Protocol

from slop.domain.ai_personality import AIPersonality
from slop.domain.award import Award
from slop.domain.game import ContentTone
from slop.domain.script import Script

AWARD_COUNT = 3


class LLMError(Exception):
    """Generation failed: the provider errored or returned unusable output."""


@dataclass(frozen=True)
class TeamSummary:
    """A team at the end of the game. ``personality`` is its personality's display name."""

    name: str
    players: tuple[str, ...]  # player names
    score: int
    personality: str | None


@dataclass(frozen=True)
class GuessSummary:
    """A guess at a round's prompt, by team name. ``correct`` if the acting team accepted it."""

    team: str
    guess: str
    correct: bool


@dataclass(frozen=True)
class RoundSummary:
    """What happened in one round, by name. ``personality_guess`` is a display name."""

    number: int
    acting_team: str
    prompt: str | None
    guesses: tuple[GuessSummary, ...]
    personality_guess: str | None
    personality_correct: bool


@dataclass(frozen=True)
class GameSummary:
    """A finished game as the LLM sees it: names, not ids. ``winner`` is None for a draw."""

    content_tone: ContentTone
    teams: tuple[TeamSummary, ...]
    rounds: tuple[RoundSummary, ...]
    winner: str | None

    def names(self) -> frozenset[str]:
        """Every team and player name, which is who an award may go to."""
        return frozenset(name for team in self.teams for name in (team.name, *team.players))


class LLMPort(Protocol):
    """Interface for LLM providers that generate game scripts.

    Implementations provide script generation using various
    AI language models (OpenAI, Anthropic, etc.) with personality-based
    system prompts and validation.
    """

    async def generate_script(
        self,
        prompt: str,
        personality: AIPersonality,
        num_roles: int,
        content_tone: ContentTone,
    ) -> Script:
        """Generate a script based on the given prompt and parameters.

        The script should target ~150 words (~90 seconds spoken),
        include exactly num_roles character roles with descriptions,
        and suit content_tone.

        Args:
            prompt: The 6-word user prompt to base the script on
            personality: The AI personality configuration to use
            num_roles: Number of character roles needed (matches team size)
            content_tone: The game's content setting, which the script must suit

        Returns:
            A Script object with roles, content, and metadata

        Raises:
            LLMError: If script generation fails after retries
        """
        ...

    async def generate_awards(self, summary: GameSummary) -> list[Award]:
        """Write ``AWARD_COUNT`` short, funny awards for a finished game.

        Each award has a title, a recipient (a team or player name from
        ``summary.names()``), and a one-line reason that recalls a real
        moment from the game, such as a prompt or a guess. The awards suit
        ``summary.content_tone``.

        Raises:
            LLMError: If the awards can't be generated
        """
        ...
