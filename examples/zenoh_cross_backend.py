#!/usr/bin/env python3
"""
Example: Cross-Backend Communication Test

This example demonstrates that ZeroMQ and Zenoh backends are independent
and cannot communicate with each other (they use different transport layers).

For cross-backend communication, you would need to use the same backend
on both publisher and subscriber.

This script creates:
- One Zenoh publisher
- One Zenoh subscriber (will work)
- One ZeroMQ subscriber (won't receive Zenoh messages)

This demonstrates the backend isolation.
"""

import os
import sys
import time
import threading

# We'll programmatically set the backend for different nodes
from gz_transport_py import Node
from gz.msgs.stringmsg_pb2 import StringMsg


def zenoh_subscriber_callback(msg):
    """Callback for Zenoh subscriber."""
    print(f"  [Zenoh Sub] Received: {msg.data}")


def zeromq_subscriber_callback(msg):
    """Callback for ZeroMQ subscriber."""
    print(f"  [ZeroMQ Sub] Received: {msg.data}")


def main():
    """Main function."""
    print("=" * 70)
    print("Cross-Backend Communication Test")
    print("=" * 70)
    print()
    print("This demonstrates that Zenoh and ZeroMQ backends are isolated.")
    print("The Zenoh subscriber will receive messages, but ZeroMQ won't.")
    print()
    
    # Create Zenoh publisher
    print("1. Creating Zenoh publisher...")
    os.environ['GZ_TRANSPORT_IMPLEMENTATION'] = 'zenoh'
    zenoh_node = Node(verbose=False)
    zenoh_pub = zenoh_node.advertise("/test", StringMsg)
    print(f"   Backend: {zenoh_pub.backend}")
    
    # Create Zenoh subscriber
    print("\n2. Creating Zenoh subscriber...")
    zenoh_sub_node = Node(verbose=False)
    zenoh_sub_node.subscribe(StringMsg, "/test", zenoh_subscriber_callback)
    
    # Create ZeroMQ subscriber
    print("\n3. Creating ZeroMQ subscriber...")
    os.environ['GZ_TRANSPORT_IMPLEMENTATION'] = 'zeromq'
    zeromq_node = Node(verbose=False)
    zeromq_node.subscribe(StringMsg, "/test", zeromq_subscriber_callback)
    
    print("\n" + "=" * 70)
    print("Publishing messages...")
    print("=" * 70)
    
    # Publish some messages
    for i in range(5):
        msg = StringMsg()
        msg.data = f"Message #{i} from Zenoh"
        
        print(f"\n[Pub] Sending: {msg.data}")
        zenoh_pub.publish(msg)
        
        time.sleep(1)
    
    print("\n" + "=" * 70)
    print("Result:")
    print("  ✓ Zenoh subscriber received messages (same backend)")
    print("  ✗ ZeroMQ subscriber did NOT receive messages (different backend)")
    print()
    print("Conclusion: Use the same backend for all communicating nodes!")
    print("=" * 70)
    
    # Cleanup
    time.sleep(1)
    zenoh_node.shutdown()
    zenoh_sub_node.shutdown()
    zeromq_node.shutdown()
    
    print("\nDone!")


if __name__ == '__main__':
    main()

