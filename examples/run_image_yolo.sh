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

# Prefer GStreamer backend for OpenCV and ensure plugins can be found
export OPENCV_VIDEOIO_PRIORITY_GSTREAMER=1
export GST_PLUGIN_SCANNER=${GST_PLUGIN_SCANNER:-/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner}
export GST_PLUGIN_PATH=${GST_PLUGIN_PATH:-/usr/lib/x86_64-linux-gnu/gstreamer-1.0}

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

# Check if we're using system OpenCV (with GStreamer support)
echo "Checking OpenCV configuration..."
if python3 -c "import cv2" 2>/dev/null; then
    HAS_GSTREAMER=$(python3 -c "import cv2; print('YES' if 'GStreamer' in cv2.getBuildInformation() and 'YES' in cv2.getBuildInformation().split('GStreamer')[1].split('\n')[0] else 'NO')" 2>/dev/null || echo "UNKNOWN")
    if [ "$HAS_GSTREAMER" = "YES" ]; then
        echo "✓ OpenCV has GStreamer support"
    elif [ "$USE_GSTREAMER" = "true" ]; then
        echo "⚠ WARNING: OpenCV does not have GStreamer support!"
        echo "  This may cause connection failures when using USE_GSTREAMER=true"
        echo "  Ensure python3-opencv system package is installed"
    fi
fi
echo ""

# Run YOLO
$CMD

deactivate

