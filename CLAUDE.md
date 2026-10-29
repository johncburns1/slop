# CLAUDE.md

Slop is an AI party game. Teams perform scripts that an LLM writes from six-word prompts, and the other teams guess the prompt. Read `PRODUCT.md` for the game and `ARCHITECTURE.md` for the design. This file covers only what you need to work in the code.

## Commands

```bash
uv run scripts/validate.py   # setup + all checks below; JSON summary in .validation/summary.json
uv sync --all-extras
uv run pytest
uv run mypy src
uv run ruff check --fix && uv run ruff format
```

CI runs `uv run scripts/validate.py`, and a change isn't done until it passes. Start the server with `uv run slop serve` (`--port`/`--data-dir`, or `SLOP_PORT`/`SLOP_DATA_DIR`).

## Architecture rules

The code uses hexagonal architecture. Dependencies point inward:

- `domain/` is pure game logic and events. It must not import from other layers or do I/O, so the rules stay testable on their own.
- `ports/` defines `Protocol` interfaces. `adapters/` implements them. The domain and application code depend only on ports, never on a concrete adapter.
- Game state is event-sourced. A state change happens by emitting a domain event (`domain/events.py`), not by mutating storage directly.
- Persistence models stay inside adapters. Never store domain objects directly.
- Every use case follows the load → check → emit → `commit` flow described in the `slop.application` package docstring.

## Conventions

- mypy runs in strict mode, so every function needs type hints.
- Domain models are dataclasses. Events are Pydantic models.
- API endpoints take and return typed Pydantic models from `slop.api.schemas`, never `dict`, `Any`, or untyped JSON.
- Write tests first. Tests mirror the source layout under `tests/`.
- Follow `CONTRIBUTING.md` for PR rules, priority labels, and workstream states.
- For general engineering, Python, and backend practices, see the `engineering-standards`, `python-engineering`, and `backend-development` skills.
