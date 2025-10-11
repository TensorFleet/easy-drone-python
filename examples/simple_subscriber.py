#!/usr/bin/env python3
"""
Simple subscriber example.

This example subscribes to string messages on a topic.
"""

import time
import sys
sys.path.insert(0, '..')

from gz_transport_py import Node


# Create a simple StringMsg for demonstration
def create_string_msg_type():
    """Create a simple StringMsg protobuf type dynamically."""
    try:
        # Try to import gz-msgs if available
        from gz.msgs.stringmsg_pb2 import StringMsg
        return StringMsg
    except ImportError:
        print("Note: gz-msgs not found, using dynamic message type")
        
        # Create a simple mock for demonstration
        class StringMsg:
            def __init__(self):
                self.data = ""
            
            def ParseFromString(self, data):
                self.data = data.decode('utf-8')
            
            class DESCRIPTOR:
                full_name = "gz.msgs.StringMsg"
        
        return StringMsg


def callback(msg):
    """Callback function for received messages."""
    print(f"Received: {msg.data}")


def main():
    # Create node
    node = Node(verbose=True)
    
    # Get message type
    StringMsg = create_string_msg_type()
    
    # Subscribe to topic
    topic = "/example"
    node.subscribe(StringMsg, topic, callback)
    
    print(f"Subscribed to topic: {topic}")
    print("Waiting for messages... (Press Ctrl+C to stop)")
    
    try:
        # Keep running
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    
    # Cleanup
    node.shutdown()
    print("Done")


if __name__ == "__main__":
    main()

