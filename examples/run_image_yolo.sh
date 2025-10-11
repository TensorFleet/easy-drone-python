#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$(dirname "$SCRIPT_DIR")/venv"
ARTIFACTS_DIR="$SCRIPT_DIR/yolo_artifacts"

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

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Default arguments (can be overridden)
# Default to sample.mp4 for standalone testing
USE_GSTREAMER="${USE_GSTREAMER:-false}"
UDP_PORT="${UDP_PORT:-5600}"
VIDEO_FILE="${VIDEO_FILE:-$ARTIFACTS_DIR/sample.mp4}"
ZENOH_MODE="${ZENOH_MODE:-peer}"
ZENOH_CONNECT="${ZENOH_CONNECT:-}"

echo "=========================================="
echo "Starting YOLO Host Inference"
echo "=========================================="
echo "Model: $ARTIFACTS_DIR/yolov8n.onnx"
echo "Classes: $ARTIFACTS_DIR/coco.json"
if [ "$USE_GSTREAMER" = "true" ]; then
    echo "Input: GStreamer UDP port $UDP_PORT"
else
    echo "Input: Video file: $VIDEO_FILE"
fi
echo "Zenoh mode: $ZENOH_MODE"
[ -n "$ZENOH_CONNECT" ] && echo "Zenoh connect: $ZENOH_CONNECT"
echo ""
echo "Press Ctrl+C to stop."
echo "=========================================="
echo ""

# Build command
CMD="python3 $SCRIPT_DIR/image_yolo.py \
    --model $ARTIFACTS_DIR/yolov8n.onnx \
    --classes $ARTIFACTS_DIR/coco.json \
    --zenoh-mode $ZENOH_MODE \
    --visualize"

if [ "$USE_GSTREAMER" = "true" ]; then
    CMD="$CMD --use-gstreamer --udp-port $UDP_PORT"
else
    CMD="$CMD --video $VIDEO_FILE"
fi

if [ -n "$ZENOH_CONNECT" ]; then
    CMD="$CMD --zenoh-connect $ZENOH_CONNECT"
fi

# Check if PyAV is available (required for UDP streaming)
echo "Checking dependencies..."
if python3 -c "import av" 2>/dev/null; then
    PYAV_VERSION=$(python3 -c "import av; print(av.__version__)" 2>/dev/null || echo "unknown")
    echo "✓ PyAV (av) version: $PYAV_VERSION"
else
    echo "⚠ WARNING: PyAV (av) is not installed!"
    echo "  This is required for UDP streaming (USE_GSTREAMER=true)"
    echo "  Install with: pip install av"
    if [ "$USE_GSTREAMER" = "true" ]; then
        echo ""
        echo "ERROR: Cannot use USE_GSTREAMER=true without PyAV installed"
        deactivate
        exit 1
    fi
fi
echo ""

# Run YOLO
$CMD

deactivate

