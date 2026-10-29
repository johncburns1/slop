"""ID generator adapters: random ids for real games, sequential ones for tests."""

import secrets
from collections.abc import Iterable
from itertools import count
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from slop.ports.ids import IdGenerator

# Consonants only, so codes can't spell words, and no easily confused letters.
ROOM_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ"
ROOM_CODE_LENGTH = 4


class RandomIds:
    """UUID ids and random 4-letter room codes."""

    def new_id(self) -> str:
        """Return a random UUID."""
        return str(uuid4())

    def new_room_code(self) -> str:
        """Return a random code such as ``KXQB``."""
        return "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))


class SequentialIds:
    """Predictable ids (``id-1``, ``id-2``, ...) and room codes.

    Room codes come from ``room_codes`` in order, then ``ROOM1``, ``ROOM2``, ...
    Pass codes to test collisions, e.g. ``SequentialIds(["ABCD", "ABCD", "WXYZ"])``.
    """

    def __init__(self, room_codes: Iterable[str] = ()) -> None:
        self._ids = count(1)
        self._room_codes = iter(room_codes)
        self._fallback_codes = count(1)

    def new_id(self) -> str:
        """Return the next id."""
        return f"id-{next(self._ids)}"

    def new_room_code(self) -> str:
        """Return the next scripted room code, or a numbered one after those run out."""
        return next(self._room_codes, None) or f"ROOM{next(self._fallback_codes)}"


if TYPE_CHECKING:
    # mypy fails here if an adapter drifts from the port's signature.
    _random_check: IdGenerator = RandomIds()
    _sequential_check: IdGenerator = SequentialIds()
