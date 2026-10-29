"""Deterministic stand-in for a real LLM provider.

Builds believable scripts from fixed word banks, seeded by the inputs, so the
same prompt, personality, and role count always give the same script. It makes
no network calls and costs nothing, which makes it suitable for local play,
tests, and validation environments.
"""

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from slop.domain.ai_personality import AIPersonality
from slop.domain.script import Role, Script

if TYPE_CHECKING:
    from slop.ports.llm import LLMPort

# A fixed timestamp keeps generated scripts fully comparable across calls.
GENERATED_AT = datetime(2026, 1, 1, tzinfo=UTC)

TARGET_WORDS = 150

CHARACTERS: tuple[tuple[str, str], ...] = (
    ("Detective Mallory", "A weary investigator who has seen too much"),
    ("Aunt Bernadette", "A nosy relative with strong opinions"),
    ("Captain Fizz", "A self-appointed leader with no actual authority"),
    ("Doctor Plum", "A scientist whose experiments rarely go to plan"),
    ("The Narrator", "Explains everything, often incorrectly"),
    ("Gary", "An ordinary guy who keeps getting dragged into this"),
    ("Madame Vex", "A fortune teller who is wrong with total confidence"),
    ("Officer Crumb", "A rule-follower who is terrible at following rules"),
    ("Baroness Pickle", "Old money, new problems"),
    ("Intern Josh", "Eager, underpaid, and secretly in charge"),
    ("Grandpa Moss", "Tells long stories that are somehow relevant"),
    ("The Talking Lamp", "An inanimate object with a lot to say"),
)


@dataclass(frozen=True)
class Style:
    """The flavor a personality gives a script."""

    opening: str
    lines: tuple[str, ...]
    closing: str


STYLES: dict[str, Style] = {
    "noir": Style(
        opening="Rain hammers a dim office. Everyone is a suspect.",
        lines=(
            "This city chews people up, and tonight it's chewing on {prompt}.",
            "I've seen trouble before, but never trouble like {prompt}.",
            "Don't look at me like that. I only came here for answers.",
            "Somebody in this room knows more than they're saying.",
            "The clues don't add up. They never add up in this town.",
            "Light me a cigarette. I need to think about {prompt}.",
        ),
        closing="The lights flicker out. Nobody is innocent.",
    ),
    "melodrama": Style(
        opening="A grand staircase. Thunder. Someone gasps for no reason.",
        lines=(
            "How could you? After everything we've been through with {prompt}!",
            "I have a secret, and it will change everything about {prompt}!",
            "No! I refuse to believe it! Not today, not ever!",
            "You have betrayed me for the very last time, darling.",
            "My heart cannot bear another word about {prompt}!",
            "Hold me. No, don't hold me. Actually, yes, hold me.",
        ),
        closing="Everyone faints dramatically at once.",
    ),
    "absurdist": Style(
        opening="A kitchen floating in space. A goose watches silently.",
        lines=(
            "I was told there would be soup, but instead there is {prompt}.",
            "My left shoe has filed a formal complaint about {prompt}.",
            "If we all hum loudly, the problem might simply leave.",
            "The goose knows. The goose has always known about {prompt}.",
            "I am legally a sandwich now. Please respect my journey.",
            "Has anyone checked behind the moon? Things hide there.",
        ),
        closing="The goose honks once. Blackout.",
    ),
}

GENERIC_LINES: tuple[str, ...] = (
    "Okay, nobody panic, but we have to talk about {prompt}.",
    "I knew this would happen. I said it would happen. Nobody listened.",
    "Wait, are you telling me this is all because of {prompt}?",
    "Fine. I have a plan, and you are all going to hate it.",
    "Let's take a deep breath and think about {prompt} calmly.",
    "That is the worst idea I have ever heard. Let's do it.",
)


def _style_for(personality: AIPersonality) -> Style:
    """Pick a known style, or build one from the personality's own words."""
    if personality.id in STYLES:
        return STYLES[personality.id]
    tone = personality.description or personality.name
    return Style(
        opening=f"The scene begins. The tone: {tone}.",
        lines=GENERIC_LINES,
        closing=f"Curtain falls on the {personality.name} production.",
    )


def _seed(prompt: str, personality: AIPersonality, num_roles: int) -> int:
    """Derive a stable seed; built-in hash() is randomized per process."""
    key = "\x1f".join((prompt, personality.id, str(num_roles)))
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


def _cast(rng: random.Random, num_roles: int) -> list[Role]:
    """Choose num_roles characters with unique names."""
    picks = rng.sample(CHARACTERS, k=min(num_roles, len(CHARACTERS)))
    roles = [Role(name=name, description=description) for name, description in picks]
    for extra in range(len(roles), num_roles):
        name, description = CHARACTERS[extra % len(CHARACTERS)]
        roles.append(Role(name=f"{name} {extra // len(CHARACTERS) + 1}", description=description))
    return roles


class StandInLLMAdapter:
    """LLMPort implementation that needs no network and no API key."""

    async def generate_script(
        self,
        prompt: str,
        personality: AIPersonality,
        num_roles: int,
    ) -> Script:
        """Generate a deterministic script for the given inputs."""
        if num_roles < 1:
            raise ValueError("num_roles must be at least 1")
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt cannot be blank")

        rng = random.Random(_seed(prompt, personality, num_roles))
        style = _style_for(personality)
        roles = _cast(rng, num_roles)
        subject = prompt.lower()

        body: list[str] = []
        word_count = len(prompt.split()) + len(style.opening.split()) + len(style.closing.split())
        deck: list[str] = []
        speaker = roles[0]
        turn = 0
        # Every role speaks at least once, then keep going until ~150 words.
        while turn < num_roles or word_count < TARGET_WORDS:
            if turn < num_roles:
                role = roles[turn]
            else:
                role = rng.choice([r for r in roles if r is not speaker] or roles)
            if not deck:
                # Deal every line once before any line repeats.
                deck = rng.sample(style.lines, k=len(style.lines))
            line = deck.pop().format(prompt=subject)
            role.lines.append(line)
            body.append(f"{role.name}: {line}")
            word_count += len(body[-1].split())
            speaker = role
            turn += 1

        content = "\n".join([prompt.title(), f"[{style.opening}]", *body, f"[{style.closing}]"])
        return Script(
            content=content,
            roles=roles,
            personality=personality.id,
            generated_at=GENERATED_AT,
        )


if TYPE_CHECKING:
    # mypy fails here if the adapter drifts from the port's signature.
    _port_check: LLMPort = StandInLLMAdapter()
