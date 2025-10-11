#!/bin/bash
# Auto-connect Gazebo Image Bridge
# Automatically discovers the publisher address and connects to it
# Usage: ./gi_bridge_auto.sh <topic_name> [additional_args...]

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Check if topic is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <gz_topic> [additional_args...]"
    echo "Example: $0 /world/default/model/x500/link/camera/sensor/image --fps 30"
    exit 1
fi

GZ_TOPIC="$1"
shift  # Remove first argument, keep the rest

echo "[gi_bridge_auto] Discovering publisher for: $GZ_TOPIC"

# Get publisher address
PUBLISHER_ADDRESS=$(gz topic -i -t "$GZ_TOPIC" 2>/dev/null | \
    grep -oP 'tcp://[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+' | \
    head -n 1)

if [ -z "$PUBLISHER_ADDRESS" ]; then
    echo "[gi_bridge_auto] ERROR: Could not find publisher for topic: $GZ_TOPIC" >&2
    echo "[gi_bridge_auto] Troubleshooting:" >&2
    echo "  1. Check if Gazebo is running" >&2
    echo "  2. List available topics: gz topic -l" >&2
    echo "  3. Verify topic has publisher: gz topic -i -t \"$GZ_TOPIC\"" >&2
    exit 1
fi

echo "[gi_bridge_auto] Found publisher: $PUBLISHER_ADDRESS"

# Activate venv if it exists
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Run the bridge with direct connection
echo "[gi_bridge_auto] Starting bridge..."
GZ_TRANSPORT_IMPLEMENTATION=zeromq python "$SCRIPT_DIR/gi_bridge.py" \
    --gz-topic "$GZ_TOPIC" \
    --publisher-address "$PUBLISHER_ADDRESS" \
    "$@"

