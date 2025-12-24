"""Port interfaces for external systems.

Ports define contracts between the domain and external systems.
"""

from slop.ports.llm import LLMPort
from slop.ports.realtime import RealtimePort
from slop.ports.storage import StoragePort

__all__ = [
    "LLMPort",
    "RealtimePort",
    "StoragePort",
]
