# Architecture: Slop

**An AI-powered party game with real-time multiplayer synchronization**

---

## System Overview

Slop is a real-time, multi-device party game where teams perform AI-generated scripts and compete by guessing prompts. The system supports room-based game sessions with 4-18 players (2-6 teams), real-time WebSocket synchronization, AI script generation, and crash-resilient game state management.

**Scale:** POC for friends - 1-5 concurrent games, <50 WebSocket connections peak
**Budget:** <$20/month (free tier hosting + low-cost LLM API)
**Availability:** Single-region, occasional downtime acceptable
**Latency:** <1 second real-time sync, <5 seconds script generation

---

## Architecture Pattern

**Hexagonal Architecture (Ports and Adapters)** with **Event Sourcing**

```text
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server                            │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │            WebSocket Handler (Socket.IO)                │ │
│  │         (Real-time event broadcast to clients)          │ │
│  └──────────────────────┬─────────────────────────────────┘ │
│                         │                                    │
│  ┌──────────────────────▼─────────────────────────────────┐ │
│  │              Application Layer                          │ │
│  │   - GameManagement (create, join, manage rooms)         │ │
│  │   - ScriptGeneration (AI script orchestration)          │ │
│  │   - Scoring (calculate and update scores)               │ │
│  └──────────────────────┬─────────────────────────────────┘ │
│                         │                                    │
│  ┌──────────────────────▼─────────────────────────────────┐ │
│  │                 Domain Layer                            │ │
│  │      Game, Team, Player, Round, Script, Event           │ │
│  │         (Pure business logic, no dependencies)          │ │
│  └────┬─────────────────────────────────────────┬─────────┘ │
│       │                                         │            │
│  ┌────▼─────────┐  ┌──────────────┐  ┌────────▼─────────┐  │
│  │ StoragePort  │  │ RealtimePort │  │    LLMPort       │  │
│  │ (interface)  │  │ (interface)  │  │  (interface)     │  │
│  └────┬─────────┘  └──────────────┘  └────────┬─────────┘  │
└───────┼─────────────────────────────────────────┼───────────┘
        │                                         │
   ┌────▼──────────┐                      ┌──────▼────────┐
   │ Event Store   │                      │   LLM API     │
   │  + Snapshots  │                      │   Gateway     │
   │   (SQLite)    │                      │ (OpenAI/etc)  │
   └───────────────┘                      └───────────────┘
```

**Clients (React PWA)** connect via WebSocket, receive event broadcasts, maintain local state mirrors.

---

## Core Components

### 1. Domain Layer (Pure Business Logic)

**Entities:**

- `Game` - Room session with teams, rounds, settings, status
- `Player` - Individual participant, belongs to Team
- `Team` - Group of 1-3 players, has assigned AI personality, score
- `Round` - Turn with prompt, script, role assignments, guesses, scores
- `Script` - AI-generated content with N roles (matches acting team size)
- `AIPersonality` - LLM prompt configuration for script style

**Relationships:**

- Game → Teams (2-6) → Players (1-3 per team)
- Game → Rounds (3 per team + tiebreakers)
- Round → Script → Roles (N roles per script)

### 2. Application Layer (Use Cases)

- **GameManagement:** Create game, join game, form teams, assign personalities
- **ScriptGeneration:** Orchestrate LLM calls with personality prompts, assign roles to players
- **Scoring:** Calculate points (guessing teams + acting team), update leaderboard

### 3. Adapters

**Storage Adapter (SQLite):**

- Event store (append-only event log)
- Snapshots (materialized current state for fast reads)

**WebSocket Adapter (python-socketio):**

- Bidirectional communication with clients
- Room-based event broadcasting
- Connection management

**LLM Adapter:**

- Interface to LLM provider (implementation-agnostic)
- Generate scripts from 6-word prompts
- Apply personality-based system prompts

---

## Event Sourcing Design

### Hybrid Approach: Event Log + Materialized Snapshots

**Storage Model:**

```text
Events Table (Append-only)
├─ event_id (auto-increment)
├─ game_id
├─ event_type (PromptSubmitted, ScriptGenerated, RoundCompleted, etc.)
├─ event_data (JSON payload)
├─ round_number (for recovery checkpoints)
└─ timestamp

Snapshots Table (Current State)
├─ game_id (PK)
├─ current_state (JSON - full game state)
├─ last_event_id (pointer to event log)
└─ last_completed_round (recovery checkpoint)
```

**Normal Operation:**

