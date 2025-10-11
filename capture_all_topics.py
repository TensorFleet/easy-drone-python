#!/usr/bin/env python3
"""
Capture all topics from the publisher for 30 seconds to see if camera messages arrive.
"""
import zmq
import sys
import time
from collections import Counter

if len(sys.argv) < 2:
    print("Usage: python capture_all_topics.py <publisher_address>")
    sys.exit(1)

address = sys.argv[1]
print(f"Connecting to: {address}")
print("Capturing ALL topics for 30 seconds...")
print("=" * 80)

context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.setsockopt(zmq.SUBSCRIBE, b"@")  # Subscribe to all partitioned topics
socket.connect(address)
socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout

topic_counts = Counter()
topic_samples = {}
start_time = time.time()
total_messages = 0

try:
    while time.time() - start_time < 30:  # Run for 30 seconds
        try:
            parts = socket.recv_multipart()
            total_messages += 1
            
            if len(parts) >= 1:
                # Extract topic from part 0
                topic_with_prefix = parts[0].decode('utf-8', errors='ignore')
                if '@' in topic_with_prefix:
                    topic_parts = topic_with_prefix.split('@')
                    topic = topic_parts[-1]
                else:
                    topic = topic_with_prefix
                
                topic_counts[topic] += 1
                
                # Store first sample
                if topic not in topic_samples:
                    topic_samples[topic] = {
                        'parts': len(parts),
                        'size': len(parts[2]) if len(parts) >= 3 else 0,
                        'type': parts[3].decode('utf-8', errors='ignore') if len(parts) >= 4 else 'unknown'
                    }
                    print(f"✓ New topic discovered: {topic}")
                
        except zmq.Again:
            continue
        except KeyboardInterrupt:
            break

except KeyboardInterrupt:
    pass

socket.close()
context.term()

# Print summary
print("\n" + "=" * 80)
print(f"SUMMARY - Captured {total_messages} messages in {int(time.time() - start_time)} seconds")
print("=" * 80)

for topic, count in topic_counts.most_common():
    sample = topic_samples[topic]
    print(f"\n📊 Topic: {topic}")
    print(f"   Count: {count} messages")
    print(f"   Format: {sample['parts']} parts, data size: {sample['size']} bytes")
    print(f"   Type: {sample['type']}")

# Check for camera topic
camera_found = any('camera' in topic.lower() or 'image' in topic.lower() for topic in topic_counts.keys())
print("\n" + "=" * 80)
if camera_found:
    print("✅ CAMERA TOPIC FOUND!")
else:
    print("❌ NO CAMERA TOPIC RECEIVED")
    print("\nThis means:")
    print("  1. Camera messages aren't coming through this connection")
    print("  2. OR camera publishes very infrequently (> 30 seconds)")
    print("  3. OR camera topic has unexpected name")
print("=" * 80)

