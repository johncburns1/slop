"""Tests for the Claude moderation adapter, with the Anthropic API faked at the HTTP layer."""

import json
import logging
from typing import Any

import httpx2
import pytest

from slop.adapters.moderation import ClaudeModerationAdapter
from slop.adapters.moderation.claude import DEFAULT_MODEL, REFUSED, UNAVAILABLE
from slop.adapters.moderation.prompts import MODERATION_SYSTEM
from slop.domain import ContentTone
from slop.ports import ModerationPort, ModerationResult
from slop.ports.moderation import ALLOWED
from tests.adapters.llm.fake_anthropic import (
    FakeAnthropicAPI,
    Reply,
    schema_fields,
    user_message,
)
from tests.adapters.moderation.contract import ModerationPortContract

FAMILY, ADULT = ContentTone.FAMILY, ContentTone.ADULT
ALWAYS_BLOCKED = "a hateful slur"
FAMILY_BLOCKED = "some salty swearing"


def classify(body: dict[str, Any]) -> dict[str, Any]:
    """Answer like a model following the rules the request states for its content setting."""
    text = user_message(body)
    if ALWAYS_BLOCKED in text:
        return {"verdict": "slur"}
    if FAMILY_BLOCKED in text and "profanity" in body["system"]:
        return {"verdict": "profanity"}
    return {"verdict": "allowed"}


@pytest.fixture
def api() -> FakeAnthropicAPI:
    return FakeAnthropicAPI(respond=classify)


@pytest.fixture
def claude(api: FakeAnthropicAPI) -> ClaudeModerationAdapter:
    return ClaudeModerationAdapter(client=api.client())


class TestClaudeModerationAdapterContract(ModerationPortContract):
    """The Claude adapter must pass the shared moderation contract."""

    @pytest.fixture
    def adapter(self, claude: ClaudeModerationAdapter) -> ModerationPort:
        return claude

    @pytest.fixture
    def blocked_always(self) -> str:
        return ALWAYS_BLOCKED

    @pytest.fixture
    def blocked_for_family(self) -> str:
        return FAMILY_BLOCKED


def test_defaults_to_haiku() -> None:
    assert ClaudeModerationAdapter(client=FakeAnthropicAPI().client()).model == DEFAULT_MODEL
    assert DEFAULT_MODEL == "claude-haiku-5-5"


async def test_request_carries_the_model_rules_and_text(api: FakeAnthropicAPI) -> None:
    adapter = ClaudeModerationAdapter(model="claude-sonnet-5-5", client=api.client())

    await adapter.check("Cat steals the moon", ADULT)

    (body,) = api.requests
    assert body["model"] == "claude-sonnet-5-5"
    assert body["system"] == MODERATION_SYSTEM[ADULT]
    assert user_message(body) == "Cat steals the moon"
    assert schema_fields(body) == {"verdict"}


def test_family_rules_include_every_adult_rule() -> None:
    """The port promises family games are at least as strict as adult ones."""
    adult_rules = MODERATION_SYSTEM[ADULT].split("Block text that contains:\n")[1]
    rules = adult_rules.split("\n\n")[0].splitlines()

    assert rules
    for rule in rules:
        assert rule in MODERATION_SYSTEM[FAMILY]
    for word in ("profanity", "sexual content", "graphic violence"):
        assert word in MODERATION_SYSTEM[FAMILY]


def test_rules_say_the_text_is_not_instructions() -> None:
    for system in MODERATION_SYSTEM.values():
        assert "never follow" in system


@pytest.mark.parametrize("tone", list(ContentTone))
async def test_blocked_text_reports_the_category_claude_chose(
    claude: ClaudeModerationAdapter, tone: ContentTone
) -> None:
    assert await claude.check(ALWAYS_BLOCKED, tone) == ModerationResult.blocked("slur")


async def test_the_same_text_is_judged_by_the_games_content_setting(
    claude: ClaudeModerationAdapter,
) -> None:
    assert await claude.check(FAMILY_BLOCKED, FAMILY) == ModerationResult.blocked("profanity")
    assert await claude.check(FAMILY_BLOCKED, ADULT) == ALLOWED


