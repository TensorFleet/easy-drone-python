"""
Publisher implementation supporting both ZeroMQ and Zenoh backends.
"""

import zmq
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .zenoh_backend import ZenohPublisher


class Publisher:
    """
    A publisher that sends messages on a topic.
    
    Supports both ZeroMQ and Zenoh backends.
    """
    
    def __init__(self, socket: Optional[zmq.Socket], topic: str, msg_type: str, 
                 address: str, zenoh_publisher: Optional['ZenohPublisher'] = None):
        self.socket = socket
        self.topic = topic
        self.msg_type = msg_type
        self.address = address
        self.zenoh_publisher = zenoh_publisher
        self._valid = True
        
        # Determine backend
        self.backend = 'zenoh' if zenoh_publisher is not None else 'zeromq'
    
    def publish(self, proto_msg) -> bool:
        """
        Publish a protobuf message.
        
        Args:
            proto_msg: A protobuf message instance
            
        Returns:
            True if successful, False otherwise
        """
        if not self._valid:
            return False
        
        if self.backend == 'zeromq':
            try:
                # Serialize the protobuf message
                msg_bytes = proto_msg.SerializeToString()
                
                # Send topic name followed by message data
                self.socket.send_multipart([
                    self.topic.encode('utf-8'),
                    msg_bytes
                ])
                return True
            except Exception as e:
                print(f"[Publisher] Error publishing (ZeroMQ): {e}")
                return False
        
        elif self.backend == 'zenoh':
            return self.zenoh_publisher.publish(proto_msg)
        
        return False
    
    def publish_raw(self, msg_bytes: bytes, msg_type: str = None) -> bool:
        """
        Publish raw serialized message bytes.
        
        Args:
            msg_bytes: Serialized message data
            msg_type: Message type name (optional, ignored for backward compatibility)
            
        Returns:
            True if successful, False otherwise
        """
        if not self._valid:
            return False
        
        if self.backend == 'zeromq':
            try:
                self.socket.send_multipart([
                    self.topic.encode('utf-8'),
                    msg_bytes
                ])
                return True
            except Exception as e:
                print(f"[Publisher] Error publishing raw (ZeroMQ): {e}")
                return False
        
        elif self.backend == 'zenoh':
            return self.zenoh_publisher.publish_raw(msg_bytes)
        
        return False
    
    def invalidate(self):
        """Mark this publisher as invalid."""
        self._valid = False
        if self.backend == 'zenoh' and self.zenoh_publisher:
            self.zenoh_publisher.invalidate()
    
    def valid(self) -> bool:
        """Check if publisher is valid."""
        if self.backend == 'zenoh' and self.zenoh_publisher:
            return self._valid and self.zenoh_publisher.valid()
        return self._valid

