# Architecture Overview

This document explains the internal architecture of gz-transport-py.

## System Components

```
┌─────────────────────────────────────────────────────────────┐
│                        Application Layer                     │
│  (Your code using Node.advertise() / Node.subscribe())      │
└──────────────────┬──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│                     Node (node.py)                           │
│  - Manages publishers and subscribers                        │
│  - Applies namespaces and topic remapping                   │
│  - Coordinates between discovery and transport               │
└──────┬─────────────────────────────────────────────┬────────┘
       │                                             │
       │ Discovery                                   │ Data Transport
       │                                             │
┌──────▼────────────────────┐              ┌────────▼─────────┐
│  Discovery (discovery.py) │              │  Publisher       │
│  - UDP multicast          │              │  Subscriber      │
│  - Topic advertisement    │              │  (ZeroMQ)        │
│  - Heartbeat/timeout      │              │                  │
└───────────────────────────┘              └──────────────────┘
```

## Discovery Protocol

### Message Types

1. **ADVERTISE** - Announce a new publisher
2. **UNADVERTISE** - Remove a publisher
3. **SUBSCRIBE** - Request discovery of a topic
4. **HEARTBEAT** - Keep-alive message
5. **BYE** - Node is shutting down

### Message Flow

```
Publisher Node                  Network                 Subscriber Node
      │                            │                            │
      │ ADVERTISE(/topic)          │                            │
      ├───────────────────────────>│                            │
      │                            │ ADVERTISE(/topic)          │
      │                            ├───────────────────────────>│
      │                            │                            │ Store publisher info
      │                            │                            │ Connect ZeroMQ socket
      │                            │                            │
      │                            │          SUBSCRIBE(/topic) │
      │                            │<───────────────────────────┤
      │ ADVERTISE(/topic) [reply]  │                            │
      │<───────────────────────────┤                            │
      │                            │ ADVERTISE(/topic)          │
      │                            ├───────────────────────────>│
      │                            │                            │
      │ HEARTBEAT (every 1s)       │                            │
      ├───────────────────────────>│                            │
      │                            │                            │
```

### Discovery Message Format

Messages are JSON-encoded:

```json
{
  "type": "advertise",
  "process_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "topic": "/example",
    "msg_type": "gz.msgs.StringMsg",
    "address": "tcp://192.168.1.100:5555",
    "process_uuid": "550e8400-e29b-41d4-a716-446655440000",
    "node_uuid": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "scope": "all"
  }
}
```

### Timeout Mechanism

```
Time:  0s        1s        2s        3s        4s
       │         │         │         │         │
Pub: ──┼─HB─────┼─HB─────┼─HB─────┼─────────┼─────
       │         │         │         │         │
Sub: ──┼─────────┼─────────┼─────────┼──TIMEOUT─┤ Remove publisher
       │         │         │         │         │
       │<──────────3s silence ─────────>│
```

## Data Transport (ZeroMQ)

### Socket Types

- **PUB (Publisher)** - Binds to random port, broadcasts messages
- **SUB (Subscriber)** - Connects to publisher addresses, receives messages

### Message Format

Messages are sent as multipart ZeroMQ messages:

```
┌────────────────┐
│ Part 0: Topic  │  UTF-8 encoded string
├────────────────┤
│ Part 1: Data   │  Serialized protobuf bytes
└────────────────┘
```

Example:

```python
socket.send_multipart([
    b"/example",           # Topic name
    msg.SerializeToString() # Protobuf bytes
])
```

### Connection Flow

```
1. Publisher advertises → Discovery broadcasts
2. Subscriber receives discovery message
3. Subscriber extracts ZeroMQ address
4. Subscriber connects to address
5. Data flows over ZeroMQ connection

Publisher                     Subscriber
    │                             │
    │ bind(tcp://*:5555)          │
    │                             │
    │  ─── discovery msg ───>     │
    │  (contains: tcp://...:5555) │
    │                             │
    │                             │ connect(tcp://...:5555)
    │                             │
    │<══════ ZeroMQ PUB/SUB ═════>│
    │                             │
    │  ──── message data ────>    │
    │                             │
```

## Threading Model

### Discovery Thread

