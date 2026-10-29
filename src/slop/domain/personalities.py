"""The built-in AI personalities a team can be assigned.

Teams store only a personality id; this catalog turns it into the full
``AIPersonality`` the LLM needs.
"""

from slop.domain.ai_personality import AIPersonality
from slop.domain.errors import GameRuleError

PERSONALITIES: dict[str, AIPersonality] = {
    p.id: p
    for p in (
        AIPersonality(
            id="noir",
            name="Noir",
            description="Hard-boiled detective drama: rain, shadows, and suspicion",
            system_prompt=(
                "Write a short scene as 1940s film noir. Weary narration, clipped "
                "dialogue, everyone is a suspect, and the mood is always rainy."
            ),
        ),
        AIPersonality(
            id="melodrama",
            name="Melodrama",
            description="Soap-opera emotions turned all the way up",
            system_prompt=(
                "Write a short scene as an over-the-top soap opera. Gasps, betrayals, "
                "secret twins, and every feeling stated as loudly as possible."
            ),
        ),
        AIPersonality(
            id="absurdist",
            name="Absurdist",
            description="Dream logic, non sequiturs, and a goose",
            system_prompt=(
                "Write a short absurdist scene. The characters accept impossible "
                "things calmly, logic bends, and nothing is explained."
            ),
        ),
    )
}


def get_personality(personality_id: str) -> AIPersonality:
    """Return the built-in personality with this id.

    Raises:
        GameRuleError: If there is no such personality
    """
    try:
        return PERSONALITIES[personality_id]
    except KeyError:
        raise GameRuleError(f"Unknown personality {personality_id}") from None
