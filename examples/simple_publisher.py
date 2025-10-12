#!/usr/bin/env python3
"""
Simple publisher example.

This example publishes string messages on a topic.

Note: Install easy-drone first with: pip install -e .
"""

import time
from gz_transport import Node

# You'll need to have protobuf message definitions
# For this example, we'll create a simple one
from google.protobuf.descriptor_pb2 import DescriptorProto
from google.protobuf import message_factory
from google.protobuf import descriptor_pool
from google.protobuf import descriptor_pb2


# Create a simple StringMsg for demonstration
def create_string_msg_type():
    """Create a simple StringMsg protobuf type dynamically."""
    # This is a workaround since we don't have gz-msgs compiled
    # In real usage, you would import from gz.msgs
    try:
        # Try to import gz-msgs if available
        from gz.msgs.stringmsg_pb2 import StringMsg
        return StringMsg
    except ImportError:
        print("Note: gz-msgs not found, using dynamic message type")
        print("Install gz-msgs for full compatibility")

        # Create a simple mock for demonstration
        class StringMsg:
            def __init__(self):
                self.data = ""

            def SerializeToString(self):
                return self.data.encode('utf-8')

            class DESCRIPTOR:
                full_name = "gz.msgs.StringMsg"

        return StringMsg


def main():
    # Create node
    node = Node(verbose=True)

    # Get message type
    StringMsg = create_string_msg_type()

    # Advertise topic
    topic = "/example"
    pub = node.advertise(topic, StringMsg)

    print(f"Publishing on topic: {topic}")
    print("Press Ctrl+C to stop")

    try:
        counter = 0
        while True:
            # Create message
            msg = StringMsg()
            msg.data = f"Hello World {counter}"

            # Publish
            if pub.publish(msg):
                print(f"Published: {msg.data}")
            else:
                print("Failed to publish")

            counter += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping...")

    # Cleanup
    node.shutdown()
    print("Done")


if __name__ == "__main__":
    main()
