"""
Publisher implementation using ZeroMQ.
"""

import zmq
from typing import Optional


class Publisher:
    """
    A publisher that sends messages on a topic.
    """
    
    def __init__(self, socket: zmq.Socket, topic: str, msg_type: str, address: str):
        self.socket = socket
        self.topic = topic
        self.msg_type = msg_type
        self.address = address
        self._valid = True
    
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
            print(f"[Publisher] Error publishing: {e}")
            return False
    
    def publish_raw(self, msg_bytes: bytes, msg_type: str) -> bool:
        """
        Publish raw serialized message bytes.
        
        Args:
            msg_bytes: Serialized message data
            msg_type: Message type name
            
        Returns:
            True if successful, False otherwise
        """
        if not self._valid:
            return False
        
        try:
            self.socket.send_multipart([
                self.topic.encode('utf-8'),
                msg_bytes
            ])
            return True
        except Exception as e:
            print(f"[Publisher] Error publishing raw: {e}")
            return False
    
    def invalidate(self):
        """Mark this publisher as invalid."""
        self._valid = False
    
    def valid(self) -> bool:
        """Check if publisher is valid."""
        return self._valid

