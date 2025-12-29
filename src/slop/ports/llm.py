"""LLM port interface.

This port defines the contract for AI language model providers
that generate scripts based on prompts and personalities.
"""

from typing import Protocol

from slop.domain.ai_personality import AIPersonality
from slop.domain.script import Script


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
    ) -> Script:
        """Generate a script based on the given prompt and parameters.

        The script should target ~150 words (~90 seconds spoken) and
        include exactly num_roles character roles with descriptions.

        Args:
            prompt: The 6-word user prompt to base the script on
            personality: The AI personality configuration to use
            num_roles: Number of character roles needed (matches team size)

        Returns:
            A Script object with roles, content, and metadata

        Raises:
            LLMError: If script generation fails after retries
        """
        ...
