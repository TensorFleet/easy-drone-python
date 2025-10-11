"""
Pure Python implementation of Gazebo Transport.

This is a minimal implementation of gz-transport that provides:
- Pub/Sub messaging
- Automatic discovery via UDP multicast
- ZeroMQ for data transport
- Protobuf message serialization
"""

from .node import Node
from .publisher import Publisher
from .options import (
    NodeOptions,
    AdvertiseOptions,
    SubscribeOptions,
    Scope
)

__version__ = "0.1.0"
__all__ = [
    "Node",
    "Publisher",
    "NodeOptions",
    "AdvertiseOptions",
    "SubscribeOptions",
    "Scope",
]

