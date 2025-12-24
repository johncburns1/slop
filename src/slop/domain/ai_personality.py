"""AIPersonality domain model."""

from dataclasses import dataclass


@dataclass
class AIPersonality:
    """Represents an AI personality configuration for script generation.

    Personalities define the style and tone of generated scripts through
    system prompts and descriptions.
    """

    id: str
    name: str
    description: str
    system_prompt: str
    example_script: str | None = None

    def __post_init__(self) -> None:
        """Validate personality fields."""
        if not self.id:
            raise ValueError("ID cannot be empty")
        if not self.name:
            raise ValueError("Name cannot be empty")
        if not self.system_prompt:
            raise ValueError("System prompt cannot be empty")
