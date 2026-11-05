"""Application layer: one module per use case, all following the same flow.

A use case is an async function ``use_case(deps, command) -> Game`` in its own
module (see ``create_game`` for the model), where ``deps`` is an
``engine.GameDeps`` holding the ports (storage, realtime, LLM, moderation), a
clock, and an id generator, and ``command`` is a frozen dataclass. It:

1. Takes the game's lock and loads it with ``engine.locked_game``, or
   ``engine.locked_room`` for a room code.
2. Checks the command against the domain rules, raising
   ``slop.domain.errors.GameRuleError`` before emitting anything. Text a
   player sends goes through ``moderation.check_player_text`` here too.
3. Builds the domain event(s). Leave ``event_id`` and ``timestamp`` unset.
4. Calls ``engine.commit(deps, game, events)``, which stamps the events,
   applies them with ``slop.domain.projection.apply_event``, appends them
   with ``save_event``, saves the snapshot, and broadcasts them to the room.
   Wrap an event in ``engine.Private`` to send it only to some players.

Commands for one game run one at a time, from load through snapshot save,
because each would otherwise save a snapshot built from what it loaded and
overwrite whatever another saved meanwhile. Different games run concurrently.
``commit`` raises unless its caller holds the lock. The lock is an in-process
``asyncio.Lock``, one per game id in ``GameDeps.locks``, which is enough because
the server is a single process (one container, with SQLite; see
``ARCHITECTURE.md``). Each lock exists only while a task holds or awaits it, so
expired games leave none behind. It isn't reentrant: to run one use case's steps
inside another, call a helper that takes the locked game (see ``move_on``).

Never hold the lock across a slow call (moderation, the LLM), since that would
stall the whole room. Instead: load and check under the lock, release it, make
the slow call, then take the lock again to reload the game, check everything
again against what may have changed, and commit (see ``submit_guess``). Anything
worked out from the first load is stale by then, and the game may be gone.

State changes only through events. A new event type needs a ``case`` in
``apply_event`` and an entry in ``tests/event_logs.py``. Test use cases with
the stand-in fixtures in ``tests/application/conftest.py``.
"""
