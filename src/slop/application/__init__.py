"""Application layer: one module per use case, all following the same flow.

A use case is an async function ``use_case(deps, command) -> Game`` in its own
module (see ``create_game`` for the model), where ``deps`` is an
``engine.GameDeps`` holding the ports, a clock, and an id generator, and
``command`` is a frozen dataclass. It:

1. Loads the game with ``engine.load_game`` or ``engine.find_game``.
2. Checks the command against the domain rules, raising
   ``slop.domain.errors.GameRuleError`` before emitting anything.
3. Builds the domain event(s). Leave ``event_id`` and ``timestamp`` unset.
4. Calls ``engine.commit(deps, game, events)``, which stamps the events,
   applies them with ``slop.domain.projection.apply_event``, appends them
   with ``save_event``, saves the snapshot, and broadcasts them to the room.
   Wrap an event in ``engine.Private`` to send it only to some players.

State changes only through events. A new event type needs a ``case`` in
``apply_event`` and an entry in ``tests/event_logs.py``. Test use cases with
the stand-in fixtures in ``tests/application/conftest.py``.
"""
