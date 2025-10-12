# Easy-Drone Quick Start Guide

## Installation (One Command!)

```bash
cd /path/to/easy-drone-python
pip install -e .
```

That's it! You're ready to go! 🚁

## Verify Installation

```bash
python verify_install.py
```

## Run Your First Example

### Terminal 1 - Start Subscriber
```bash
python examples/simple_subscriber.py
```

### Terminal 2 - Start Publisher
```bash
python examples/simple_publisher.py
```

You should see messages flowing!

## What Changed?

### Before (Old Way)
```bash
cd examples
python simple_publisher.py  # Required sys.path hack inside file
```

### After (New Way)
```bash
pip install -e .           # Install once
python examples/simple_publisher.py  # Run from anywhere!
```

## Your Code Doesn't Need Changes!

Your existing code works exactly the same:
```python
from gz_transport_py import Node
from gz.msgs.stringmsg_pb2 import StringMsg

node = Node()
pub = node.advertise("/topic", StringMsg)
# ... everything works the same!
```

## Optional Features

```bash
# Zenoh backend support
pip install -e .[zenoh]

# YOLO computer vision
pip install -e .[yolo]

# Everything
pip install -e .[all]
```

## More Examples

```bash
# List topics
python examples/topic_list.py

# Zenoh publisher/subscriber
python examples/zenoh_publisher.py
python examples/zenoh_subscriber.py

# Namespace example
python examples/namespace_example.py robot1-pub
```

## Help & Documentation

- **Installation**: See [INSTALL.md](INSTALL.md)
- **Full Documentation**: See [README.md](README.md)
- **Migration Info**: See [MIGRATION.md](MIGRATION.md)
- **Summary**: See [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)

## Troubleshooting

### Import errors?
```bash
pip install -e .
```

### Protobuf errors?
```bash
pip install --upgrade 'protobuf>=4.25.0'
```

### Still having issues?
```bash
python verify_install.py
```

Happy flying! 🚁✨

