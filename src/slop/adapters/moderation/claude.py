"""Moderation adapter backed by Anthropic's Claude.

Claude classifies each text against the game's content setting and answers with
structured output: "allowed", or the rule the text breaks, which becomes the
result's category. The rules are in ``slop.adapters.moderation.prompts``.

When Claude gives no usable answer (the API call fails, or the output can't be
read), the text is blocked in family games and allowed in adult ones, and the
adapter logs it, so an outage stops family games from showing unchecked text
without stopping adult games from being played. A refusal is different: it says
something about the text, so it blocks in every game.

Moderation runs on every name, prompt, guess, script, and award while players
wait, so requests get a short timeout and one SDK retry, and one answer is final.
The SDK stays inside this module: nothing outside the adapters layer imports
``anthropic``.
"""

import logging
import time
from typing import TYPE_CHECKING, Literal

import anthropic
from anthropic.types import Message, OutputConfigParam
from pydantic import BaseModel, ValidationError

from slop.adapters.moderation.prompts import MODERATION_SYSTEM
from slop.domain.game import ContentTone
from slop.ports.moderation import ALLOWED, ModerationResult

if TYPE_CHECKING:
    from slop.ports.moderation import ModerationPort

DEFAULT_MODEL = "claude-haiku-5-5"
# Seconds per HTTP attempt. Someone is waiting on their phone, so at worst this
# takes about (MAX_RETRIES + 1) * TIMEOUT before failing safe.
DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 1
# The answer is a word, but this also has to cover the model's thinking.
MAX_TOKENS = 1024
# Classification doesn't repay deep thought, and low effort keeps it fast.
EFFORT: Literal["low"] = "low"

# The category when no usable answer failed safe to blocked.
UNAVAILABLE = "unavailable"
# The category when Claude refused to look at the text at all.
REFUSED = "refused"

logger = logging.getLogger(__name__)


class ModerationOutput(BaseModel):
    """Claude's structured output. Its schema is sent to Claude with each request."""

    verdict: Literal[
        "allowed", "slur", "hate", "minors", "harassment", "profanity", "sexual", "violence"
    ]


OUTPUT_CONFIG: OutputConfigParam = {
    "effort": EFFORT,
    "format": {"type": "json_schema", "schema": anthropic.transform_schema(ModerationOutput)},
}


class ClaudeModerationAdapter:
    """ModerationPort implementation that calls Claude through the Anthropic SDK.

    The API key comes from ``ANTHROPIC_API_KEY`` unless ``client`` is given.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        client: anthropic.AsyncAnthropic | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.model = model
        self._client = client or anthropic.AsyncAnthropic(timeout=timeout, max_retries=max_retries)

    async def check(self, text: str, tone: ContentTone) -> ModerationResult:
        """Ask Claude whether ``text`` may be shown in a game with this content setting."""
        if not text.strip():
            return ALLOWED

        started = time.perf_counter()
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=MODERATION_SYSTEM[tone],
                messages=[{"role": "user", "content": text}],
                output_config=OUTPUT_CONFIG,
            )
        except anthropic.APIError as error:
            return _fail_safe(tone, f"the request failed: {error}")
        latency = time.perf_counter() - started
        logger.info(
            "Claude moderation took %.2fs, %d input and %d output tokens (request %s)",
            latency,
            response.usage.input_tokens,
            response.usage.output_tokens,
            response._request_id,
            extra={
                "llm_model": response.model,
                "llm_latency": latency,
                "llm_input_tokens": response.usage.input_tokens,
                "llm_output_tokens": response.usage.output_tokens,
            },
        )

        # A refusal comes first: its text may not match the schema, and must not
        # be mistaken for an unreadable answer, which adult games would allow.
        if response.stop_reason == "refusal":
            logger.warning("Claude refused to moderate text (request %s)", response._request_id)
            return ModerationResult.blocked(REFUSED)
        if response.stop_reason != "end_turn":
            return _fail_safe(tone, f"it stopped early ({response.stop_reason})")
        try:
            verdict = ModerationOutput.model_validate_json(_text_of(response)).verdict
        except ValidationError as error:
            # Only the count: the error's details would quote the output into the log.
            return _fail_safe(tone, f"its output had {error.error_count()} schema errors")
        return ALLOWED if verdict == "allowed" else ModerationResult.blocked(verdict)


def _text_of(response: Message) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def _fail_safe(tone: ContentTone, reason: str) -> ModerationResult:
    """The result when Claude gave no usable answer: see the module docstring."""
    result = ALLOWED if tone == ContentTone.ADULT else ModerationResult.blocked(UNAVAILABLE)
    outcome = "allowing" if result.allowed else "blocking"
    logger.warning(
        "Claude moderation gave no answer because %s; failing safe by %s text (%s game)",
        reason,
        outcome,
        tone.value,
    )
    return result


if TYPE_CHECKING:
    # mypy fails here if the adapter drifts from the port's signature.
    _port_check: ModerationPort = ClaudeModerationAdapter()