1. Command arrives (e.g., submit prompt)
2. Domain validates and emits event (e.g., `PromptSubmitted`)
3. Append event to event log (immutable, write-only)
4. Update snapshot (materialized current state)
5. Broadcast event to all clients in room via WebSocket

**Crash Recovery:**

1. Server restarts
2. Load last snapshot for each active game
3. Identify incomplete rounds (events after last `RoundCompleted`)
4. Attempt to resume incomplete round:
   - If sufficient events exist (prompt, script, roles assigned) → resume from current step
   - Otherwise → discard incomplete round, restart from last completed round
5. Broadcast `GameResumed` event to reconnecting clients

**Event Retention:**

- Events persist only for active game session
- Delete all events when game ends (`GameCompleted` event)

### Key Events

- `GameCreated`, `PlayerJoined`, `TeamFormed`, `PersonalityAssigned`
- `RoundStarted`, `PromptSubmitted`, `ScriptGenerated`, `RoleAssigned`
- `PerformanceStarted`, `GuessSubmitted`, `GuessAccepted`
- `PersonalityGuessSubmitted`, `ScoresUpdated`
- **`RoundCompleted`** ← Recovery checkpoint
- `GameCompleted`

---

## Data Flow

### 1. Room Setup Flow

```text
Client → REST: Create Game
Server → SQLite: Store game + emit GameCreated event
Server → WebSocket: Broadcast GameCreated to room
Client → WebSocket: Join game (room code)
Server → SQLite: Append PlayerJoined event
Server → WebSocket: Broadcast PlayerJoined to room
... (team formation, personality assignment)
```

### 2. Round Gameplay Flow

```text
Client → WebSocket: Submit prompt (6 words)
Server → SQLite: Append PromptSubmitted event
Server → LLM API: Generate script with personality
Server → SQLite: Append ScriptGenerated + RoleAssigned events
Server → WebSocket: Broadcast script to acting team only
... (performance, guessing, scoring)
Server → SQLite: Append RoundCompleted event (checkpoint)
Server → WebSocket: Broadcast updated scores to all
```

### 3. Real-time Synchronization

- All game state changes emit events
- Events broadcast to room via WebSocket
- Clients maintain local state mirrors
- Optimistic UI updates with server reconciliation

---

## Design Decisions & Trade-offs

| Decision | Benefit | Cost | Rationale |
|----------|---------|------|-----------|
| **Event Sourcing (Hybrid)** | Crash recovery, audit trail, natural fit for real-time game | More complex than CRUD, event replay logic | Game is inherently event-driven; recovery is critical for user experience |
| **Hexagonal Architecture** | Swap LLM providers, test domain without infrastructure | More abstraction layers | Small codebase, benefits outweigh complexity at POC scale |
| **SQLite (File-based DB)** | Zero ops, free, adequate for scale | No horizontal scaling, single-region only | POC scale (<5 concurrent games), hosting budget constraint |
| **WebSocket (Socket.IO)** | Real-time bidirectional communication, room support | More complex than polling, stateful connections | Real-time sync is core requirement (<1s latency) |
| **Single Server** | Simple deployment, no distributed coordination | No redundancy, single point of failure | POC scale, occasional downtime acceptable |
| **Async Python (FastAPI)** | Handle concurrent WebSockets efficiently | Async code complexity | Required for real-time performance with 50+ connections |
| **No authentication** | Faster onboarding, lower complexity | Less secure (room codes only) | In-person party game, security not critical for POC |
| **Session-only persistence** | Lower storage costs, simpler cleanup | No game history across sessions | Out of scope for MVP (per PRODUCT.md) |

---

## Non-Functional Requirements

**Performance:**

- Real-time sync latency: <1 second (WebSocket broadcasts)
- Script generation: <5 seconds (LLM API call)
- Concurrent games: 1-5 peak (POC scale)
- WebSocket connections: <50 peak

**Reliability:**

- Crash recovery: Resume from last completed round or restart round
- Disconnection handling: Clients auto-reconnect, receive current state
- Data durability: Events persisted before broadcast

**Security:**

- Content filtering: LLM output validation (prevent inappropriate content)
- Rate limiting: Prevent API abuse (DOS protection)
- Input validation: 6-word max on prompts
- Room code expiration: 24 hours or game completion

**Cost:**

- Hosting: Fly.io free tier (3 VMs, persistent volumes)
- LLM API: <$20/month target (optimize prompt length, use cost-effective models)

---

## Error Handling & Resilience

### Error Handling Strategies

