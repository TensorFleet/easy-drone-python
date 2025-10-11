#!/bin/bash
# Helper script to get publisher address from remote Gazebo server
# Usage: ./get_publisher_address.sh <remote_host> <topic>

if [ $# -lt 2 ]; then
    echo "Usage: $0 <remote_host> <topic>"
    echo ""
    echo "Example:"
    echo "  $0 10.197.1.132 /world/shibuya_crossing/model/x500/model/simple_camera/link/mono_cam/base_link/sensor/imager/image"
    echo ""
    echo "This will SSH into the remote host and get the publisher address."
    exit 1
fi

REMOTE_HOST="$1"
TOPIC="$2"

echo "Querying remote Gazebo at $REMOTE_HOST for topic: $TOPIC"
echo "================================================================"

# SSH into remote and run gz topic -i
ssh "$REMOTE_HOST" "gz topic -i -t '$TOPIC'" | grep -A 10 "Publishers" | grep "tcp://" | head -1 | awk '{print $1}' | tr -d ','

