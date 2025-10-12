#!/usr/bin/env python3
"""
Example using actual gz-msgs if available.

This demonstrates full compatibility with the C++ gz-transport.

Note: Install easy-drone first with: pip install -e .
"""

import time
import sys
from gz_transport import Node

# Try to import gz-msgs
try:
    from gz.msgs.stringmsg_pb2 import StringMsg
    from gz.msgs.vector3d_pb2 import Vector3d
    HAVE_GZ_MSGS = True
    print("✓ Using gz-msgs")
except ImportError:
    HAVE_GZ_MSGS = False
    print("✗ gz-msgs not found")
    print("  Install: pip install gz-msgs (if available)")
    sys.exit(1)


def string_callback(msg):
    """Callback for StringMsg."""
    print(f"  StringMsg: {msg.data}")


def vector3_callback(msg):
    """Callback for Vector3d."""
    print(f"  Vector3d: x={msg.x}, y={msg.y}, z={msg.z}")


def publisher_example():
    """Run publisher."""
    print("\n=== Publisher Mode ===")
    node = Node(verbose=True)

    # Advertise multiple topics
    string_pub = node.advertise("/string_topic", StringMsg)
    vector_pub = node.advertise("/vector_topic", Vector3d)

    print("Publishing messages... (Ctrl+C to stop)")

    try:
        counter = 0
        while True:
            # Publish string message
            string_msg = StringMsg()
            string_msg.data = f"Message {counter}"
            string_pub.publish(string_msg)

            # Publish vector message
            vector_msg = Vector3d()
            vector_msg.x = counter
            vector_msg.y = counter * 2
            vector_msg.z = counter * 3
            vector_pub.publish(vector_msg)

            print(f"Published #{counter}")
            counter += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping publisher...")

    node.shutdown()


def subscriber_example():
    """Run subscriber."""
    print("\n=== Subscriber Mode ===")
    node = Node(verbose=True)

    # Subscribe to multiple topics
    node.subscribe(StringMsg, "/string_topic", string_callback)
    node.subscribe(Vector3d, "/vector_topic", vector3_callback)

    print("Waiting for messages... (Ctrl+C to stop)")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping subscriber...")

    node.shutdown()


def list_topics():
    """List all topics."""
    print("\n=== Topic Discovery ===")
    node = Node()

    print("Discovering topics...")
    time.sleep(2)

    topics = node.topic_list()

    if topics:
        print(f"\nFound {len(topics)} topic(s):")
        for topic in sorted(topics):
            print(f"  • {topic}")
    else:
        print("\nNo topics found")

    node.shutdown()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 with_gz_msgs.py pub       # Run publisher")
        print("  python3 with_gz_msgs.py sub       # Run subscriber")
        print("  python3 with_gz_msgs.py list      # List topics")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "pub":
        publisher_example()
    elif mode == "sub":
        subscriber_example()
    elif mode == "list":
        list_topics()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
