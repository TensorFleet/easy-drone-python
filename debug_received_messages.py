#!/usr/bin/env python3
"""
Debug script to see what message parts are actually being received.
Run this to understand the C++ gz-transport message format.
"""
import zmq
import sys

if len(sys.argv) < 2:
    print("Usage: python debug_received_messages.py <publisher_address>")
    print("Example: python debug_received_messages.py tcp://172.17.0.1:45943")
    sys.exit(1)

address = sys.argv[1]
print(f"Connecting to: {address}")
print("Will show structure of received messages...\n")

context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.setsockopt(zmq.SUBSCRIBE, b"")  # Empty filter - receive all
socket.connect(address)
socket.setsockopt(zmq.RCVTIMEO, 10000)  # 10 second timeout

print("Waiting for messages...")
print("=" * 80)

for i in range(5):  # Capture 5 messages
    try:
        parts = socket.recv_multipart()
        print(f"\n📦 Message {i+1}:")
        print(f"   Total parts: {len(parts)}")
        
        for j, part in enumerate(parts):
            print(f"\n   Part {j}: {len(part)} bytes")
            
            # Try to decode as string
            try:
                text = part.decode('utf-8', errors='ignore')
                if text.isprintable() or '\n' in text:
                    print(f"      As text: {text[:100]}")
            except:
                pass
            
            # Show hex preview
            hex_preview = part[:40].hex()
            print(f"      As hex: {hex_preview}")
            
            # Try to parse as protobuf if it's a larger part
            if len(part) > 1000:
                print(f"      → Likely protobuf data (large)")
                try:
                    from gz.msgs.image_pb2 import Image
                    msg = Image()
                    msg.ParseFromString(part)
                    print(f"      ✓ Successfully parsed as gz.msgs.Image!")
                    print(f"         Width: {msg.width}, Height: {msg.height}")
                except Exception as e:
                    print(f"      ✗ Failed to parse as Image: {e}")
        
        print("-" * 80)
        
    except zmq.Again:
        print(f"\n⏱ Timeout waiting for message {i+1}")
        break
    except KeyboardInterrupt:
        print("\n\n⚠ Stopped by user")
        break

socket.close()
context.term()

print("\n" + "=" * 80)
print("Analysis:")
print("  - If part 0 is text/topic: Standard format [topic, data]")
print("  - If part 0 is binary: May need to skip or parse differently")
print("  - If only 1 part: Message is not multipart")
print("=" * 80)

