#!/bin/bash
# Quick fix to try: Change ZMQ subscription filter to empty
# This is the most common fix for C++ gz-transport compatibility

set -e

echo "================================"
echo "Quick Fix: Empty Subscription Filter"
echo "================================"
echo ""
echo "This changes the ZMQ subscription filter from topic-specific to"
echo "empty (receive all messages), which often fixes C++ gz-transport"
echo "compatibility issues."
echo ""

# Backup original file
NODEFILE="gz_transport/node.py"
BACKUP="gz_transport/node.py.backup.$(date +%s)"

if [ ! -f "$NODEFILE" ]; then
    echo "Error: $NODEFILE not found"
    echo "Are you in the easy-drone-python directory?"
    exit 1
fi

echo "Creating backup: $BACKUP"
cp "$NODEFILE" "$BACKUP"

# Apply the fix
echo "Applying fix..."

# Use sed to change line 321
if grep -q 'socket.setsockopt_string(zmq.SUBSCRIBE, full_topic)' "$NODEFILE"; then
    # Make the change
    sed -i.tmp 's/socket\.setsockopt_string(zmq\.SUBSCRIBE, full_topic)/socket.setsockopt(zmq.SUBSCRIBE, b"")  # Empty filter for C++ compatibility/' "$NODEFILE"
    rm -f "${NODEFILE}.tmp"
    
    echo "✓ Fix applied successfully!"
    echo ""
    echo "Changed:"
    echo "  FROM: socket.setsockopt_string(zmq.SUBSCRIBE, full_topic)"
    echo "  TO:   socket.setsockopt(zmq.SUBSCRIBE, b\"\")  # Empty filter"
    echo ""
    echo "Now test with:"
    echo "  ./examples/gi_bridge_auto.sh \"\$GZ_TOPIC\" --fps 30"
    echo ""
    echo "If this doesn't work, restore with:"
    echo "  cp $BACKUP $NODEFILE"
    echo ""
else
    echo "⚠ Could not find the line to change."
    echo "The file might have already been modified or the line number changed."
    echo ""
    echo "Manual fix:"
    echo "  Edit: $NODEFILE"
    echo "  Find line ~321: socket.setsockopt_string(zmq.SUBSCRIBE, full_topic)"
    echo "  Change to:      socket.setsockopt(zmq.SUBSCRIBE, b\"\")"
fi

