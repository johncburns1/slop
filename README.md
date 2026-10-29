# Slop

[![CI](https://github.com/johncburns1/slop/actions/workflows/ci.yml/badge.svg)](https://github.com/johncburns1/slop/actions/workflows/ci.yml)

A party game for groups in the same room. Your team writes a six-word prompt, an AI turns it into a ridiculous script, and you perform it while everyone else races to guess what you typed. Everyone plays from their phone.

**Status:** early development. The domain model and port interfaces are in place. The server and frontend aren't built yet.

## Docs

- [PRODUCT.md](PRODUCT.md): what we're building and why
- [ARCHITECTURE.md](ARCHITECTURE.md): how the system is put together
- [CONTRIBUTING.md](CONTRIBUTING.md): PR rules, priority labels, and workstream states

## Development

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras   # install
uv run pytest          # test
uv run mypy src        # type check
uv run ruff check      # lint
uv run ruff format     # format
```

These are the same checks CI runs.
