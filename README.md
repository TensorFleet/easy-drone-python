# Pure Python Gazebo Transport

A pure Python implementation of Gazebo Transport (gz-transport) providing pub/sub messaging with automatic discovery.

## Features

✅ **Pub/Sub Messaging** - Publish and subscribe to topics
✅ **Automatic Discovery** - UDP multicast discovery of publishers/subscribers  
✅ **ZeroMQ Transport** - Fast message delivery using ZeroMQ
✅ **Protobuf Messages** - Compatible with Protocol Buffer messages
✅ **No C++ Dependencies** - Pure Python, no need to compile gz-transport
✅ **Network Communication** - Works across processes and machines

## Installation

### Requirements

```bash
pip install pyzmq protobuf
```

### Optional: Gazebo Messages

For full compatibility with gz-transport C++ version:

```bash
# Install gz-msgs Python bindings (if available)
pip install gz-msgs
```

## Quick Start

### Publisher

```python
from gz_transport_py import Node
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
from gz_transport_py import Node
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

See the `examples/` directory for complete examples:

- `simple_publisher.py` - Basic publisher
- `simple_subscriber.py` - Basic subscriber
- `topic_list.py` - List all available topics

### Running Examples

Terminal 1 (Subscriber):

```bash
cd examples
python3 simple_subscriber.py
```

Terminal 2 (Publisher):

```bash
cd examples
python3 simple_publisher.py
```

## API Reference

### Node

Main interface for communication.

```python
from gz_transport_py import Node, NodeOptions

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
from gz_transport_py import NodeOptions

options = NodeOptions(
    namespace="my_namespace",
    partition="my_partition"
)

# Topic remapping
options.add_topic_remap("/old_topic", "/new_topic")
```

#### AdvertiseOptions

```python
from gz_transport_py import AdvertiseOptions, Scope

options = AdvertiseOptions(
    scope=Scope.ALL  # PROCESS, HOST, or ALL
)
```

#### SubscribeOptions

```python
from gz_transport_py import SubscribeOptions

options = SubscribeOptions(
    throttled=True,
    msgs_per_sec=10.0
)
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

## Comparison with C++ gz-transport

| Feature            | Pure Python | C++ gz-transport |
| ------------------ | ----------- | ---------------- |
| Pub/Sub            | ✅          | ✅               |
| Discovery          | ✅          | ✅               |
| Services (Req/Rep) | ❌ (TODO)   | ✅               |
| Logging            | ❌ (TODO)   | ✅               |
| Statistics         | ❌ (TODO)   | ✅               |
| Zenoh Support      | ❌          | ✅               |
| Performance        | Good        | Excellent        |
| Dependencies       | Python only | C++, deps        |

## Compatibility

- **Protocol Compatible**: Can communicate with C++ gz-transport nodes
- **Message Format**: Uses same Protobuf serialization
- **Discovery**: Uses compatible (simplified) discovery protocol

## Configuration

Environment variables:

- `GZ_IP` - Set specific IP address for multicast
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
# Install dependencies
pip install pyzmq protobuf

# For gz-msgs compatibility
pip install gz-msgs  # if available
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
