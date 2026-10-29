"""Storage adapters.

Implementations for game state persistence (in-memory, database, etc.)
that implement the StoragePort interface.
"""

from slop.adapters.storage.in_memory import InMemoryStorage
from slop.adapters.storage.sqlite import SQLiteStorage

__all__ = ["InMemoryStorage", "SQLiteStorage"]
