#!/usr/bin/env python3
"""
Test different ZMQ subscription patterns to find what works with C++ gz-transport.
"""
import zmq
import sys
import time
import threading

if len(sys.argv) < 3:
    print("Usage: python test_zmq_subscription.py <publisher_address> <topic>")
    print("Example: python test_zmq_subscription.py tcp://172.17.0.1:45943 /world/...")
    sys.exit(1)

address = sys.argv[1]
topic = sys.argv[2]

print(f"Testing ZMQ subscriptions to: {address}")
print(f"Topic: {topic}")
print()

def test_subscription(filter_value, description):
    """Test a specific subscription filter."""
    print(f"\n{'='*70}")
    print(f"Test: {description}")
    print(f"Filter: {repr(filter_value)}")
    print('='*70)
    
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    
    # Set subscription filter
    if isinstance(filter_value, str):
        socket.setsockopt_string(zmq.SUBSCRIBE, filter_value)
    else:
        socket.setsockopt(zmq.SUBSCRIBE, filter_value)
    
    socket.connect(address)
    socket.setsockopt(zmq.RCVTIMEO, 3000)  # 3 second timeout
    
    print("Waiting for message (3s timeout)...")
    
    try:
        parts = socket.recv_multipart()
        print(f"✓ SUCCESS! Received {len(parts)} parts")
        
        for i, part in enumerate(parts):
            print(f"\n  Part {i}: {len(part)} bytes")
            preview = part[:200]
            print(f"    Hex: {preview.hex()[:100]}")
            try:
                text = part.decode('utf-8', errors='ignore')[:100]
                if any(c.isprintable() or c.isspace() for c in text):
                    print(f"    Text preview: {repr(text)}")
            except:
                pass
        
        return True
        
    except zmq.Again:
        print("✗ TIMEOUT - No message received")
        return False
    
    finally:
        socket.close()
        context.term()
        time.sleep(0.5)  # Give socket time to close

# Test different subscription patterns
tests = [
    (b"", "Empty filter (receive all messages)"),
    (topic.encode('utf-8'), "Topic as bytes"),
    (topic, "Topic as string"),
    (b"/", "Root prefix /"),
    (topic.split('/')[0].encode('utf-8') if '/' in topic else b"", "First part of topic"),
]

print("\nRunning tests...")
print("(Each test has 3 second timeout)")

results = []
for filter_val, desc in tests:
    success = test_subscription(filter_val, desc)
    results.append((desc, success))
    time.sleep(1)  # Brief pause between tests

# Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70)

for desc, success in results:
    status = "✓ WORKS" if success else "✗ FAILED"
    print(f"{status}: {desc}")

if any(success for _, success in results):
    print("\n" + "="*70)
    print("SOLUTION FOUND!")
    print("="*70)
    working = [desc for desc, success in results if success]
    print(f"Working filter(s): {', '.join(working)}")
    
    if results[0][1]:  # Empty filter works
        print("\n→ C++ publisher sends messages without topic prefix in filter")
        print("→ Need to modify Python subscriber to use empty filter")
        print("→ Then check topic from message content")
else:
    print("\n" + "="*70)
    print("NO SOLUTION FOUND")
    print("="*70)
    print("Possible causes:")
    print("  1. Publisher not actively sending messages")
    print("  2. Not using standard ZeroMQ PUB/SUB")
    print("  3. Additional handshake or protocol required")
    print("  4. Network/firewall issue")
    print("\nVerify with: gz topic -e -t", topic)

