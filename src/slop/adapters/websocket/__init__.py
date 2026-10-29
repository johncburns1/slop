"""WebSocket adapters.

Implementations for real-time communication (Socket.io, etc.)
that implement the RealtimePort interface.
"""

from slop.adapters.websocket.recording import Delivery, RecordingRealtime
from slop.adapters.websocket.socket_io import SocketIORealtime

__all__ = ["Delivery", "RecordingRealtime", "SocketIORealtime"]
