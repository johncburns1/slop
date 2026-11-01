"""Opt-in tests against the real Anthropic API.

Skipped unless ANTHROPIC_API_KEY is set and SLOP_LIVE_LLM=1, so CI and local runs
never need a key or the network. Run them with:

    SLOP_LIVE_LLM=1 ANTHROPIC_API_KEY=... uv run pytest tests/adapters/llm/test_claude_live.py

Set SLOP_LLM_MODEL to try another model. Besides the contract, this writes a sample
script with its latency and token usage to ``claude-live/sample.md`` in the evidence
directory (``.validation/evidence`` unless SLOP_EVIDENCE_DIR says otherwise).
"""

import logging
import os
import time

import pytest

from slop.adapters.llm import ClaudeLLMAdapter
from slop.adapters.llm.claude import DEFAULT_MODEL
from slop.domain.personalities import get_personality
from slop.ports import LLMPort
from tests.adapters.llm.contract import PROMPT, LLMPortContract, make_summary
from tests.evidence import write_evidence

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("SLOP_LIVE_LLM") == "1"),
    reason="live API test: set ANTHROPIC_API_KEY and SLOP_LIVE_LLM=1",
)

MODEL = os.environ.get("SLOP_LLM_MODEL", DEFAULT_MODEL)


@pytest.fixture
def live() -> ClaudeLLMAdapter:
    return ClaudeLLMAdapter(model=MODEL)


class TestClaudeLLMAdapterLiveContract(LLMPortContract):
    """The real API must pass the shared LLM contract too."""

    @pytest.fixture
    def adapter(self, live: ClaudeLLMAdapter) -> LLMPort:
        return live


def _calls(caplog: pytest.LogCaptureFixture) -> list[str]:
    """One table row per API call the adapter logged."""
    return [
        f"| {r.llm_model} | {r.llm_latency:.2f}s | {r.llm_input_tokens} | {r.llm_output_tokens} |"
        for r in caplog.records
        if hasattr(r, "llm_latency")
    ]


async def test_writes_a_sample_script_with_latency_and_usage(
    live: ClaudeLLMAdapter, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="slop.adapters.llm.claude")

    started = time.perf_counter()
    script = await live.generate_script(PROMPT, get_personality("noir"), 3)
    script_seconds = time.perf_counter() - started
    awards = await live.generate_awards(make_summary())

    calls = _calls(caplog)
    assert calls
    roles = "\n".join(f"- **{role.name}**: {role.description}" for role in script.roles)
    award_lines = "\n".join(f"- **{a.title}** to {a.recipient}: {a.reason}" for a in awards)
    write_evidence(
        "claude-live/sample.md",
        f"# Live Claude sample ({MODEL})\n\n"
        f"Prompt: *{PROMPT}*, personality Noir, 3 roles. "
        f"Script took {script_seconds:.2f}s end to end, {script.word_count} words.\n\n"
        f"## Roles\n\n{roles}\n\n## Script\n\n```\n{script.content}\n```\n\n"
        f"## Awards\n\n{award_lines}\n\n"
        "## API calls\n\n| Model | Latency | Input tokens | Output tokens |\n"
        f"| --- | --- | --- | --- |\n" + "\n".join(calls) + "\n",
    )
