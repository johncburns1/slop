"""Award domain model: a short, funny end-of-game award written by the LLM."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Award:
    """An award for a team or player, such as "Most Unhinged Prompt".

    ``recipient`` is the name of the team or player it goes to, and ``reason``
    a one-line explanation, ideally recalling something that happened.
    """

    title: str
    recipient: str
    reason: str
