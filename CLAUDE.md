# CLAUDE.md

This file provides slop-specific guidance to Claude Code when working with this codebase.

> **Note**: For general engineering principles, Python tooling conventions, and development practices, see the `engineering-standards`, `python-engineering`, and `backend-development` skills.

## What is Slop?

**Slop** is an AI-powered party game where teams perform outrageous AI-generated scripts based on simple prompts. Players compete by acting out scenes and guessing each other's original prompts in a fast-paced, multiplayer experience.

**Key Features:**

- Multi-device real-time synchronization (everyone on their phones)
- AI-generated scripts with personality variants (dramatic, absurdist, noir, etc.)
- Team-based gameplay with strategic AI personality assignments
- Dual scoring system (guessing + acting incentives)
- Room-based sessions with simple join codes

This is a **Python 3.13** project managed with **uv**. The project uses:

- Hatchling for builds
- Ruff for linting and formatting
- mypy for static type checking
- pytest with coverage reporting
- pre-commit hooks for automated checks

See `PRODUCT.md` for full product vision, user stories, features, and success metrics.
See `ARCHITECTURE.md` for system overview, components, and design principles.

## Project-Specific Architecture

Slop uses **hexagonal architecture** (Ports and Adapters) with **Domain-Driven Design** patterns.

### Directory Structure

```text
src/slop/
├── domain/          # Pure business logic (Game, Team, Player, Round, Script)
├── ports/           # Interfaces for external systems
│   ├── llm.py      # LLM provider interface
│   ├── realtime.py # WebSocket/real-time communication interface
│   └── storage.py  # Game state persistence interface
├── adapters/        # Concrete implementations
│   ├── llm/        # LLM provider integrations (OpenAI, Anthropic)
│   ├── websocket/  # WebSocket server (Socket.io or similar)
│   └── storage/    # In-memory or persistent storage
├── application/     # Use cases and application services
│   ├── game_management.py    # Create/join/manage games
│   ├── script_generation.py  # Generate scripts with AI
│   └── scoring.py            # Handle scoring logic
├── api/             # REST and WebSocket endpoints
├── __init__.py      # Package initialization
└── __main__.py      # Server entry point
```

### Architecture Principles

1. **Dependencies point inward**: Domain layer depends on nothing; adapters depend on ports
2. **Domain models are never persisted directly**: Repository adapters translate between domain and persistence models
3. **Pluggable components**: Easy to swap LLM providers or real-time backends
4. **Real-time synchronization**: All game state changes broadcast to connected clients with <1 second latency
5. **Stateful sessions**: Room-based game sessions with distributed state management
6. **Script quality control**: LLM prompts engineered to generate performable, timed, personality-driven scripts

### Key Domain Models

- **Game**: Room session with teams, rounds, settings, and current state
- **Team**: Group of players with assigned AI personality and score
- **Player**: Individual participant with WebSocket connection
- **Round**: Single turn including prompt, script, role assignments, guesses, and scores
- **Script**: AI-generated content with roles matching team size
- **AIPersonality**: Configuration for LLM script generation style

## Development Workflow

Quick reference for Slop-specific commands:

```bash
# Setup
uv sync

# Run development server
uv run slop serve

# Run CLI (if applicable)
uv run slop --help

# Testing (with coverage)
uv run pytest

# Type checking
uv run mypy src

# Linting and formatting
uv run ruff check --fix
uv run ruff format
```

For detailed Python tooling and testing practices, see the `python-engineering` and `engineering-standards` skills.

## Technical Considerations

### Real-Time Requirements

- WebSocket connections for all players
- Game state synchronization across devices
- Graceful handling of disconnections/reconnections
- View-specific data (acting team sees script, others don't)

### LLM Integration

- Script generation from 6-word prompts
- Personality-based system prompts
- Exactly N roles (matching team size)
- ~90 second performance length (~150 words)
- Cost optimization (caching, prompt efficiency)

### Multi-Device UX

- Mobile-first Progressive Web App
- Dynamic views based on game state and player role
- Real-time score updates
- Timer synchronization

## Related Documentation

- **`PRODUCT.md`**: Full product vision, user stories, features, and success metrics
- **`ARCHITECTURE.md`**: System overview, components, data models, and design principles
- **`engineering-standards` skill**: General software engineering principles (TDD, hexagonal architecture, simplicity-first)
- **`python-engineering` skill**: Python-specific tooling and practices (uv, ruff, mypy, pytest)
- **`backend-development` skill**: Backend architecture and API design standards
