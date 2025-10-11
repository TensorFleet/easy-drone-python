#!/bin/bash
# Auto-connect YOLO Inference from Gazebo Image Topic
# Automatically discovers the publisher address and connects to it
# Usage: ./run_image_yolo.sh <gz_topic> [additional_args...]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/venv"
ARTIFACTS_DIR="$SCRIPT_DIR/yolo_artifacts"

# Check if topic is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <gz_topic> [additional_args...]"
    echo "Example: $0 /world/default/model/x500/link/camera/sensor/image --visualize"
    echo ""
    echo "Optional environment variables:"
    echo "  ZENOH_MODE=peer|client (default: peer)"
    echo "  ZENOH_CONNECT=tcp://host:port (default: none)"
    exit 1
fi

GZ_TOPIC="$1"
shift  # Remove first argument, keep the rest

# Check if setup has been run
if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Virtual environment not found at $VENV_DIR"
    echo "Please run setup first:"
    echo "  ./scripts/yolo_setup.sh"
    exit 1
fi

if [ ! -f "$ARTIFACTS_DIR/yolov8n.onnx" ] || [ ! -f "$ARTIFACTS_DIR/coco.json" ]; then
    echo "ERROR: YOLO artifacts not found in $ARTIFACTS_DIR"
    echo "Please run setup first:"
    echo "  ./scripts/yolo_setup.sh"
    exit 1
fi

echo "[run_image_yolo] Discovering publisher for: $GZ_TOPIC"

# Get publisher address
PUBLISHER_ADDRESS=$(gz topic -i -t "$GZ_TOPIC" 2>/dev/null | \
    grep -oP 'tcp://[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+' | \
    head -n 1)

if [ -z "$PUBLISHER_ADDRESS" ]; then
    echo "[run_image_yolo] ERROR: Could not find publisher for topic: $GZ_TOPIC" >&2
    echo "[run_image_yolo] Troubleshooting:" >&2
    echo "  1. Check if Gazebo is running" >&2
    echo "  2. List available topics: gz topic -l" >&2
    echo "  3. Verify topic has publisher: gz topic -i -t \"$GZ_TOPIC\"" >&2
    exit 1
fi

echo "[run_image_yolo] Found publisher: $PUBLISHER_ADDRESS"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Environment variables (can be overridden)
ZENOH_MODE="${ZENOH_MODE:-peer}"
ZENOH_CONNECT="${ZENOH_CONNECT:-}"

echo "=========================================="
echo "Starting YOLO Inference from Gazebo"
echo "=========================================="
echo "Gazebo topic: $GZ_TOPIC"
echo "Publisher: $PUBLISHER_ADDRESS"
echo "Model: $ARTIFACTS_DIR/yolov8n.onnx"
echo "Classes: $ARTIFACTS_DIR/coco.json"
echo "Zenoh mode: $ZENOH_MODE"
[ -n "$ZENOH_CONNECT" ] && echo "Zenoh connect: $ZENOH_CONNECT"
echo ""
echo "Press Ctrl+C to stop."
echo "=========================================="
echo ""

# Build command
CMD="GZ_TRANSPORT_IMPLEMENTATION=zeromq python3 $SCRIPT_DIR/image_yolo.py \
    --gz-topic \"$GZ_TOPIC\" \
    --publisher-address \"$PUBLISHER_ADDRESS\" \
    --model $ARTIFACTS_DIR/yolov8n.onnx \
    --classes $ARTIFACTS_DIR/coco.json \
    --zenoh-mode $ZENOH_MODE"

if [ -n "$ZENOH_CONNECT" ]; then
    CMD="$CMD --zenoh-connect $ZENOH_CONNECT"
fi

# Add any additional arguments passed to script
if [ $# -gt 0 ]; then
    CMD="$CMD $@"
fi

# Check dependencies
echo "Checking dependencies..."
if python3 -c "import gz_transport_py" 2>/dev/null; then
    echo "✓ gz-transport-py installed"
else
    echo "✗ ERROR: gz-transport-py not installed!"
    echo "  Install with: cd $PROJECT_DIR && pip install -e ."
    deactivate
    exit 1
fi

if python3 -c "from gz.msgs import image_pb2" 2>/dev/null; then
    echo "✓ gz-msgs-py installed"
else
    echo "✗ ERROR: gz-msgs-py not installed!"
    echo "  Install with: cd $(dirname $PROJECT_DIR)/gz-msgs-py && pip install -e ."
    deactivate
    exit 1
fi
echo ""

# Run YOLO
eval $CMD

deactivate

