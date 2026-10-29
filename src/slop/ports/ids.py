"""ID generator port interface.

Use cases get new ids and room codes through this port so tests can
predict them.
"""

from typing import Protocol


class IdGenerator(Protocol):
    """Source of new unique ids and candidate room codes."""

    def new_id(self) -> str:
        """Return an id not returned before, for games, events, and so on."""
        ...

    def new_room_code(self) -> str:
        """Return a candidate room code of 4-6 characters.

        Codes need not be unique: the caller checks storage and asks again
        if the code is taken.
        """
        ...
