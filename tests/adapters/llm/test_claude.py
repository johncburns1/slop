"""Tests for the Claude LLM adapter, with the Anthropic API faked at the HTTP layer."""

import pytest

from slop.adapters.llm import ClaudeLLMAdapter
from slop.adapters.llm.claude import ATTEMPTS, DEFAULT_MODEL, EFFORT
from slop.adapters.llm.prompts import AWARDS_SYSTEM, CONTENT_GUIDANCE, SCRIPT_SYSTEM
from slop.domain import ContentTone
from slop.ports import LLMPort
from slop.ports.llm import LLMError
from tests.adapters.llm.contract import PROMPT, LLMPortContract, make_personality, make_summary
from tests.adapters.llm.fake_anthropic import (
    FakeAnthropicAPI,
    Reply,
    schema_fields,
    script_output,
    user_message,
)


@pytest.fixture
def api() -> FakeAnthropicAPI:
    return FakeAnthropicAPI()


@pytest.fixture
def claude(api: FakeAnthropicAPI) -> ClaudeLLMAdapter:
    return ClaudeLLMAdapter(client=api.client())


class TestClaudeLLMAdapterContract(LLMPortContract):
    """The Claude adapter must pass the shared LLM contract."""

    @pytest.fixture
    def adapter(self, claude: ClaudeLLMAdapter) -> LLMPort:
        return claude


async def test_defaults_to_haiku() -> None:
    assert ClaudeLLMAdapter(client=FakeAnthropicAPI().client()).model == DEFAULT_MODEL
    assert DEFAULT_MODEL == "claude-haiku-5-5"


async def test_script_request_carries_the_inputs(api: FakeAnthropicAPI) -> None:
    adapter = ClaudeLLMAdapter(model="claude-haiku-5-5", client=api.client())
    personality = make_personality("melodrama")

    await adapter.generate_script(PROMPT, personality, 3, ContentTone.ADULT)

    (body,) = api.requests
    assert body["model"] == "claude-haiku-5-5"
    assert body["system"] == SCRIPT_SYSTEM
    assert body["output_config"]["effort"] == EFFORT
    assert schema_fields(body) == {"title", "roles", "lines"}
    request = user_message(body)
    assert PROMPT in request
    assert personality.system_prompt in request
    assert "exactly 3 roles" in request
    assert CONTENT_GUIDANCE[ContentTone.ADULT] in request


async def test_scripts_are_family_friendly_unless_told_otherwise(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    await claude.generate_script(PROMPT, make_personality(), 2)

    assert CONTENT_GUIDANCE[ContentTone.FAMILY] in user_message(api.requests[0])


async def test_script_has_the_title_roles_and_lines(claude: ClaudeLLMAdapter) -> None:
    script = await claude.generate_script(PROMPT, make_personality(), 2)

    lines = script.content.splitlines()
    assert lines[0] == "The Missing Masterpiece"
    assert lines[1] == "[A dark gallery. An empty frame hangs on the wall.]"
    assert [role.name for role in script.roles] == ["Inspector A", "Inspector B"]
    for role in script.roles:
        assert role.lines
        assert all(f"{role.name}: {line}" in lines for line in role.lines)


@pytest.mark.parametrize(
    "bad",
    [
        Reply(output=script_output(3)),  # wrong role count
        Reply(text="Sorry, here is a script: once upon a time"),  # not JSON
        Reply(output=script_output(2), stop_reason="refusal"),
        Reply(text='{"title": "Cut off', stop_reason="max_tokens"),
    ],
)
async def test_retries_once_after_unusable_output(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI, bad: Reply
) -> None:
    api.replies = [bad]

    script = await claude.generate_script(PROMPT, make_personality(), 2)

    assert script.get_role_count() == 2
    assert len(api.requests) == 2


async def test_raises_llm_error_after_two_unusable_outputs(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    api.replies = [Reply(output=script_output(3)) for _ in range(ATTEMPTS)]

    with pytest.raises(LLMError, match="3 roles instead of 2"):
        await claude.generate_script(PROMPT, make_personality(), 2)
    assert len(api.requests) == ATTEMPTS == 2


async def test_rejects_a_speaker_who_is_not_a_role(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    stranger = script_output(2)
    stranger["lines"].append({"speaker": "The Butler", "text": "I did it."})
    api.replies = [Reply(output=stranger), Reply(output=stranger)]

    with pytest.raises(LLMError, match="The Butler"):
        await claude.generate_script(PROMPT, make_personality(), 2)


async def test_rejects_a_role_with_no_lines(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    silent = script_output(2)
    silent["lines"] = [line for line in silent["lines"] if line["speaker"] != "Inspector B"]
    api.replies = [Reply(output=silent), Reply(output=silent)]

    with pytest.raises(LLMError, match="Inspector B"):
        await claude.generate_script(PROMPT, make_personality(), 2)


async def test_rejects_duplicate_role_names(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    twins = script_output(2)
    twins["roles"][1]["name"] = twins["roles"][0]["name"]
    api.replies = [Reply(output=twins), Reply(output=twins)]

    with pytest.raises(LLMError, match="unique"):
        await claude.generate_script(PROMPT, make_personality(), 2)


async def test_an_api_error_raises_llm_error_without_asking_again(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    api.replies = [Reply(status=400)]

    with pytest.raises(LLMError, match="request failed"):
        await claude.generate_script(PROMPT, make_personality(), 2)
    assert len(api.requests) == 1


async def test_transient_server_errors_are_retried_by_the_sdk(api: FakeAnthropicAPI) -> None:
    adapter = ClaudeLLMAdapter(client=api.client(max_retries=1))
    api.replies = [Reply(status=529)]

    script = await adapter.generate_script(PROMPT, make_personality(), 2)

    assert script.get_role_count() == 2
    assert len(api.requests) == 2


async def test_awards_request_describes_the_game(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    await claude.generate_awards(make_summary(content_tone=ContentTone.ADULT))

    (body,) = api.requests
    assert body["system"] == AWARDS_SYSTEM
    assert schema_fields(body) == {"awards"}
    request = user_message(body)
    assert "Penguins open a tiny bakery" in request
    assert "Birds sell bread" in request
    assert CONTENT_GUIDANCE[ContentTone.ADULT] in request


async def test_retries_awards_for_someone_not_in_the_game(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    stranger = {
        "awards": [
            {"title": "Best", "recipient": name, "reason": "Because."}
            for name in ("Red", "Ann", "Mystery Guest")
        ]
    }
    api.replies = [Reply(output=stranger), Reply(output=stranger)]

    with pytest.raises(LLMError, match="Mystery Guest"):
        await claude.generate_awards(make_summary())
    assert len(api.requests) == 2


async def test_no_teams_means_no_awards_and_no_request(
    claude: ClaudeLLMAdapter, api: FakeAnthropicAPI
) -> None:
    summary = make_summary()
    empty = type(summary)(content_tone=summary.content_tone, teams=(), rounds=(), winner=None)

    with pytest.raises(LLMError):
        await claude.generate_awards(empty)
    assert api.requests == []


@pytest.mark.parametrize("num_roles", [0, -1])
async def test_rejects_non_positive_role_count(claude: ClaudeLLMAdapter, num_roles: int) -> None:
    with pytest.raises(ValueError, match="num_roles"):
        await claude.generate_script(PROMPT, make_personality(), num_roles)
