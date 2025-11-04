#!/usr/bin/env python3
"""
Example: Zenoh-based Subscriber

This example demonstrates how to use gz-transport with the Zenoh backend.

To use Zenoh backend:
1. Install zenoh: pip install eclipse-zenoh
2. Set environment variable: export GZ_TRANSPORT_IMPLEMENTATION=zenoh
3. Run this script in one terminal
4. Run zenoh_publisher.py in another terminal

The API is exactly the same as with ZeroMQ - the only difference is the
environment variable that selects the backend.
"""

import os
import sys
import time

# Set Zenoh implementation before importing gz_transport
os.environ['GZ_TRANSPORT_IMPLEMENTATION'] = 'zenoh'

from gz_transport import Node
from gz.msgs.stringmsg_pb2 import StringMsg


# Global counter for received messages
received_count = 0


def message_callback(msg):
    """Callback for received messages."""
    global received_count
    received_count += 1
    print(f"[{received_count:4d}] Received: {msg.data}")


def main():
    """Main function."""
    print("=" * 60)
    print("Zenoh Subscriber Example")
    print("=" * 60)
    print()
    print("Environment:")
    print(f"  GZ_TRANSPORT_IMPLEMENTATION={os.environ.get('GZ_TRANSPORT_IMPLEMENTATION')}")
    print()
    
    # Create node (will use Zenoh backend based on environment variable)
    print("Creating node...")
    node = Node(verbose=True)
    
    # Subscribe to a topic
    topic = "/chatter"
    print(f"\nSubscribing to topic: {topic}")
    node.subscribe(StringMsg, topic, message_callback)
    
    print()
    print("Waiting for messages (Ctrl+C to stop)...")
    print("-" * 60)
    
    # Keep running
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n")
        print("-" * 60)
        print(f"Received {received_count} messages total")
        print("Shutting down...")
    
    # Cleanup
    node.shutdown()
    print("Done!")


if __name__ == '__main__':
    main()

