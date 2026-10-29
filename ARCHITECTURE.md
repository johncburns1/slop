# Architecture: Slop

## Overview

Slop runs on one async Python server. It hosts game rooms, keeps every player's phone in sync over WebSockets, and calls an LLM to write scripts. The frontend is a mobile-first web app.

**Constraints**

- **Scale:** a proof of concept for friends, with a handful of games running at once
- **Cost:** under $20 a month for hosting and LLM usage combined
- **Latency:** state syncs to every phone in under a second, and scripts generate in under 5 seconds
- **Availability:** one region, and occasional downtime is acceptable

## Shape

The code follows hexagonal architecture (ports and adapters). The game state is stored with event sourcing.

```text
  Phones (web app)
        │  WebSocket
┌───────▼────────────────────────────┐
│ API: REST + Socket.IO              │
│ Application: use cases             │
│ Domain: Game, Team, Round, Script, │
│         events (no dependencies)   │
│ Ports: Storage · Realtime · LLM    │
└───┬───────────────────────┬────────┘
    │                       │
 SQLite                  LLM provider
 (events + snapshots)
```

- **Domain:** the game rules and the events they emit. It has no I/O.
- **Application:** use cases such as creating and joining games, generating scripts, and scoring.
- **Ports:** interfaces for storage, realtime messaging, and the LLM.
- **Adapters:** the implementations behind those interfaces (SQLite, Socket.IO, and an LLM provider). The LLM provider can be swapped.

## Game state

Every change to a game is recorded as a domain event, such as `PromptSubmitted`, `ScriptGenerated`, or `RoundCompleted`.

1. A command arrives, and the domain checks it and emits an event.
2. The server appends the event to the log and updates a snapshot of the current state.
3. The server broadcasts the event to the room. Some events, such as the script, go only to the acting team.

After a crash, the server reloads each game's snapshot and resumes the current round if it can. If it can't, it restarts from the last `RoundCompleted`. When a player reconnects, they receive the full current state. Events are deleted when the game ends because history is session-only.

## Script generation

The LLM receives the prompt, the team's personality, the content setting, and the number of roles. It returns structured output: a title, one role per player (name and description), and the script text. The adapter validates the output and retries once if it fails. Each personality is a short prompt describing a style. We rely on the model's judgment for comedy and pacing instead of rigid rules.

## Key decisions

| Decision | Why | Trade-off |
| --- | --- | --- |
| Event sourcing | The game is a series of events. The log makes crash recovery and broadcasting simple. | More complex than basic create, read, update, delete storage |
| Hexagonal architecture | Domain logic can be tested on its own, and the LLM and storage can be swapped | More layers of abstraction |
| SQLite on one server | No operations work, and it's free at this scale | Can't scale horizontally |
| Socket.IO | Built-in rooms and reconnection | Connections are stateful |
| No accounts | Players join instantly | A room code is the only access control |

## Resilience and safety

- **LLM failures:** the server retries with backoff, then tells the room and lets the team retry.
- **Disconnects:** the client reconnects automatically, and the server sends a fresh snapshot.
- **Content:** the content setting is part of the prompt, and the output is moderated before display.
- **Abuse:** prompts are validated (six words maximum), requests are rate-limited, and room codes expire.

## Deployment

The app runs as one container on Fly.io, with SQLite on a persistent volume. The same server also serves the web app. CI (GitHub Actions) runs lint, type checks, and tests on every push.

## If it grows

Add Redis for state shared across instances, move from SQLite to Postgres, and run the WebSocket servers separately from the API. None of these changes reach the domain layer.
