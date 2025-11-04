#!/usr/bin/env python3
"""
Simple test to verify basic functionality.

This creates a publisher and subscriber in the same process to test basic operations.
"""

import time
import threading
from gz_transport import Node


# Simple message type for testing
class TestMsg:
    def __init__(self, text=""):
        self.data = text
    
    def SerializeToString(self):
        return self.data.encode('utf-8')
    
    def ParseFromString(self, data):
        self.data = data.decode('utf-8')
    
    class DESCRIPTOR:
        full_name = "TestMsg"


def test_basic_pubsub():
    """Test basic publish/subscribe functionality."""
    print("=" * 50)
    print("TEST: Basic Pub/Sub")
    print("=" * 50)
    
    received_messages = []
    
    def callback(msg):
        received_messages.append(msg.data)
        print(f"  ✓ Received: {msg.data}")
    
    # Create subscriber node
    print("\n1. Creating subscriber node...")
    sub_node = Node(verbose=False)
    sub_node.subscribe(TestMsg, "/test_topic", callback)
    print("   ✓ Subscriber ready")
    
    # Wait for discovery to initialize
    time.sleep(0.5)
    
    # Create publisher node
    print("\n2. Creating publisher node...")
    pub_node = Node(verbose=False)
    pub = pub_node.advertise("/test_topic", TestMsg)
    print("   ✓ Publisher ready")
    
    # Wait for discovery
    time.sleep(1.0)
    
    # Publish messages
    print("\n3. Publishing messages...")
    for i in range(5):
        msg = TestMsg(f"Message {i}")
        pub.publish(msg)
        print(f"   → Sent: Message {i}")
        time.sleep(0.2)
    
    # Wait for messages to arrive
    time.sleep(0.5)
    
    # Check results
    print("\n4. Checking results...")
    print(f"   Messages sent: 5")
    print(f"   Messages received: {len(received_messages)}")
    
    # Cleanup
    print("\n5. Cleaning up...")
    pub_node.shutdown()
    sub_node.shutdown()
    print("   ✓ Cleanup complete")
    
    # Verify
    if len(received_messages) >= 4:  # Allow some loss due to timing
        print("\n✅ TEST PASSED")
        return True
    else:
        print(f"\n❌ TEST FAILED: Only received {len(received_messages)}/5 messages")
        return False


def test_multiple_topics():
    """Test multiple topics simultaneously."""
    print("\n" + "=" * 50)
    print("TEST: Multiple Topics")
    print("=" * 50)
    
    topic1_msgs = []
    topic2_msgs = []
    
    def callback1(msg):
        topic1_msgs.append(msg.data)
    
    def callback2(msg):
        topic2_msgs.append(msg.data)
    
    print("\n1. Setting up nodes...")
    node = Node(verbose=False)
    
    # Subscribe to two topics
    node.subscribe(TestMsg, "/topic1", callback1)
    node.subscribe(TestMsg, "/topic2", callback2)
    
    # Advertise two topics
    pub1 = node.advertise("/topic1", TestMsg)
    pub2 = node.advertise("/topic2", TestMsg)
    
    time.sleep(0.5)
    
    print("\n2. Publishing to multiple topics...")
    for i in range(3):
        msg1 = TestMsg(f"Topic1-{i}")
        msg2 = TestMsg(f"Topic2-{i}")
        pub1.publish(msg1)
        pub2.publish(msg2)
        time.sleep(0.1)
    
    time.sleep(0.5)
    
    print(f"\n3. Results:")
    print(f"   Topic1 received: {len(topic1_msgs)} messages")
    print(f"   Topic2 received: {len(topic2_msgs)} messages")
    
    node.shutdown()
    
    if len(topic1_msgs) >= 2 and len(topic2_msgs) >= 2:
        print("\n✅ TEST PASSED")
        return True
    else:
        print("\n❌ TEST FAILED")
        return False


def test_topic_discovery():
    """Test topic discovery."""
    print("\n" + "=" * 50)
    print("TEST: Topic Discovery")
    print("=" * 50)
    
    print("\n1. Creating nodes with topics...")
    node1 = Node(verbose=False)
    node2 = Node(verbose=False)
    
    pub1 = node1.advertise("/discovery_test_1", TestMsg)
    pub2 = node2.advertise("/discovery_test_2", TestMsg)
    
    time.sleep(1.0)
    
    print("\n2. Discovering topics...")
    topics = node1.topic_list()
    
    print(f"\n3. Found topics: {topics}")
    
    # Check if our topics are discovered
    has_topic1 = "/discovery_test_1" in topics
    has_topic2 = "/discovery_test_2" in topics
    
    print(f"   Found /discovery_test_1: {has_topic1}")
    print(f"   Found /discovery_test_2: {has_topic2}")
    
    node1.shutdown()
    node2.shutdown()
    
    if has_topic1 and has_topic2:
        print("\n✅ TEST PASSED")
        return True
    else:
        print("\n❌ TEST FAILED: Not all topics discovered")
        return False


def test_unadvertise():
    """Test unadvertising topics."""
    print("\n" + "=" * 50)
    print("TEST: Unadvertise")
    print("=" * 50)
    
    print("\n1. Creating publisher...")
    node = Node(verbose=False)
    pub = node.advertise("/temp_topic", TestMsg)
    
    time.sleep(0.5)
    
    print("\n2. Checking advertised topics...")
    topics = node.advertised_topics()
    print(f"   Advertised: {topics}")
    
    print("\n3. Unadvertising topic...")
    node.unadvertise("/temp_topic")
    
    time.sleep(0.2)
    
    print("\n4. Checking advertised topics again...")
    topics = node.advertised_topics()
    print(f"   Advertised: {topics}")
    
    node.shutdown()
    
    if len(topics) == 0:
        print("\n✅ TEST PASSED")
        return True
    else:
        print("\n❌ TEST FAILED: Topic still advertised")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("GZ-TRANSPORT-PY TEST SUITE")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(("Basic Pub/Sub", test_basic_pubsub()))
    time.sleep(1)
    
    results.append(("Multiple Topics", test_multiple_topics()))
    time.sleep(1)
    
    results.append(("Topic Discovery", test_topic_discovery()))
    time.sleep(1)
    
    results.append(("Unadvertise", test_unadvertise()))
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")
    
    print("\n" + "=" * 50)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 50)
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())

