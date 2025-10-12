#!/usr/bin/env python3
"""
Verification script for easy-drone installation.

This script checks if easy-drone is installed correctly and all components are accessible.
"""

import sys


def check_import(module_name, display_name=None):
    """Try to import a module and report status."""
    if display_name is None:
        display_name = module_name

    try:
        __import__(module_name)
        print(f"✓ {display_name}")
        return True
    except ImportError as e:
        print(f"✗ {display_name} - {str(e)}")
        return False


def main():
    """Run verification checks."""
    print("=" * 60)
    print("Easy-Drone Installation Verification")
    print("=" * 60)
    print()

    print("Checking core components:")
    core_ok = True
    core_ok &= check_import("gz_transport", "gz_transport (core)")
    core_ok &= check_import("gz_transport.node", "gz_transport.node")
    core_ok &= check_import("gz_transport.publisher",
                            "gz_transport.publisher")
    core_ok &= check_import("gz_transport.options",
                            "gz_transport.options")

    print()
    print("Checking gz.msgs:")
    msgs_ok = True
    msgs_ok &= check_import("gz.msgs.stringmsg_pb2", "gz.msgs.stringmsg_pb2")
    msgs_ok &= check_import("gz.msgs.image_pb2", "gz.msgs.image_pb2")
    msgs_ok &= check_import("gz.msgs.vector3d_pb2", "gz.msgs.vector3d_pb2")

    print()
    print("Checking required dependencies:")
    deps_ok = True
    deps_ok &= check_import("zmq", "pyzmq")
    deps_ok &= check_import("google.protobuf", "protobuf")

    print()
    print("Checking optional dependencies:")
    check_import("zenoh", "zenoh (optional - for Zenoh backend)")
    check_import("cv2", "opencv-python (optional - for YOLO)")
    check_import("numpy", "numpy (optional - for YOLO)")
    check_import("onnxruntime", "onnxruntime (optional - for YOLO)")

    print()
    print("=" * 60)

    if core_ok and msgs_ok and deps_ok:
        print("✓ Easy-Drone is installed correctly!")
        print()
        print("You can now run examples:")
        print("  python examples/simple_publisher.py")
        print("  python examples/simple_subscriber.py")
        return 0
    else:
        print("✗ Installation incomplete or has issues.")
        print()
        print("Try reinstalling:")
        print("  pip install -e .")
        return 1


if __name__ == "__main__":
    sys.exit(main())
