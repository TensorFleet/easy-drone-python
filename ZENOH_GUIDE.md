# Zenoh Backend Guide

This guide explains how to use the Zenoh backend in gz-transport-py, which provides an alternative to the default ZeroMQ backend.

## What is Zenoh?

Zenoh is a modern pub/sub/query protocol designed for IoT, Edge Computing, and Cloud. It provides:

- Built-in discovery via liveliness tokens
- Efficient wire protocol
- Native support for queries (future use for services)
- Better scalability for large deployments
- Cloud-native architecture

## Installation

To use the Zenoh backend, you need to install the zenoh Python package:

```bash
pip install eclipse-zenoh
```

Or install all requirements including Zenoh:

```bash
pip install -r requirements.txt
```

## Usage

### Selecting the Backend

Set the `GZ_TRANSPORT_IMPLEMENTATION` environment variable before running your Python script:

```bash
# Use Zenoh backend
export GZ_TRANSPORT_IMPLEMENTATION=zenoh
python3 your_script.py
```

Or set it programmatically in your script (before importing gz_transport):

```python
import os
os.environ['GZ_TRANSPORT_IMPLEMENTATION'] = 'zenoh'

from gz_transport import Node
```

### Code Examples

The API is exactly the same regardless of backend. Here's a simple example:

#### Publisher (zenoh_publisher.py)

```python
import os
os.environ['GZ_TRANSPORT_IMPLEMENTATION'] = 'zenoh'

from gz_transport import Node
from gz.msgs.stringmsg_pb2 import StringMsg
import time

node = Node(verbose=True)
pub = node.advertise("/chatter", StringMsg)

while True:
    msg = StringMsg()
    msg.data = "Hello from Zenoh!"
    pub.publish(msg)
    time.sleep(1)
```

#### Subscriber (zenoh_subscriber.py)

```python
import os
os.environ['GZ_TRANSPORT_IMPLEMENTATION'] = 'zenoh'

from gz_transport import Node
from gz.msgs.stringmsg_pb2 import StringMsg
import time

def callback(msg):
    print(f"Received: {msg.data}")

node = Node(verbose=True)
node.subscribe(StringMsg, "/chatter", callback)

# Keep running
while True:
    time.sleep(0.1)
```

## How It Works

### Discovery Mechanism

Unlike ZeroMQ which uses UDP multicast for discovery, Zenoh uses **liveliness tokens**:

1. **Publisher:** When a topic is advertised, a liveliness token is created:

   - Format: `{topic}/{process_uuid}/{node_uuid}/MS/{msg_type}`
   - Example: `/chatter/550e8400-e29b.../6ba7b810-9dad.../MS/gz.msgs.StringMsg`

2. **Subscriber:** Zenoh automatically discovers publishers through these tokens

   - No manual discovery protocol needed
   - Built into Zenoh's infrastructure

3. **Message Type Attachment:** The message type is sent as an attachment with each message, allowing type checking on the subscriber side

### Message Flow

```
Publisher                             Zenoh                          Subscriber
    │                                  │                                 │
    │ 1. Declare Publisher             │                                 │
    ├─────────────────────────────────>│                                 │
    │                                  │                                 │
    │ 2. Create Liveliness Token       │                                 │
    │    (/topic/.../MS/type)          │                                 │
    ├─────────────────────────────────>│                                 │
    │                                  │                                 │
    │                                  │  3. Declare Subscriber          │
    │                                  │<────────────────────────────────┤
    │                                  │                                 │
    │                                  │  4. Discover via Liveliness     │
    │                                  │────────────────────────────────>│
    │                                  │                                 │
    │ 5. Publish (payload + attachment)│                                 │
    ├─────────────────────────────────>│                                 │
    │                                  │  6. Deliver Message             │
    │                                  │────────────────────────────────>│
    │                                  │                                 │
```

## Comparison: ZeroMQ vs Zenoh

| Feature          | ZeroMQ Backend     | Zenoh Backend         |
| ---------------- | ------------------ | --------------------- |
| Discovery        | UDP Multicast      | Liveliness Tokens     |
| Protocol         | TCP (ZMQ PUB/SUB)  | Zenoh Wire Protocol   |
| Configuration    | Multicast setup    | Default config works  |
| Firewall         | May need UDP:11317 | Typically easier      |
| Cloud/Container  | May need config    | Works out of the box  |
| Performance      | Excellent (local)  | Excellent (any scale) |
| Network Topology | Requires multicast | More flexible         |

