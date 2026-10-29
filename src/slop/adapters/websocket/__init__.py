"""WebSocket adapters.

Implementations for real-time communication (Socket.io, etc.)
that implement the RealtimePort interface.
"""

from slop.adapters.websocket.recording import Delivery, RecordingRealtime

__all__ = ["Delivery", "RecordingRealtime"]
