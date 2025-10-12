# Installation Guide for Easy-Drone

This guide covers the installation of the `easy-drone` Python package.

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Virtual environment (recommended)

## Installation Steps

### 1. Create a Virtual Environment (Recommended)

```bash
# Navigate to the project directory
cd /path/to/easy-drone-python

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
# On Linux/Mac:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

### 2. Install Easy-Drone

#### Basic Installation

Install the base package with ZeroMQ transport support:

```bash
pip install -e .
```

This installs:
- Core `gz_transport_py` module
- Integrated `gz.msgs` protobuf messages (212+ message types)
- ZeroMQ backend (default)
- All required dependencies

#### Installation with Optional Features

**Install with Zenoh backend support:**
```bash
pip install -e .[zenoh]
```

**Install with YOLO computer vision support:**
```bash
pip install -e .[yolo]
```
This adds: opencv-python, numpy, onnxruntime, matplotlib

**Install with all optional features:**
```bash
pip install -e .[all]
```

**Install for development:**
```bash
pip install -e .[dev]
```
This adds: pytest, black, mypy, and other dev tools

### 3. Verify Installation

Test that the package is installed correctly:

```bash
# Test import
python3 -c "from gz_transport_py import Node; print('✓ Easy-Drone installed successfully!')"

# Check installed version
python3 -c "import gz_transport_py; print(f'Version: {gz_transport_py.__version__}')"
```

### 4. Run Examples

After installation, you can run the examples:

```bash
# List available topics
python examples/topic_list.py

# Run a simple subscriber (in one terminal)
python examples/simple_subscriber.py

# Run a simple publisher (in another terminal)
python examples/simple_publisher.py
```

## Installation Options Explained

| Command | Installs | Use Case |
|---------|----------|----------|
| `pip install -e .` | Base package + ZeroMQ | Basic pub/sub communication |
| `pip install -e .[zenoh]` | Base + Zenoh backend | Alternative transport backend |
| `pip install -e .[yolo]` | Base + Computer vision libs | YOLO object detection examples |
| `pip install -e .[all]` | Everything | Full feature set |
| `pip install -e .[dev]` | Base + Dev tools | Development and testing |

## Troubleshooting

### Import Errors

If you encounter import errors:

```bash
# Uninstall and reinstall
pip uninstall easy-drone -y
pip install -e .
```

### Protobuf Version Issues

If you get protobuf-related errors:

```bash
# Ensure protobuf 4.21.0 or newer
pip uninstall protobuf -y
pip install 'protobuf>=4.21.0'
```

### ZeroMQ Issues

If you encounter ZeroMQ errors:

```bash
# Reinstall pyzmq
pip uninstall pyzmq -y
pip install 'pyzmq>=25.0.0'
```

### Virtual Environment Issues

If the virtual environment is causing problems:

```bash
# Remove and recreate
deactivate  # if currently activated
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Uninstallation

To uninstall easy-drone:

```bash
pip uninstall easy-drone
```

## Package Contents

After installation, you'll have access to:

- **gz_transport_py**: Core transport library
  - `Node`: Main communication node
  - `Publisher`: Message publisher
  - `NodeOptions`, `AdvertiseOptions`, `SubscribeOptions`: Configuration
  
- **gz.msgs**: Gazebo message definitions
  - 212+ protobuf message types
  - Full compatibility with C++ gz-transport

## Next Steps

1. Read the [README.md](README.md) for usage examples
2. Explore the `examples/` directory
3. Check the API documentation in the README
4. Join the community for support

## Support

For issues or questions:
- Check the [README.md](README.md) troubleshooting section
- Review example scripts in `examples/`
- File issues on GitHub

Happy drone programming! 🚁

