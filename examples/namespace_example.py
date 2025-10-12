#!/usr/bin/env python3
"""
Example demonstrating namespaces and partitions.

This shows how to isolate topics using namespaces and partitions.

Note: Install easy-drone first with: pip install -e .
"""

import time
import sys
from gz_transport_py import Node, NodeOptions


# Simple message type for demonstration
class SimpleMsg:
    def __init__(self, text=""):
        self.data = text

    def SerializeToString(self):
        return self.data.encode('utf-8')

    def ParseFromString(self, data):
        self.data = data.decode('utf-8')

    class DESCRIPTOR:
        full_name = "SimpleMsg"


def robot1_publisher():
    """Publisher for robot1 namespace."""
    options = NodeOptions(namespace="robot1")
    node = Node(options, verbose=True)

    # This will actually publish on "/robot1/status"
    pub = node.advertise("/status", SimpleMsg)

    print("Robot1 publisher started")

    try:
        counter = 0
        while True:
            msg = SimpleMsg(f"Robot1 status: {counter}")
            pub.publish(msg)
            print(f"Robot1 sent: {counter}")
            counter += 1
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    node.shutdown()


def robot2_publisher():
    """Publisher for robot2 namespace."""
    options = NodeOptions(namespace="robot2")
    node = Node(options, verbose=True)

    # This will actually publish on "/robot2/status"
    pub = node.advertise("/status", SimpleMsg)

    print("Robot2 publisher started")

    try:
        counter = 0
        while True:
            msg = SimpleMsg(f"Robot2 status: {counter}")
            pub.publish(msg)
            print(f"Robot2 sent: {counter}")
            counter += 1
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    node.shutdown()


def robot1_subscriber():
    """Subscriber for robot1 namespace."""
    options = NodeOptions(namespace="robot1")
    node = Node(options, verbose=True)

    def callback(msg):
        print(f"Robot1 received: {msg.data}")

    # This will subscribe to "/robot1/status"
    node.subscribe(SimpleMsg, "/status", callback)

    print("Robot1 subscriber started")
    print("Listening to /robot1/status")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    node.shutdown()


def robot2_subscriber():
    """Subscriber for robot2 namespace."""
    options = NodeOptions(namespace="robot2")
    node = Node(options, verbose=True)

    def callback(msg):
        print(f"Robot2 received: {msg.data}")

    # This will subscribe to "/robot2/status"
    node.subscribe(SimpleMsg, "/status", callback)

    print("Robot2 subscriber started")
    print("Listening to /robot2/status")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    node.shutdown()


def monitor_all():
    """Monitor all robot topics."""
    node = Node(verbose=False)

    def robot1_callback(msg):
        print(f"[Robot1] {msg.data}")

    def robot2_callback(msg):
        print(f"[Robot2] {msg.data}")

    # Subscribe to both namespaced topics
    node.subscribe(SimpleMsg, "/robot1/status", robot1_callback)
    node.subscribe(SimpleMsg, "/robot2/status", robot2_callback)

    print("Monitoring all robots...")

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    node.shutdown()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 namespace_example.py robot1-pub")
        print("  python3 namespace_example.py robot1-sub")
        print("  python3 namespace_example.py robot2-pub")
        print("  python3 namespace_example.py robot2-sub")
        print("  python3 namespace_example.py monitor")
        print()
        print("Try running:")
        print("  Terminal 1: python3 namespace_example.py robot1-pub")
        print("  Terminal 2: python3 namespace_example.py robot2-pub")
        print("  Terminal 3: python3 namespace_example.py monitor")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "robot1-pub":
        robot1_publisher()
    elif mode == "robot1-sub":
        robot1_subscriber()
    elif mode == "robot2-pub":
        robot2_publisher()
    elif mode == "robot2-sub":
        robot2_subscriber()
    elif mode == "monitor":
        monitor_all()
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
