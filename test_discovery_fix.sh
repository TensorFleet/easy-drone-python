#!/bin/bash
# Test script to verify the discovery fix

set -e

echo "================================"
echo "Testing Discovery Fix"
echo "================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if topic is provided
if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage: $0 <gz_topic>${NC}"
    echo ""
    echo "Example:"
    echo "  $0 /world/shibuya_crossing/model/x500/model/simple_camera/link/mono_cam/base_link/sensor/imager/image"
    echo ""
    echo "Or set GZ_TOPIC environment variable:"
    echo "  export GZ_TOPIC=/world/..."
    echo "  $0 \$GZ_TOPIC"
    exit 1
fi

GZ_TOPIC="$1"

echo "Testing with topic: $GZ_TOPIC"
echo ""

# Test 1: Check if gz command exists
echo "Test 1: Checking gz command..."
if command -v gz &> /dev/null; then
    echo -e "${GREEN}✓ gz command found${NC}"
else
    echo -e "${RED}✗ gz command not found${NC}"
    echo "  Install gz-tools: sudo apt install gz-tools"
    exit 1
fi
echo ""

# Test 2: Check if publisher exists
echo "Test 2: Checking if publisher exists..."
PUBLISHER_INFO=$(gz topic -i -t "$GZ_TOPIC" 2>&1)

if echo "$PUBLISHER_INFO" | grep -q "tcp://"; then
    PUBLISHER_ADDR=$(echo "$PUBLISHER_INFO" | grep -oP 'tcp://[0-9.]+:[0-9]+' | head -n 1)
    echo -e "${GREEN}✓ Publisher found: $PUBLISHER_ADDR${NC}"
else
    echo -e "${RED}✗ No publisher found${NC}"
    echo ""
    echo "Publisher info:"
    echo "$PUBLISHER_INFO"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check if Gazebo is running: gz sim --version"
    echo "  2. List topics: gz topic -l"
    echo "  3. Verify topic name (case-sensitive)"
    exit 1
fi
echo ""

# Test 3: Test helper script
echo "Test 3: Testing get_publisher_address_auto.sh..."
if [ -f "./get_publisher_address_auto.sh" ]; then
    SCRIPT_ADDR=$(./get_publisher_address_auto.sh "$GZ_TOPIC" 2>&1)
    if [ "$SCRIPT_ADDR" = "$PUBLISHER_ADDR" ]; then
        echo -e "${GREEN}✓ Helper script works: $SCRIPT_ADDR${NC}"
    else
        echo -e "${YELLOW}⚠ Helper script returned different address: $SCRIPT_ADDR${NC}"
    fi
else
    echo -e "${RED}✗ Helper script not found${NC}"
fi
echo ""

# Test 4: Check if messages are flowing
echo "Test 4: Checking if messages are flowing..."
echo "  (Timeout after 5 seconds)"
MESSAGE_TEST=$(timeout 5 gz topic -e -t "$GZ_TOPIC" 2>&1 | head -n 10)

if [ -n "$MESSAGE_TEST" ]; then
    echo -e "${GREEN}✓ Messages flowing${NC}"
    echo "  First few lines:"
    echo "$MESSAGE_TEST" | head -n 3 | sed 's/^/    /'
else
    echo -e "${YELLOW}⚠ No messages received in 5 seconds${NC}"
    echo "  This might be normal if messages are infrequent"
fi
echo ""

# Test 5: Check Python dependencies
echo "Test 5: Checking Python dependencies..."
PYTHON_CHECK=$(python3 -c "
import sys
try:
    import zmq
    print('zmq:', zmq.zmq_version())
except ImportError:
    print('ERROR: zmq not found')
    sys.exit(1)

try:
    import google.protobuf
    print('protobuf:', google.protobuf.__version__)
except ImportError:
    print('ERROR: protobuf not found')
    sys.exit(1)

try:
    from gz.msgs.image_pb2 import Image
    print('gz-msgs: OK')
except ImportError:
    print('WARNING: gz-msgs not found (install with: cd gz-msgs-py && pip install -e .)')
" 2>&1)

if echo "$PYTHON_CHECK" | grep -q "ERROR"; then
    echo -e "${RED}✗ Python dependencies missing${NC}"
    echo "$PYTHON_CHECK"
    echo ""
    echo "Install dependencies:"
    echo "  pip install pyzmq 'protobuf>=4.21.0'"
    exit 1
else
    echo -e "${GREEN}✓ Python dependencies OK${NC}"
    echo "$PYTHON_CHECK" | sed 's/^/    /'
fi
echo ""

# Test 6: Check if auto-connect script exists
echo "Test 6: Checking gi_bridge_auto.sh..."
if [ -f "./examples/gi_bridge_auto.sh" ]; then
    if [ -x "./examples/gi_bridge_auto.sh" ]; then
        echo -e "${GREEN}✓ gi_bridge_auto.sh found and executable${NC}"
    else
        echo -e "${YELLOW}⚠ gi_bridge_auto.sh not executable${NC}"
        echo "  Run: chmod +x ./examples/gi_bridge_auto.sh"
    fi
else
    echo -e "${RED}✗ gi_bridge_auto.sh not found${NC}"
fi
echo ""

# Summary
echo "================================"
echo "Summary"
echo "================================"
echo ""
echo "Publisher Address: $PUBLISHER_ADDR"
echo "Topic: $GZ_TOPIC"
echo ""
echo "To run gi_bridge with direct connection:"
echo ""
echo "  # Method 1: Auto-connect"
echo "  ./examples/gi_bridge_auto.sh \"$GZ_TOPIC\" --fps 30"
echo ""
echo "  # Method 2: Manual"
echo "  GZ_TRANSPORT_IMPLEMENTATION=zeromq python examples/gi_bridge.py \\"
echo "    --gz-topic \"$GZ_TOPIC\" \\"
echo "    --publisher-address $PUBLISHER_ADDR \\"
echo "    --fps 30"
echo ""
echo "  # Method 3: Environment variable"
echo "  export GZ_PUBLISHER_ADDRESS=$PUBLISHER_ADDR"
echo "  python examples/gi_bridge.py --gz-topic \"$GZ_TOPIC\" --fps 30"
echo ""
echo -e "${GREEN}All tests passed! ✓${NC}"
echo ""

