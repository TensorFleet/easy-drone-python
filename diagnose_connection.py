#!/usr/bin/env python3
"""
Comprehensive diagnostic for gz-transport connection issues.
Tests various ZMQ socket types and patterns.
"""
import zmq
import sys
import time
import struct

if len(sys.argv) < 2:
    print("Usage: python diagnose_connection.py <publisher_address>")
    print("Example: python diagnose_connection.py tcp://172.17.0.1:45943")
    sys.exit(1)

address = sys.argv[1]
print(f"Diagnosing connection to: {address}")
print()

def test_socket_type(socket_type, type_name, setup_fn=None):
    """Test connecting with a specific socket type."""
    print(f"\n{'='*70}")
    print(f"Testing: {type_name}")
    print('='*70)
    
    context = zmq.Context()
    socket = context.socket(socket_type)
    
    if setup_fn:
        setup_fn(socket)
    
    try:
        socket.connect(address)
        socket.setsockopt(zmq.RCVTIMEO, 2000)
        print(f"✓ Connected successfully")
        
        # Try to receive
        print("  Waiting for data (2s timeout)...")
        try:
            data = socket.recv_multipart()
            print(f"  ✓ Received {len(data)} parts!")
            for i, part in enumerate(data[:3]):  # Show first 3 parts
                print(f"    Part {i}: {len(part)} bytes - {part[:50].hex()}")
            return True
        except zmq.Again:
            print("  ✗ No data received (timeout)")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        socket.close()
        context.term()
        time.sleep(0.3)

# Test 1: SUB with empty filter
def setup_sub_empty(sock):
    sock.setsockopt(zmq.SUBSCRIBE, b"")
    print("  Filter: (empty - receive all)")

# Test 2: SUB with topic filter
def setup_sub_topic(sock):
    sock.setsockopt(zmq.SUBSCRIBE, b"/world")
    print("  Filter: /world")

# Test 3: PULL socket
def setup_pull(sock):
    print("  No special setup")

# Test 4: DEALER socket
def setup_dealer(sock):
    print("  Identity: test-subscriber")
    sock.setsockopt_string(zmq.IDENTITY, "test-subscriber")

print("Running diagnostics...")
print("(This will test different ZMQ socket patterns)\n")

results = []

# Test SUB socket (standard pub/sub)
results.append(("SUB (empty filter)", test_socket_type(zmq.SUB, "SUB socket with empty filter", setup_sub_empty)))
time.sleep(0.5)

results.append(("SUB (topic filter)", test_socket_type(zmq.SUB, "SUB socket with topic filter", setup_sub_topic)))
time.sleep(0.5)

# Test PULL socket (pipeline pattern)
results.append(("PULL", test_socket_type(zmq.PULL, "PULL socket (pipeline pattern)", setup_pull)))
time.sleep(0.5)

# Test DEALER socket (request/reply pattern)
results.append(("DEALER", test_socket_type(zmq.DEALER, "DEALER socket (req/rep pattern)", setup_dealer)))
time.sleep(0.5)

# Summary
print("\n" + "="*70)
print("DIAGNOSTIC SUMMARY")
print("="*70)

for name, success in results:
    status = "✓ SUCCESS" if success else "✗ FAILED  "
    print(f"{status}: {name}")

if any(success for _, success in results):
    print("\n" + "="*70)
    print("WORKING SOCKET TYPE(S) FOUND!")
    print("="*70)
    working = [name for name, success in results if success]
    for name in working:
        print(f"  ✓ {name}")
    
    if results[0][1]:  # SUB with empty filter
        print("\n→ Standard ZMQ PUB/SUB works!")
        print("→ Issue is likely with subscription filter")
        print("→ Try subscribing with empty filter: socket.setsockopt(zmq.SUBSCRIBE, b'')")
else:
    print("\n" + "="*70)
    print("NO WORKING SOCKET TYPE FOUND")
    print("="*70)
    print("\nThis suggests:")
    print("  1. The address might not be a standard ZMQ socket")
    print("  2. A handshake or registration might be required")
    print("  3. The publisher might be using a custom protocol")
    print("  4. The publisher might not be actively sending")
    print("\nNext steps:")
    print("  • Verify messages are being published: gz topic -e -t <topic>")
    print("  • Check gz-transport C++ source for protocol details")
    print("  • Consider using official gz-transport Python bindings if available")

print("\n" + "="*70)
print("Additional Information")
print("="*70)

# Try to get socket information
context = zmq.Context()
test_socket = context.socket(zmq.SUB)
test_socket.setsockopt(zmq.SUBSCRIBE, b"")

try:
    test_socket.connect(address)
    time.sleep(0.5)
    
    # Check socket events
    events = test_socket.get(zmq.EVENTS)
    print(f"Socket events: {events}")
    if events & zmq.POLLIN:
        print("  • POLLIN: Data available to read")
    if events & zmq.POLLOUT:
        print("  • POLLOUT: Socket ready to send")
    
    # Check if connected
    print(f"File descriptor: {test_socket.get(zmq.FD)}")
    
except Exception as e:
    print(f"Could not get socket info: {e}")
finally:
    test_socket.close()
    context.term()

print("\n" + "="*70)
print("Run this on your server to verify the publisher is active:")
print(f"  gz topic -e -t <your_topic_name>")
print("="*70)

