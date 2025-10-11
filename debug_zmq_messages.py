#!/usr/bin/env python3
"""
Debug script to see raw ZMQ messages from Gazebo publisher.
This helps diagnose why messages aren't being received.
"""
import zmq
import sys
import time

if len(sys.argv) < 2:
    print("Usage: python debug_zmq_messages.py <publisher_address>")
    print("Example: python debug_zmq_messages.py tcp://172.17.0.1:45943")
    sys.exit(1)

address = sys.argv[1]
print(f"Connecting to: {address}")
print("This will show raw message parts received...")
print()

context = zmq.Context()
socket = context.socket(zmq.SUB)

# Try different subscription filters
print("Trying subscription filters:")
print("  1. Empty filter (receive all)")
socket.setsockopt(zmq.SUBSCRIBE, b"")
print("  2. Connected to:", address)
socket.connect(address)

# Set a reasonable timeout
socket.setsockopt(zmq.RCVTIMEO, 10000)  # 10 seconds

print()
print("Waiting for messages (timeout: 10s)...")
print("=" * 60)

try:
    while True:
        try:
            parts = socket.recv_multipart()
            print(f"\n[{time.strftime('%H:%M:%S')}] Received {len(parts)} parts:")
            
            for i, part in enumerate(parts):
                print(f"  Part {i}: {len(part)} bytes")
                # Show first 100 bytes as hex and try to decode as string
                preview = part[:100]
                print(f"    Hex: {preview.hex()[:80]}...")
                try:
                    text = part.decode('utf-8', errors='ignore')[:80]
                    if text.isprintable():
                        print(f"    Text: {text}...")
                except:
                    pass
            
            print("-" * 60)
            
        except zmq.Again:
            print("\nTimeout! No message received in 10 seconds.")
            print("\nPossible causes:")
            print("  1. Publisher not sending messages")
            print("  2. Different transport protocol (not ZeroMQ)")
            print("  3. Network/firewall blocking")
            print("  4. Publisher using different socket type")
            break
            
except KeyboardInterrupt:
    print("\n\nStopped by user")

socket.close()
context.term()

print("\nTo verify publisher is active:")
print(f"  gz topic -e -t <topic_name>")

