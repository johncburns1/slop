"""Script and Role domain models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Role:
    """Represents a character role in a script.

    Each role has a name, description, and optional dialogue lines.
    """

    name: str
    description: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Script:
    """Represents an AI-generated script for a performance.

    Scripts contain the full content, character roles, and metadata
    about the generation process.
    """

    content: str
    roles: list[Role]
    personality: str
    estimated_duration: int = 0
    word_count: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate and calculate derived fields after initialization."""
        if not self.roles:
            raise ValueError("Script must have at least one role")

        # Auto-calculate word count if not provided
        if self.word_count == 0:
            self.word_count = len(self.content.split())

        # Auto-calculate estimated duration if not provided
        # Assume ~150 words per minute for spoken content
        if self.estimated_duration == 0:
            words_per_second = 150 / 60  # ~2.5 words per second
            self.estimated_duration = int(self.word_count / words_per_second)

    def get_role_count(self) -> int:
        """Get the number of roles in this script."""
        return len(self.roles)
