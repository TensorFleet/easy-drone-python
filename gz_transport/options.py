"""
Configuration options for nodes, publishers, and subscribers.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict


class Scope(Enum):
    """Scope of topic/service advertisement."""
    PROCESS = "process"  # Only within same process
    HOST = "host"        # Only within same machine
    ALL = "all"          # Across network


@dataclass
class AdvertiseOptions:
    """Options for advertising topics."""
    scope: Scope = Scope.ALL
    
    def __post_init__(self):
        if isinstance(self.scope, str):
            self.scope = Scope(self.scope)


@dataclass
class SubscribeOptions:
    """Options for subscribing to topics."""
    throttled: bool = False
    msgs_per_sec: float = 0.0  # 0 means no throttling


@dataclass
class NodeOptions:
    """Options for configuring a transport node."""
    namespace: str = ""
    partition: str = ""
    topic_remaps: Dict[str, str] = field(default_factory=dict)
    
    def add_topic_remap(self, from_topic: str, to_topic: str):
        """Add a topic remapping."""
        self.topic_remaps[from_topic] = to_topic
    
    def get_remapped_topic(self, topic: str) -> str:
        """Get the remapped topic name if it exists."""
        return self.topic_remaps.get(topic, topic)

