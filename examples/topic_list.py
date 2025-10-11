#!/usr/bin/env python3
"""
List all available topics on the network.
"""

import time
import sys
sys.path.insert(0, '..')

from gz_transport_py import Node


def main():
    print("Discovering topics on the network...")
    
    # Create node
    node = Node(verbose=False)
    
    # Wait for discovery
    time.sleep(2)
    
    # Get topic list
    topics = node.topic_list()
    
    if topics:
        print(f"\nFound {len(topics)} topic(s):")
        for topic in sorted(topics):
            print(f"  - {topic}")
    else:
        print("\nNo topics found")
    
    # Cleanup
    node.shutdown()


if __name__ == "__main__":
    main()