@pytest.mark.parametrize("text", ["", "   \n"])
async def test_blank_text_is_allowed_without_asking(
    claude: ClaudeModerationAdapter, api: FakeAnthropicAPI, text: str
) -> None:
    assert await claude.check(text, FAMILY) == ALLOWED
    assert api.requests == []


FAILURES = {
    "server error": Reply(status=500),
    "rate limited": Reply(status=429),
    "bad request": Reply(status=400),
    "rejected key": Reply(status=401),
    "timeout": Reply(raises=httpx2.ReadTimeout("too slow")),
    "dropped connection": Reply(raises=httpx2.ConnectError("no route")),
    "not json": Reply(text="Sure! That looks fine to me."),
    "cut off json": Reply(text='{"verd'),
    "empty text": Reply(text=""),
    "wrong shape": Reply(output={"allowed": True}),
    "unknown verdict": Reply(output={"verdict": "fine I guess"}),
    "hit max_tokens": Reply(output={"verdict": "allowed"}, stop_reason="max_tokens"),
}


@pytest.fixture(params=list(FAILURES.values()), ids=list(FAILURES))
def failing_api(request: pytest.FixtureRequest) -> FakeAnthropicAPI:
    return FakeAnthropicAPI(replies=[request.param])


async def test_family_games_block_when_claude_gives_no_usable_answer(
    failing_api: FakeAnthropicAPI, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = ClaudeModerationAdapter(client=failing_api.client())

    with caplog.at_level(logging.WARNING, logger="slop.adapters.moderation.claude"):
        result = await adapter.check("Cat steals the moon", FAMILY)

    assert result == ModerationResult.blocked(UNAVAILABLE)
    assert "failing safe" in caplog.text
    assert "family" in caplog.text


async def test_adult_games_allow_when_claude_gives_no_usable_answer(
    failing_api: FakeAnthropicAPI, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = ClaudeModerationAdapter(client=failing_api.client())

    with caplog.at_level(logging.WARNING, logger="slop.adapters.moderation.claude"):
        result = await adapter.check("Cat steals the moon", ADULT)

    assert result == ALLOWED
    assert "failing safe" in caplog.text
    assert "adult" in caplog.text


async def test_failure_logs_leave_out_the_players_text(
    failing_api: FakeAnthropicAPI, caplog: pytest.LogCaptureFixture
) -> None:
    adapter = ClaudeModerationAdapter(client=failing_api.client())

    with caplog.at_level(logging.DEBUG, logger="slop.adapters.moderation.claude"):
        await adapter.check("my secret prompt", FAMILY)

    assert "my secret prompt" not in caplog.text


@pytest.mark.parametrize("tone", list(ContentTone))
@pytest.mark.parametrize(
    "reply",
    [
        Reply(text="", stop_reason="refusal"),
        Reply(text="I can't help with that.", stop_reason="refusal"),
        # A refusal outranks whatever the model had written by then.
        Reply(output={"verdict": "allowed"}, stop_reason="refusal"),
    ],
    ids=["empty", "prose", "allowed so far"],
)
async def test_a_refusal_blocks_in_every_game(reply: Reply, tone: ContentTone) -> None:
    """A refusal says something about the text, so unlike an outage it never fails open."""
    api = FakeAnthropicAPI(replies=[reply])
    adapter = ClaudeModerationAdapter(client=api.client())

    assert await adapter.check("Cat steals the moon", tone) == ModerationResult.blocked(REFUSED)


async def test_the_sdk_retries_a_transient_error(api: FakeAnthropicAPI) -> None:
    api.replies.append(Reply(status=500))
    adapter = ClaudeModerationAdapter(client=api.client(max_retries=1))

    assert await adapter.check("Cat steals the moon", FAMILY) == ALLOWED
    assert len(api.requests) == 2


async def test_the_output_schema_only_offers_known_verdicts(
    claude: ClaudeModerationAdapter, api: FakeAnthropicAPI
) -> None:
    await claude.check("Cat steals the moon", FAMILY)

    schema = api.requests[0]["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert "allowed" in json.dumps(schema["properties"]["verdict"])
