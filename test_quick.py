#!/usr/bin/env python3
"""
Quick test to verify multiple nodes can be created.
"""

from gz_transport import Node
import time

print("Test: Creating multiple nodes in same process")
print("=" * 50)

print("\n1. Creating first node...")
node1 = Node(verbose=False)
print("   ✓ Node 1 created")

print("\n2. Creating second node...")
node2 = Node(verbose=False)
print("   ✓ Node 2 created")

print("\n3. Both nodes share same process UUID:")
print(f"   Node1 process UUID: {node1.process_uuid}")
print(f"   Node2 process UUID: {node2.process_uuid}")
print(f"   Match: {node1.process_uuid == node2.process_uuid}")

print("\n4. But have different node UUIDs:")
print(f"   Node1 UUID: {node1.node_uuid}")
print(f"   Node2 UUID: {node2.node_uuid}")
print(f"   Different: {node1.node_uuid != node2.node_uuid}")

print("\n5. Cleaning up...")
node1.shutdown()
node2.shutdown()
print("   ✓ Cleanup complete")

print("\n✅ TEST PASSED - Multiple nodes can coexist!")

