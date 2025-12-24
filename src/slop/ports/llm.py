"""LLM port interface.

This port defines the contract for AI language model providers
that generate scripts based on prompts and personalities.
"""

from typing import Protocol

from slop.domain.ai_personality import AIPersonality
from slop.domain.script import Script


class LLMPort(Protocol):
    """Interface for LLM providers that generate game scripts.

    Implementations should provide script generation using various
    AI language models (OpenAI, Anthropic, etc.).
    """

    async def generate_script(
        self,
        prompt: str,
        personality: AIPersonality,
        num_roles: int,
        content_tone: str,
    ) -> Script:
        """Generate a script based on the given prompt and parameters.

        Args:
            prompt: The 6-word user prompt to base the script on
            personality: The AI personality configuration to use
            num_roles: Number of character roles needed (matches team size)
            content_tone: Content tone ("family" or "adult")

        Returns:
            A Script object with roles, content, and metadata

        Raises:
            LLMError: If script generation fails
        """
        ...
