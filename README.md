# Slop

[![CI](https://github.com/johncburns1/slop/actions/workflows/ci.yml/badge.svg)](https://github.com/johncburns1/slop/actions/workflows/ci.yml)

A party game for groups in the same room. Your team writes a six-word prompt, an AI turns it into a ridiculous script, and you perform it while everyone else races to guess what you typed. Everyone plays from their phone.

**Status:** playable end to end on phones. `uv run slop serve` serves the mobile web app at `/`, with a local AI stand-in by default; `--llm claude` uses Claude (needs `ANTHROPIC_API_KEY`).

## Docs

- [PRODUCT.md](PRODUCT.md): what we're building and why
- [ARCHITECTURE.md](ARCHITECTURE.md): how the system is put together
- [CONTRIBUTING.md](CONTRIBUTING.md): PR rules, priority labels, and workstream states

## Development

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv run scripts/validate.py   # set up and run every check, as CI does
uv run slop serve            # run the server; --port/--data-dir or SLOP_PORT/SLOP_DATA_DIR
uv run pytest                # test
uv run ruff check --fix && uv run ruff format
```

The client message contract is in `src/slop/api/messages.py`.

Scripts come from the AI stand-in unless you ask for Claude: `ANTHROPIC_API_KEY=... uv run slop serve --llm claude` (or `SLOP_LLM=claude`). Pick the model with `--llm-model` or `SLOP_LLM_MODEL` (default `claude-haiku-5-5`). The prompts are in `src/slop/adapters/llm/prompts.py`.

## Validation

Everything runs locally with no network or cost. Stand-ins replace the LLM, storage, realtime, and moderation, and simulated players play whole games in-process or against a real server. Named scenarios in `tests/scenarios/` cover a full game, tiebreakers, disconnects, and a server crash.

`scripts/validate.py` writes a report to `.validation/report.md` with a pass/fail table and each scenario's evidence. Tests add evidence with `tests.evidence.write_evidence`. CI shows the report on the run's summary page.