## Benefits of Zenoh

1. **No Multicast Required:** Works in environments where UDP multicast is blocked
2. **Cloud-Native:** Better suited for cloud deployments and containers
3. **Scalability:** Designed for large-scale distributed systems
4. **Built-in Discovery:** No custom discovery protocol needed
5. **Future-Proof:** Native query support for future service implementation

## Limitations

### Backend Isolation

**Important:** ZeroMQ and Zenoh backends cannot communicate with each other!

```python
# ❌ This won't work:
# Publisher using Zenoh + Subscriber using ZeroMQ = No communication

# ✅ This works:
# Publisher using Zenoh + Subscriber using Zenoh = Communication works
```

All nodes in your system must use the same backend.

### Not Yet Implemented

- **Services (REQ/REP):** Coming soon using Zenoh queryables
- **Statistics:** Not yet implemented in either backend

## Migration from ZeroMQ to Zenoh

Migration is straightforward:

1. **Install Zenoh:**

   ```bash
   pip install eclipse-zenoh
   ```

2. **Update all nodes:** Set environment variable for ALL nodes:

   ```bash
   export GZ_TRANSPORT_IMPLEMENTATION=zenoh
   ```

3. **No code changes needed:** The API is identical

4. **Restart all nodes:** Ensure all nodes are using the same backend

## Troubleshooting

### Zenoh Not Available

```
[Node] Warning: Zenoh implementation requested but zenoh module not available
[Node] Falling back to zeromq. Install zenoh with: pip install eclipse-zenoh
```

**Solution:** Install zenoh:

```bash
pip install eclipse-zenoh
```

### Messages Not Being Received

**Cause:** Mixed backends (some nodes using ZeroMQ, others using Zenoh)

**Solution:** Ensure all nodes have the same `GZ_TRANSPORT_IMPLEMENTATION`:

```bash
# On all terminals/nodes:
export GZ_TRANSPORT_IMPLEMENTATION=zenoh
```

### Verify Backend in Use

Enable verbose mode to see which backend is active:

```python
node = Node(verbose=True)
# Output will show: [Node] Created (UUID: ..., Implementation: zenoh)
```

## Advanced Configuration

### Zenoh Configuration File

You can provide custom Zenoh configuration (advanced):

```python
# Future enhancement - not yet implemented
# This shows the potential API
```

For now, Zenoh uses default configuration which should work for most use cases.

## Examples

See the `examples/` directory:

- `zenoh_publisher.py` - Basic Zenoh publisher
- `zenoh_subscriber.py` - Basic Zenoh subscriber
- `zenoh_cross_backend.py` - Demonstrates backend isolation

Run them:

```bash
# Terminal 1
export GZ_TRANSPORT_IMPLEMENTATION=zenoh
python3 examples/zenoh_subscriber.py

# Terminal 2
export GZ_TRANSPORT_IMPLEMENTATION=zenoh
python3 examples/zenoh_publisher.py
```

## Compatibility with C++ gz-transport

The Python Zenoh implementation is designed to match the C++ gz-transport Zenoh backend:

- Same liveliness token format
- Same message type attachment mechanism
- Compatible discovery via Zenoh

**Note:** For actual interoperability, both C++ and Python implementations must:

1. Use Zenoh backend
2. Use same Protobuf message definitions
3. Be on the same network/Zenoh infrastructure

## Future Enhancements

Planned improvements for the Zenoh backend:

- [ ] Service support using Zenoh queryables
- [ ] Custom Zenoh configuration support
- [ ] Advanced routing configuration
- [ ] Performance tuning options
- [ ] Better error reporting

## Resources

- [Zenoh Official Site](https://zenoh.io/)
- [Zenoh Python Documentation](https://zenoh.io/docs/apis/python/)
- [gz-transport C++ Zenoh Implementation](https://github.com/gazebosim/gz-transport)

## Summary

The Zenoh backend provides a modern, cloud-native alternative to ZeroMQ:

✅ **When to use Zenoh:**

- Cloud/container deployments
- Networks without multicast support
- Large-scale distributed systems
- Future-proofing for service support

✅ **When to use ZeroMQ:**

- Local development
- Traditional network setups with multicast
- Existing ZeroMQ-based systems
- Maximum compatibility with older systems

Both backends provide the same API and feature set, making it easy to switch between them.
