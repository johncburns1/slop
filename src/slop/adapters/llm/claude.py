"""LLM adapter backed by Anthropic's Claude.

Scripts and awards come back as structured output (a JSON schema built from the
Pydantic models below), which the adapter then checks against what the port
promises: exactly the requested roles, every role speaking, and awards that name
someone in the game. If a response is unusable it asks once more, then raises
``LLMError``. Transient API errors (429, 5xx, timeouts, dropped connections) are
retried by the SDK itself; whatever is left also becomes ``LLMError``.

The prompt text lives in ``slop.adapters.llm.prompts``. The SDK stays inside
this module: nothing outside the adapters layer imports ``anthropic``.
"""

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

import anthropic
from pydantic import BaseModel, ValidationError

from slop.adapters.llm import prompts
from slop.domain.ai_personality import AIPersonality
from slop.domain.award import Award
from slop.domain.game import ContentTone
from slop.domain.script import Role, Script
from slop.ports.llm import AWARD_COUNT, GameSummary, LLMError

if TYPE_CHECKING:
    from slop.ports.llm import LLMPort

DEFAULT_MODEL = "claude-haiku-5-5"
# Seconds per HTTP attempt. The SDK retries timeouts, 429s, 5xx, and connection
# errors MAX_RETRIES times with backoff before giving up.
DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_RETRIES = 2
# A script is ~150 words; this leaves room for the model's thinking as well.
MAX_TOKENS = 8000
# Short creative writing doesn't need deep thought, and low effort keeps it fast.
EFFORT: Literal["low"] = "low"
# The first try plus one retry when the output is unusable.
ATTEMPTS = 2

logger = logging.getLogger(__name__)


# Claude's structured output. Docstrings here are sent to Claude in the schema.


class ScriptLine(BaseModel):
    speaker: str  # a role name, or "" for a stage direction
    text: str


class ScriptRole(BaseModel):
    name: str
    description: str


class ScriptOutput(BaseModel):
    """A short comic script for players to perform."""

    title: str
    roles: list[ScriptRole]
    lines: list[ScriptLine]


class AwardOutput(BaseModel):
    title: str
    recipient: str
    reason: str


class AwardsOutput(BaseModel):
    """End-of-game awards, each for a team or player in the game."""

    awards: list[AwardOutput]


class InvalidOutputError(Exception):
    """Claude's output parsed but broke a rule of the port."""


class ClaudeLLMAdapter:
    """LLMPort implementation that calls Claude through the Anthropic SDK.

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

    async def generate_script(
        self,
        prompt: str,
        personality: AIPersonality,
        num_roles: int,
        content_tone: ContentTone,
    ) -> Script:
        """Ask Claude for a script with exactly ``num_roles`` roles."""
        if num_roles < 1:
            raise ValueError("num_roles must be at least 1")
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt cannot be blank")

        request = prompts.script_request(prompt, personality, num_roles, content_tone)
        return await self._ask(
            "script",
            prompts.SCRIPT_SYSTEM,
            request,
            ScriptOutput,
            lambda output: _script(output, personality, num_roles),
        )

    async def generate_awards(self, summary: GameSummary) -> list[Award]:
        """Ask Claude for ``AWARD_COUNT`` awards, each naming someone in the game."""
        if not summary.teams:
            raise LLMError("A game with no teams gets no awards")
        return await self._ask(
            "awards",
            prompts.AWARDS_SYSTEM,
            prompts.awards_request(summary),
            AwardsOutput,
            lambda output: _awards(output, summary.names()),
        )

    async def _ask[O: BaseModel, R](
        self,
        what: str,
        system: str,
        request: str,
        output: type[O],
        check: Callable[[O], R],
    ) -> R:
        """Send one request, check the output, and retry once if it's unusable."""
        problem = ""
        for attempt in range(1, ATTEMPTS + 1):
            started = time.perf_counter()
            try:
                response = await self._client.messages.parse(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": request}],
                    output_format=output,
                    output_config={"effort": EFFORT},
                )
            except anthropic.APIError as error:
                raise LLMError(f"Claude {what} request failed: {error}") from error
            except ValidationError as error:
                # The text wasn't valid JSON for the schema, e.g. cut off at max_tokens.
                problem = f"output didn't match the schema: {error.error_count()} errors"
                logger.warning("Claude %s attempt %d: %s", what, attempt, problem)
                continue
            latency = time.perf_counter() - started
            logger.info(
                "Claude %s took %.2fs, %d input and %d output tokens (request %s)",
                what,
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
            try:
                if response.stop_reason != "end_turn":
                    raise InvalidOutputError(f"stopped early ({response.stop_reason})")
                parsed = response.parsed_output
                if parsed is None:
                    raise InvalidOutputError("no structured output in the response")
                return check(parsed)
            except InvalidOutputError as error:
                problem = str(error)
                logger.warning("Claude %s attempt %d: %s", what, attempt, problem)
        raise LLMError(f"Claude gave an unusable {what} {ATTEMPTS} times: {problem}")


def _script(output: ScriptOutput, personality: AIPersonality, num_roles: int) -> Script:
    """Turn Claude's output into a Script, or raise InvalidOutputError."""
    if len(output.roles) != num_roles:
        raise InvalidOutputError(f"{len(output.roles)} roles instead of {num_roles}")
    roles = [Role(name=r.name.strip(), description=r.description.strip()) for r in output.roles]
    by_name = {role.name: role for role in roles}
    if len(by_name) != num_roles or "" in by_name:
        raise InvalidOutputError("role names must be unique and non-blank")
    if any(not role.description for role in roles):
        raise InvalidOutputError("every role needs a description")
    title = output.title.strip()
    if not title:
        raise InvalidOutputError("the script has no title")

    body: list[str] = []
    for line in output.lines:
        speaker, text = line.speaker.strip(), line.text.strip()
        if not text:
            continue
        if not speaker:
            body.append(f"[{text}]")
        elif speaker in by_name:
            by_name[speaker].lines.append(text)
            body.append(f"{speaker}: {text}")
        else:
            raise InvalidOutputError(f"{speaker!r} speaks but isn't one of the roles")
    silent = [role.name for role in roles if not role.lines]
    if silent:
        raise InvalidOutputError(f"roles with no lines: {', '.join(silent)}")

    return Script(content="\n".join([title, *body]), roles=roles, personality=personality.id)


def _awards(output: AwardsOutput, names: frozenset[str]) -> list[Award]:
    """Turn Claude's output into awards, or raise InvalidOutputError."""
    if len(output.awards) != AWARD_COUNT:
        raise InvalidOutputError(f"{len(output.awards)} awards instead of {AWARD_COUNT}")
    awards = [Award(a.title.strip(), a.recipient.strip(), a.reason.strip()) for a in output.awards]
    for award in awards:
        if not award.title or not award.reason:
            raise InvalidOutputError("every award needs a title and a reason")
        if award.recipient not in names:
            raise InvalidOutputError(f"{award.recipient!r} isn't a team or player in the game")
    return awards


if TYPE_CHECKING:
    # mypy fails here if the adapter drifts from the port's signature.
    _port_check: LLMPort = ClaudeLLMAdapter()
