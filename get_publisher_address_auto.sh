#!/bin/bash
# Automatically get publisher address for a Gazebo topic
# Usage: ./get_publisher_address_auto.sh <topic_name>

if [ -z "$1" ]; then
    echo "Usage: $0 <topic_name>"
    echo "Example: $0 /world/default/model/x500/link/camera/sensor/image"
    exit 1
fi

TOPIC="$1"

# Get topic info and extract publisher address
PUBLISHER_ADDRESS=$(gz topic -i -t "$TOPIC" 2>/dev/null | \
    grep -oP 'tcp://[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+' | \
    head -n 1)

if [ -z "$PUBLISHER_ADDRESS" ]; then
    echo "Error: Could not find publisher for topic: $TOPIC" >&2
    echo "Make sure:" >&2
    echo "  1. Gazebo is running" >&2
    echo "  2. The topic exists: gz topic -l" >&2
    echo "  3. The topic has a publisher: gz topic -i -t \"$TOPIC\"" >&2
    exit 1
fi

echo "$PUBLISHER_ADDRESS"

