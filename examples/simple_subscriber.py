#!/usr/bin/env python3
"""
Simple subscriber example.

This example subscribes to string messages on a topic.

Note: Install easy-drone first with: pip install -e .

Usage:
  python simple_subscriber.py [topic]
  
Environment Variables:
  GZ_PUBLISHER_ADDRESS - Direct publisher address (bypasses discovery)
                         Example: tcp://172.17.0.1:45943
"""

import os
import time
import sys
from gz_transport import Node


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
    # Get topic from command line or use default
    topic = sys.argv[1] if len(sys.argv) > 1 else "/example"

    # Get publisher address from environment
    publisher_address = os.getenv('GZ_PUBLISHER_ADDRESS')

    # Create node
    node = Node(verbose=True)

    # Get message type
    StringMsg = create_string_msg_type()

    # Subscribe to topic
    if publisher_address:
        print(f"Using direct publisher address: {publisher_address}")
        node.subscribe(StringMsg, topic, callback,
                       publisher_address=publisher_address)
    else:
        node.subscribe(StringMsg, topic, callback)

    print(f"Subscribed to topic: {topic}")
    if not publisher_address:
        print(
            "Note: Using discovery. If no messages arrive, try setting GZ_PUBLISHER_ADDRESS")
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