```python
# Started by Discovery.start()
def _recv_loop():
    while running:
        data = socket.recvfrom(65535)  # UDP receive
        handle_message(data)            # Process message
        check_timeouts()                # Remove stale publishers
```

### Heartbeat Thread

```python
# Started by Discovery.start()
def _heartbeat_loop():
    while running:
        time.sleep(HEARTBEAT_INTERVAL)
        send_heartbeat()
        re_advertise_topics()
```

### Subscriber Threads

```python
# One thread per subscriber
def _recv_loop():
    while running:
        parts = socket.recv_multipart()  # ZeroMQ receive
        msg = deserialize(parts[1])
        callback(msg)                     # User callback
```

## State Management

### Node State

```python
{
    'publishers': {
        '/topic1': Publisher(...),
        '/topic2': Publisher(...)
    },
    'subscribers': {
        '/topic1': Subscriber(...),
        '/topic3': Subscriber(...)
    },
    'publisher_sockets': {
        '/topic1': zmq.Socket(...),
        '/topic2': zmq.Socket(...)
    }
}
```

### Discovery State

```python
{
    'publishers': {
        '/topic1': [
            PublisherInfo(address='tcp://...', uuid='...'),
            PublisherInfo(address='tcp://...', uuid='...')
        ]
    },
    'last_heartbeat': {
        'process-uuid-1': timestamp,
        'process-uuid-2': timestamp
    },
    'local_publishers': [
        PublisherInfo(...)
    ]
}
```

## Synchronization

### Thread Safety

All shared state is protected by locks:

```python
class Discovery:
    def __init__(self):
        self.lock = threading.RLock()

    def advertise(self, pub_info):
        with self.lock:
            self.local_publishers.append(pub_info)
        # ... send message
```

### Race Conditions Handled

1. **Discovery vs Data**: Discovery happens first, connections established before data flows
2. **Multiple Subscribers**: Each gets its own socket and thread
3. **Cleanup**: Proper shutdown order (stop threads → close sockets → cleanup state)

## Scope and Namespaces

### Topic Name Resolution

```python
User provides:     "/status"
Namespace:         "robot1"
Partition:         "sim"
Result:            "@sim@/robot1/status"
```

### Scope Filtering

```python
if publisher.scope == Scope.PROCESS:
    # Only same process can see it
    if publisher.process_uuid != self.process_uuid:
        return  # Ignore

elif publisher.scope == Scope.HOST:
    # Only same machine
    if not is_local_address(publisher.address):
        return  # Ignore
```

## Performance Considerations

### Optimizations

1. **UDP Multicast** - Efficient broadcast to all nodes
2. **ZeroMQ** - High-performance message queue
3. **Protobuf** - Compact binary serialization
4. **Thread per Subscriber** - Parallel message processing

### Bottlenecks

1. **Discovery Latency** - ~1 second to discover new publishers
2. **Python GIL** - Limits CPU-bound processing in callbacks
3. **JSON Discovery** - Not as efficient as binary (could use protobuf)

## Error Handling

### Discovery Errors

- Invalid messages → Silently ignored
- Socket errors → Logged if verbose=True
- Timeouts → Automatic cleanup of stale publishers

### Transport Errors

- Publish failure → Returns False
- Subscribe error → Logged, thread continues
- Connection failure → Retried automatically by ZeroMQ

## Comparison with C++ Implementation

### Similarities

- Same discovery protocol concept
- Same ZeroMQ transport
- Same topic naming conventions
- Compatible protobuf messages

### Differences

| Aspect                | Python          | C++            |
| --------------------- | --------------- | -------------- |
| Discovery encoding    | JSON            | Protobuf       |
| Wire protocol version | Simplified      | Full (v10)     |
| Performance           | ~10-100k msg/s  | ~100k-1M msg/s |
| Memory usage          | Higher          | Lower          |
| Services              | Not implemented | Full support   |
| Statistics            | Not implemented | Full support   |

## Future Improvements

1. **Binary Discovery** - Use protobuf instead of JSON
2. **Service Support** - Implement REQ/REP pattern
3. **Message Pooling** - Reuse message objects
4. **C Extension** - Critical paths in C for performance
5. **Async API** - asyncio support
6. **Statistics** - Topic bandwidth monitoring
