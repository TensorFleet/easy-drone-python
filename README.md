# Easy Drone - Pure Python Gazebo Transport

[![Tests](https://github.com/TensorFleet/easy-drone-python/workflows/Tests/badge.svg)](https://github.com/TensorFleet/easy-drone-python/actions)
[![PyPI](https://img.shields.io/pypi/v/easy-drone)](https://pypi.org/project/easy-drone/)
[![Python](https://img.shields.io/pypi/pyversions/easy-drone)](https://pypi.org/project/easy-drone/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

A pure Python implementation of Gazebo Transport (gz-transport) for easy drone communication, providing pub/sub messaging with automatic discovery.

## Features

✅ **Pub/Sub Messaging** - Publish and subscribe to topics
✅ **Automatic Discovery** - UDP multicast (ZeroMQ) or liveliness tokens (Zenoh)
✅ **Multiple Backends** - Choose between ZeroMQ or Zenoh transport
✅ **ZeroMQ Transport** - Fast message delivery using ZeroMQ (default)
✅ **Zenoh Transport** - Alternative backend using Zenoh pub/sub
✅ **Protobuf Messages** - Compatible with Protocol Buffer messages
✅ **No C++ Dependencies** - Pure Python, no need to compile gz-transport
✅ **Network Communication** - Works across processes and machines

## Installation

### Quick Install

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Linux/Mac

# Install the package
cd /path/to/easy-drone-python
pip install -e .
```

This installs `easy-drone` with **integrated gz-msgs** (212+ message types included!).

### Install with Optional Features

```bash
# Install with Zenoh backend support
pip install -e .[zenoh]

# Install with YOLO inference support
pip install -e .[yolo]

# Install with all optional features
pip install -e .[all]

# Install for development
pip install -e .[dev]
```

### Requirements

- Python 3.8+
- `pyzmq>=25.0.0` - ZeroMQ for transport (installed automatically)
- `protobuf>=4.25.0` - Protocol buffers (installed automatically, **must be 4.25.0 or newer**)

### Optional Dependencies

- **Zenoh Backend**: `pip install -e .[zenoh]` - For Zenoh transport support
- **YOLO Inference**: `pip install -e .[yolo]` - For computer vision examples with YOLO
- **Development Tools**: `pip install -e .[dev]` - For testing and development

## Quick Start

### Publisher

```python
from gz_transport import Node
from gz.msgs.stringmsg_pb2 import StringMsg

# Create node
node = Node()

# Advertise topic
pub = node.advertise("/chatter", StringMsg)

# Publish message
msg = StringMsg()
msg.data = "Hello World"
pub.publish(msg)
```

### Subscriber

```python
from gz_transport import Node
from gz.msgs.stringmsg_pb2 import StringMsg

def callback(msg):
    print(f"Received: {msg.data}")

# Create node
node = Node()

# Subscribe to topic
node.subscribe(StringMsg, "/chatter", callback)

# Keep running
import time
while True:
    time.sleep(0.1)
```

## Examples

See the `examples/` directory for complete examples. All examples work with the installed `easy-drone` package.

**ZeroMQ Backend (default):**

- `simple_publisher.py` - Basic publisher
- `simple_subscriber.py` - Basic subscriber
- `topic_list.py` - List all available topics

**Zenoh Backend:**

- `zenoh_publisher.py` - Zenoh-based publisher
- `zenoh_subscriber.py` - Zenoh-based subscriber
- `zenoh_cross_backend.py` - Demonstrates backend isolation

**Computer Vision:**

- `image_yolo.py` - YOLO object detection from Gazebo camera
- `gi_bridge.py` - GStreamer video bridge from Gazebo

### Running Examples

First, install easy-drone:

```bash
pip install -e .
```

Then run examples from anywhere:

Terminal 1 (Subscriber):

```bash
python examples/simple_subscriber.py
```

Terminal 2 (Publisher):

```bash
python examples/simple_publisher.py
```

## API Reference

### Node

Main interface for communication.

```python
from gz_transport import Node, NodeOptions

# Create node
node = Node()

# With options
options = NodeOptions(namespace="robot1", partition="simulation")
node = Node(options)
```

**Methods:**

- `advertise(topic, msg_type, options=None)` - Advertise a topic, returns Publisher
- `subscribe(msg_type, topic, callback, options=None)` - Subscribe to topic
- `unsubscribe(topic)` - Unsubscribe from topic
- `unadvertise(topic)` - Stop advertising topic
- `topic_list()` - Get list of all known topics
- `advertised_topics()` - Get topics advertised by this node
- `subscribed_topics()` - Get topics subscribed by this node
- `shutdown()` - Clean shutdown

### Publisher

Returned by `Node.advertise()`.

```python
pub = node.advertise("/my_topic", MyMsgType)
```

**Methods:**

- `publish(proto_msg)` - Publish a protobuf message
- `publish_raw(msg_bytes, msg_type)` - Publish raw bytes
- `valid()` - Check if publisher is valid

### Options

#### NodeOptions

```python
from gz_transport import NodeOptions

options = NodeOptions(
    namespace="my_namespace",
    partition="my_partition"
)

# Topic remapping
options.add_topic_remap("/old_topic", "/new_topic")
```

#### AdvertiseOptions

```python
from gz_transport import AdvertiseOptions, Scope

options = AdvertiseOptions(
    scope=Scope.ALL  # PROCESS, HOST, or ALL
)
```

#### SubscribeOptions

```python
from gz_transport import SubscribeOptions

options = SubscribeOptions(
    throttled=True,
    msgs_per_sec=10.0
)
```

## Troubleshooting

### Discovery Issues: Not Receiving Messages

**Problem**: Your Python code subscribes but doesn't receive messages, even though `gz topic -e` works.

**Cause**: The Python bridge uses a **custom discovery protocol** that's incompatible with C++ gz-transport. This commonly happens when:

- Gazebo runs in Docker (e.g., publisher at `tcp://172.17.0.1:45943`)
- Cross-network or cross-subnet communication
- Different discovery protocols between Python and C++ implementations

**Solution**: Bypass discovery by providing the publisher address directly.

#### Option 1: Automatic (Recommended - gi_bridge)

Use the auto-connect script for image streaming:

```bash
# Automatically discovers publisher and connects
./examples/gi_bridge_auto.sh /world/default/model/x500/link/camera/sensor/image --fps 30
```

#### Option 2: Manual Connection

1. Get the publisher address:

```bash
gz topic -i -t /your/topic
# Output: tcp://172.17.0.1:45943, gz.msgs.Image
```

2. Run with `--publisher-address`:

```bash
GZ_TRANSPORT_IMPLEMENTATION=zeromq python examples/gi_bridge.py \
  --gz-topic /your/topic \
  --publisher-address tcp://172.17.0.1:45943
```

Or in Python code:

```python
from gz_transport import Node
from gz.msgs.image_pb2 import Image

node = Node(verbose=True)

# Direct connection bypassing discovery
node.subscribe(
    Image,
    "/camera",
    callback,
    publisher_address="tcp://172.17.0.1:45943"
)
```

#### Option 3: Environment Variable

```bash
export GZ_PUBLISHER_ADDRESS=tcp://172.17.0.1:45943
python examples/simple_subscriber.py /your/topic
```

#### Helper Script

Get publisher address for any topic:

```bash
./get_publisher_address_auto.sh /your/topic
# Output: tcp://172.17.0.1:45943
```

## How It Works

### Discovery Protocol

The discovery system uses UDP multicast (default: `239.255.0.7:11317`) to:

1. **Advertise** - Broadcast when a topic is published
2. **Subscribe** - Request discovery of specific topics
3. **Heartbeat** - Send periodic heartbeats (every 1 second)
4. **Cleanup** - Remove stale publishers (after 3 seconds of silence)

### Message Transport

Once discovered, actual messages are sent via ZeroMQ:

- Uses `PUB/SUB` sockets for topic communication
- Publishers bind to random ports
- Subscribers connect to all discovered publishers
- Messages are serialized using Protocol Buffers

### Architecture

```
┌─────────────────────────────────────────┐
│              Node (Your App)             │
├─────────────────────────────────────────┤
│  Publishers          │   Subscribers    │
│  (ZeroMQ PUB)        │   (ZeroMQ SUB)   │
└────────┬─────────────┴─────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │   Discovery Service   │
         │  (UDP Multicast)      │
         └───────────────────────┘
```

## Backend Selection

This library supports two transport backends, matching the C++ implementation:

### ZeroMQ (Default)

```bash
# Use ZeroMQ (default, no env var needed)
export GZ_TRANSPORT_IMPLEMENTATION=zeromq
python3 your_script.py
```

### Zenoh

```bash
# Use Zenoh backend
export GZ_TRANSPORT_IMPLEMENTATION=zenoh
python3 your_script.py
```

**Important:** All communicating nodes must use the same backend. ZeroMQ and Zenoh nodes cannot communicate with each other.

## Comparison with C++ gz-transport

| Feature            | Pure Python | C++ gz-transport |
| ------------------ | ----------- | ---------------- |
| Pub/Sub            | ✅          | ✅               |
| Discovery          | ✅          | ✅               |
| ZeroMQ Backend     | ✅          | ✅               |
| Zenoh Backend      | ✅          | ✅               |
| Services (Req/Rep) | ❌ (TODO)   | ✅               |
| Logging            | ❌ (TODO)   | ✅               |
| Statistics         | ❌ (TODO)   | ✅               |
| Performance        | Good        | Excellent        |
| Dependencies       | Python only | C++, deps        |

## Compatibility

- **Protocol Compatible**: Can communicate with C++ gz-transport nodes
- **Message Format**: Uses same Protobuf serialization
- **Discovery**: Uses compatible (simplified) discovery protocol

## Configuration

Environment variables:

- `GZ_TRANSPORT_IMPLEMENTATION` - Set transport backend: `zeromq` or `zenoh` (default: zeromq)
- `GZ_IP` - Set specific IP address for multicast (ZeroMQ only)
- `GZ_RELAY` - Set relay addresses (not yet implemented)
- `GZ_PARTITION` - Default partition name

## Troubleshooting

### No topics discovered

1. Check firewall allows UDP multicast on port 11317
2. Check if multicast is enabled on your network
3. Try running with `verbose=True`:
   ```python
   node = Node(verbose=True)
   ```

### Messages not received

1. Ensure subscriber is connected before publisher starts
2. Add a small delay after creating nodes to allow discovery
3. Check topic names match exactly

### Import errors

```bash
# Make sure easy-drone is installed
pip install -e .

# If you get import errors, reinstall with:
pip uninstall easy-drone
pip install -e .
```

## Development

### Running Tests

```bash
# Terminal 1
python3 examples/simple_subscriber.py

# Terminal 2
python3 examples/simple_publisher.py

# Terminal 3
python3 examples/topic_list.py
```

### TODO

- [ ] Service request/response implementation
- [ ] Message throttling
- [ ] Topic statistics
- [ ] Logging (record/playback)
- [ ] Better error handling
- [ ] Unit tests
- [ ] Performance optimization

## License

Apache 2.0 (same as gz-transport)

## Credits

Based on the Gazebo Transport protocol specification from:
https://github.com/gazebosim/gz-transport

## Support

For issues or questions:

- Check existing gz-transport documentation
- File issues on GitHub
- Consult the gz-transport community forums
