#!/usr/bin/env python3
"""
Example: Zenoh-based Publisher

This example demonstrates how to use gz-transport with the Zenoh backend.

To use Zenoh backend:
1. Install zenoh: pip install eclipse-zenoh
2. Set environment variable: export GZ_TRANSPORT_IMPLEMENTATION=zenoh
3. Run this script

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


def main():
    """Main function."""
    print("=" * 60)
    print("Zenoh Publisher Example")
    print("=" * 60)
    print()
    print("Environment:")
    print(f"  GZ_TRANSPORT_IMPLEMENTATION={os.environ.get('GZ_TRANSPORT_IMPLEMENTATION')}")
    print()
    
    # Create node (will use Zenoh backend based on environment variable)
    print("Creating node...")
    node = Node(verbose=True)
    
    # Advertise a topic
    topic = "/chatter"
    print(f"\nAdvertising topic: {topic}")
    pub = node.advertise(topic, StringMsg)
    
    print(f"\nPublisher backend: {pub.backend}")
    print()
    
    # Publish messages in a loop
    print("Publishing messages (Ctrl+C to stop)...")
    print("-" * 60)
    
    count = 0
    try:
        while True:
            # Create message
            msg = StringMsg()
            msg.data = f"Hello from Zenoh! Message #{count}"
            
            # Publish
            success = pub.publish(msg)
            
            if success:
                print(f"[{count:4d}] Published: {msg.data}")
            else:
                print(f"[{count:4d}] Failed to publish")
            
            count += 1
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n")
        print("-" * 60)
        print("Shutting down...")
    
    # Cleanup
    node.shutdown()
    print("Done!")


if __name__ == '__main__':
    main()

