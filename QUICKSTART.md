# Quick Start Guide

Get up and running with gz-transport-py in 5 minutes!

## 1. Install Dependencies

```bash
pip install pyzmq protobuf
```

## 2. Test Installation

### Terminal 1 - Start Subscriber

```bash
cd gz-transport-py
python3 examples/simple_subscriber.py
```

You should see:

```
Note: gz-msgs not found, using dynamic message type
[Discovery] Started (UUID: ...)
[Node] Created (UUID: ...)
Subscribed to topic: /example
Waiting for messages... (Press Ctrl+C to stop)
```

### Terminal 2 - Start Publisher

```bash
cd gz-transport-py
python3 examples/simple_publisher.py
```

You should see:

```
[Discovery] Started (UUID: ...)
[Node] Created (UUID: ...)
[Discovery] Advertised: /example
Publishing on topic: /example
Press Ctrl+C to stop
Published: Hello World 0
Published: Hello World 1
```

### Terminal 1 - Check Subscriber

You should now see messages appearing:

```
[Discovery] New publisher: /example from 12345678
[Node] Connected subscriber to new publisher: /example
Received: Hello World 0
Received: Hello World 1
```

**Success!** 🎉 You now have pub/sub working!

## 3. Explore Examples

### List Topics

In a third terminal while pub/sub are running:

```bash
python3 examples/topic_list.py
```

Output:

```
Discovering topics on the network...
Found 1 topic(s):
  - /example
```

### Namespace Example

This demonstrates topic isolation:

```bash
# Terminal 1
python3 examples/namespace_example.py robot1-pub

# Terminal 2
python3 examples/namespace_example.py robot2-pub

# Terminal 3
python3 examples/namespace_example.py monitor
```

Monitor should show both robots' messages.

## 4. Write Your Own

### Minimal Publisher

```python
from gz_transport_py import Node

# Define a simple message
class MyMsg:
    def __init__(self):
        self.data = ""

    def SerializeToString(self):
        return self.data.encode('utf-8')

    class DESCRIPTOR:
        full_name = "MyMsg"

# Create and use
node = Node()
pub = node.advertise("/my_topic", MyMsg)

msg = MyMsg()
msg.data = "Hello!"
pub.publish(msg)
```

### Minimal Subscriber

```python
from gz_transport_py import Node

class MyMsg:
    def __init__(self):
        self.data = ""

    def ParseFromString(self, data):
        self.data = data.decode('utf-8')

    class DESCRIPTOR:
        full_name = "MyMsg"

def callback(msg):
    print(f"Got: {msg.data}")

node = Node()
node.subscribe(MyMsg, "/my_topic", callback)

import time
while True:
    time.sleep(0.1)
```

## 5. Use with Gazebo Messages

If you have gz-msgs installed:

```python
from gz_transport_py import Node
from gz.msgs.stringmsg_pb2 import StringMsg

# Publisher
node = Node()
pub = node.advertise("/chat", StringMsg)

msg = StringMsg()
msg.data = "Hello from Python!"
pub.publish(msg)
```

This will be compatible with C++ gz-transport nodes!

## 6. Communicate with C++ Nodes

Your Python nodes can talk to C++ gz-transport nodes:

**C++ Publisher:**

```cpp
#include <gz/transport.hh>
#include <gz/msgs.hh>

gz::transport::Node node;
auto pub = node.Advertise<gz::msgs::StringMsg>("/chat");

gz::msgs::StringMsg msg;
msg.set_data("Hello from C++");
pub.Publish(msg);
```

**Python Subscriber:**

```python
from gz_transport_py import Node
from gz.msgs.stringmsg_pb2 import StringMsg

def callback(msg):
    print(f"Received from C++: {msg.data}")

node = Node()
node.subscribe(StringMsg, "/chat", callback)
```

## Troubleshooting

### "No topics found"

- Make sure publisher is running
- Wait 1-2 seconds for discovery
- Check firewall allows UDP port 11317

### "Connection refused"

- Ensure subscriber starts before or at same time as publisher
- Discovery takes ~1 second to propagate

### Import errors

```bash
pip install --upgrade pyzmq protobuf
```

## Next Steps

- Read the full [README.md](README.md)
- Check out [examples/](examples/) directory
- Try integrating with your robot/simulation
- Explore the API in `gz_transport_py/` source

## Performance Tips

- Use raw bytes for high-frequency messages
- Reuse message objects instead of creating new ones
- Consider message throttling for high-rate topics

## Getting Help

- Check the main README.md
- Look at example scripts
- Review gz-transport C++ documentation for concepts
- File an issue if you find bugs

Happy transporting! 🚀