| Failure Scenario | Strategy | Rationale |
|------------------|----------|-----------|
| **LLM API failure** | Retry 2-3x with exponential backoff (1s, 2s, 4s); then fail round and notify players | Balance recovery from transient errors with fast failure feedback |
| **WebSocket disconnect** | Client auto-reconnects with exponential backoff; server sends full state snapshot on reconnect | Graceful recovery from network blips, ensure state consistency |
| **Database write failure** | Fail fast, reject command, log error to stdout | Cannot compromise data integrity; rare at POC scale with local SQLite |
| **Script content filter violation** | Regenerate script with stricter prompt (1 retry); then skip round if still fails | Prevent inappropriate content while minimizing game disruption |

**Timeouts:**

- LLM API requests: 10 seconds hard timeout
- WebSocket message acknowledgment: 5 seconds (then assume client disconnected)
- Database writes: 2 seconds (SQLite should be <100ms; timeout indicates disk issues)

**Circuit Breaker:**

- LLM API: Open circuit after 5 consecutive failures; half-open retry after 30 seconds
- Prevents cascading failures and excessive API costs during outages

---

## Deployment & Operations

### Deployment Strategy (MVP)

**Automated Deployment Pipeline:**

```text
GitHub Actions Workflow:
  Push to main → Run tests → Build Docker image → Deploy to Fly.io
```

**Process:**

1. Developer merges PR to `main` branch
2. GitHub Actions triggers CI/CD workflow:
   - Run unit tests (`pytest`)
   - Run type checks (`mypy`)
   - Run linter (`ruff`)
   - Build Docker image
   - Push to Fly.io container registry
   - Deploy with `fly deploy --ha=false` (single instance for POC)
3. Fly.io performs rolling deployment (brief downtime <30s acceptable)
4. Health check: Simple HTTP endpoint (`GET /health`)

**Rollback:**

- Manual rollback via Fly.io CLI: `fly releases rollback`
- Triggered if deployment causes crash loops or major bugs

**Deployment Frequency:**

- Automated on every merge to `main`
- Typical cadence: 1-3 deployments per week during active development

### Disaster Recovery (MVP)

**Backup Strategy:**

- Manual SQLite database exports before risky deployments
- No automated backup infrastructure for MVP (session-only data model)
- Acceptable data loss: 5-10 minutes (games can be restarted)

**Recovery Plan:**

- Server crash: Fly.io auto-restarts container
- Data corruption: Restore from manual backup or reset database (games restart)
- RTO (Recovery Time Objective): <10 minutes (manual intervention)
- RPO (Recovery Point Objective): Session-only (acceptable to lose incomplete games)

### Post-MVP Operational Enhancements

Deferred to post-POC scale (>10 concurrent games):

- **Monitoring Dashboard**: WebSocket health, LLM latency, active games, error rates
- **Automated Alerts**: Critical failures (crash loops, API outages, high disconnect rates)
- **Automated Backups**: Scheduled SQLite backups to object storage (6-hour intervals)
- **Zero-downtime Deployments**: Blue-green deployment with health checks
- **Cost Tracking**: LLM spend alerts at budget thresholds

---

## Deployment Architecture

**Platform:** Fly.io (single-region, free tier)

```text
┌─────────────────────────────────────┐
│      Fly.io VM (Single Instance)    │
│  ┌───────────────────────────────┐  │
│  │   FastAPI + Socket.IO Server  │  │
│  │   (Async Python 3.13)         │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │   SQLite Database File        │  │
│  │   (Persistent Volume)         │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
          │
          │ HTTPS/WSS
          │
    ┌─────▼──────┐
    │   Clients  │ (React PWA on phones)
    └────────────┘
```

**Static Assets:** React PWA served from same FastAPI server (no separate CDN for POC)

---

## Future Scaling Considerations

**At 10x scale (50 concurrent games, 500 connections):**

- Add Redis for distributed state (multi-instance coordination)
- Separate WebSocket servers from API servers
- Migrate from SQLite to PostgreSQL
- Add CDN for static assets
- Implement LLM response caching (deduplicate similar prompts)
- Add horizontal scaling with load balancer

**At 100x scale:**

- Multi-region deployment
- Message queue for event processing (decouple WebSocket broadcast)
- Dedicated event store database
- Sharded storage by game_id
- Separate LLM service with rate limiting and retries

---

**Last Updated:** 2025-12-28
**Status:** Initial Design - Ready for Implementation
**Owner:** Development Team
