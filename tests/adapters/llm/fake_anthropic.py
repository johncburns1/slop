"""A fake Anthropic Messages API, served through an in-process HTTP transport.

The Claude adapter talks to it through the real SDK, so requests and responses
cross the same HTTP boundary they would in production, with no network.

By default it answers like a well-behaved model: a script with exactly the
requested roles, or awards for people in the game. Queue ``replies`` to script
the next responses instead (an output dict, raw text, or a whole response).
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic
import httpx2

MESSAGES_URL = "https://api.anthropic.com/v1/messages"


@dataclass
class Reply:
    """One scripted response: structured output, raw text, or an HTTP error."""

    output: dict[str, Any] | None = None
    text: str | None = None
    stop_reason: str = "end_turn"
    status: int = 200


@dataclass
class FakeAnthropicAPI:
    replies: list[Reply] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)

    def client(self, max_retries: int = 0) -> anthropic.AsyncAnthropic:
        """An SDK client whose HTTP requests this fake answers."""
        return anthropic.AsyncAnthropic(
            api_key="test-key",
            max_retries=max_retries,
            http_client=anthropic.DefaultAsyncHttpxClient(
                transport=httpx2.MockTransport(self._handle)
            ),
        )

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == MESSAGES_URL
        body = json.loads(request.content)
        self.requests.append(body)
        reply = self.replies.pop(0) if self.replies else Reply(output=_well_behaved(body))
        if reply.status != 200:
            error = {"type": "api_error", "message": f"fake {reply.status}"}
            return httpx2.Response(reply.status, json={"type": "error", "error": error})
        text = reply.text if reply.text is not None else json.dumps(reply.output)
        return httpx2.Response(
            200,
            headers={"request-id": f"req_fake_{len(self.requests)}"},
            json={
                "id": f"msg_fake_{len(self.requests)}",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": text}],
                "stop_reason": reply.stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 200, "output_tokens": 300},
            },
        )


def user_message(body: dict[str, Any]) -> str:
    content = body["messages"][0]["content"]
    return content if isinstance(content, str) else content[0]["text"]


def schema_fields(body: dict[str, Any]) -> set[str]:
    """The top-level fields of the JSON schema the request asked for."""
    return set(body["output_config"]["format"]["schema"]["properties"])


def _well_behaved(body: dict[str, Any]) -> dict[str, Any]:
    if "awards" in schema_fields(body):
        return awards_output(body)
    match = re.search(r"exactly (\d+) roles", user_message(body))
    assert match, "the script request should state the role count"
    return script_output(int(match.group(1)))


def script_output(num_roles: int) -> dict[str, Any]:
    """A valid ~150-word script with ``num_roles`` roles."""
    names = [f"Inspector {chr(ord('A') + i)}" for i in range(num_roles)]
    lines = [{"speaker": "", "text": "A dark gallery. An empty frame hangs on the wall."}]
    speeches = (
        "Someone has stolen the painting, and I intend to find out who did it tonight.",
        "I was in the cloakroom the whole time, eating a sandwich of questionable origin.",
        "The frame is still warm. Whoever took it cannot have gone very far at all.",
    )
    turn = 0
    while turn < num_roles or sum(len(x["text"].split()) for x in lines) < 140:
        lines.append({"speaker": names[turn % num_roles], "text": speeches[turn % len(speeches)]})
        turn += 1
    lines.append({"speaker": "", "text": "Blackout."})
    return {
        "title": "The Missing Masterpiece",
        "roles": [{"name": name, "description": "A detective with a theory"} for name in names],
        "lines": lines,
    }


def awards_output(body: dict[str, Any]) -> dict[str, Any]:
    """Three valid awards for the game in the request."""
    game = json.loads(user_message(body).splitlines()[-1])
    team = game["teams"][0]
    recipients = [team["name"], team["players"][0], game["teams"][-1]["name"]]
    return {
        "awards": [
            {"title": f"Award {i}", "recipient": name, "reason": "For a memorable moment."}
            for i, name in enumerate(recipients)
        ]
    }
