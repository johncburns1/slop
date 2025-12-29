# Slop

An AI-powered party game where teams perform outrageous AI-generated scripts based on simple prompts. Players compete by acting out scenes and guessing each other's original prompts in a fast-paced, multiplayer experience.

**Key Features:**

- Multi-device real-time synchronization (everyone on their phones)
- AI-generated scripts with personality variants (dramatic, absurdist, noir, etc.)
- Team-based gameplay with strategic AI personality assignments
- Dual scoring system (guessing + acting incentives)
- Room-based sessions with simple join codes

---

## Documentation

- **[PRODUCT.md](PRODUCT.md)** - Product vision, features, user stories, success metrics
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - High-level system design, components, design decisions
- **[CLAUDE.md](CLAUDE.md)** - Project-specific guidance for Claude Code

---

## Technology Stack

### Backend

- **Python 3.13** - Language
- **uv** - Fast, modern package management
- **FastAPI** - Async web framework with OpenAPI docs
- **python-socketio** - WebSocket server (Socket.IO protocol)
- **SQLite** - File-based database for game state persistence
- **ruff** - Linting and formatting
- **mypy** - Static type checking (strict mode)
- **pytest** - Testing framework with async support

### Frontend (Planned)

- **React** - PWA framework
- **Vite** - Build tool
- **socket.io-client** - WebSocket client
- **Tailwind CSS** - Styling

### Infrastructure

- **Fly.io** - Hosting (free tier: 3 VMs, persistent volumes)
- **LLM Gateway** - OpenAI (GPT-4o) or Anthropic (Claude Sonnet)

---

## Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) installed

### Setup

```bash
# Clone repository
git clone <repo-url>
cd slop

# Install dependencies
uv sync

# Run development server
uv run slop serve

# Run tests
uv run pytest

# Type check
uv run mypy src

# Lint and format
uv run ruff check --fix
uv run ruff format
```

---

## Development Workflow

```bash
# Run development server with auto-reload
uv run slop serve --reload

# Run tests with coverage
uv run pytest --cov=slop --cov-report=term-missing

# Type checking
uv run mypy src

# Linting
uv run ruff check src

# Formatting
uv run ruff format src
```

---

## Project Structure

```text
src/slop/
├── domain/          # Pure business logic (Game, Team, Player, Round, Script)
├── ports/           # Interfaces for external systems
│   ├── llm.py      # LLM provider interface
│   ├── realtime.py # WebSocket/real-time communication interface
│   └── storage.py  # Game state persistence interface
├── adapters/        # Concrete implementations
│   ├── llm/        # LLM provider integrations (OpenAI, Anthropic)
│   ├── websocket/  # WebSocket server (Socket.io)
│   └── storage/    # SQLite storage
├── application/     # Use cases and application services
│   ├── game_management.py    # Create/join/manage games
│   ├── script_generation.py  # Generate scripts with AI
│   └── scoring.py            # Handle scoring logic
├── api/             # REST and WebSocket endpoints
├── __init__.py      # Package initialization
└── __main__.py      # Server entry point
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed component design.

---
