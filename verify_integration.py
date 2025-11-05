#!/usr/bin/env python3
"""
Verification script for gz-transport with integrated gz-msgs.

This script verifies that both packages are properly integrated and working.
"""

import sys


def test_imports():
    """Test that all modules can be imported."""
    print("=" * 60)
    print("Testing imports...")
    print("=" * 60)
    
    try:
        # Test gz_transport imports
        print("✓ Importing gz_transport...")
        import gz_transport
        from gz_transport import Node
        print("  - Node class imported successfully")
        
        # Test gz.msgs imports
        print("\n✓ Importing gz.msgs...")
        import gz.msgs
        from gz.msgs.stringmsg_pb2 import StringMsg
        from gz.msgs.vector3d_pb2 import Vector3d
        from gz.msgs.pose_pb2 import Pose
        from gz.msgs.image_pb2 import Image
        from gz.msgs.imu_pb2 import IMU
        print("  - Common message types imported successfully")
        
        return True
    except ImportError as e:
        print(f"\n✗ Import failed: {e}")
        return False


def test_message_creation():
    """Test creating and using message objects."""
    print("\n" + "=" * 60)
    print("Testing message creation...")
    print("=" * 60)
    
    try:
        from gz.msgs.stringmsg_pb2 import StringMsg
        from gz.msgs.vector3d_pb2 import Vector3d
        from gz.msgs.pose_pb2 import Pose
        
        # Test StringMsg
        print("✓ Creating StringMsg...")
        msg = StringMsg()
        msg.data = "Hello from integrated package!"
        print(f"  - StringMsg.data = '{msg.data}'")
        
        # Test Vector3d
        print("\n✓ Creating Vector3d...")
        vec = Vector3d()
        vec.x = 1.0
        vec.y = 2.0
        vec.z = 3.0
        print(f"  - Vector3d = ({vec.x}, {vec.y}, {vec.z})")
        
        # Test Pose
        print("\n✓ Creating Pose...")
        pose = Pose()
        pose.name = "test_pose"
        pose.position.x = 10.0
        pose.position.y = 20.0
        pose.position.z = 30.0
        print(f"  - Pose '{pose.name}' at ({pose.position.x}, {pose.position.y}, {pose.position.z})")
        
        return True
    except Exception as e:
        print(f"\n✗ Message creation failed: {e}")
        return False


def test_serialization():
    """Test message serialization and deserialization."""
    print("\n" + "=" * 60)
    print("Testing serialization...")
    print("=" * 60)
    
    try:
        from gz.msgs.stringmsg_pb2 import StringMsg
        
        # Create and serialize
        print("✓ Serializing StringMsg...")
        msg1 = StringMsg()
        msg1.data = "Test serialization"
        serialized = msg1.SerializeToString()
        print(f"  - Serialized to {len(serialized)} bytes")
        
        # Deserialize
        print("\n✓ Deserializing StringMsg...")
        msg2 = StringMsg()
        msg2.ParseFromString(serialized)
        print(f"  - Deserialized: '{msg2.data}'")
        
        # Verify
        if msg1.data == msg2.data:
            print("\n✓ Serialization roundtrip successful!")
            return True
        else:
            print("\n✗ Serialization roundtrip failed: data mismatch")
            return False
            
    except Exception as e:
        print(f"\n✗ Serialization test failed: {e}")
        return False


def count_available_messages():
    """Count available message types."""
    print("\n" + "=" * 60)
    print("Counting available message types...")
    print("=" * 60)
    
    try:
        import gz.msgs
        import os
        import glob
        
        # Count .py files in gz/msgs directory
        gz_path = os.path.dirname(gz.msgs.__file__)
        msg_files = glob.glob(os.path.join(gz_path, "*_pb2.py"))
        
        print(f"✓ Found {len(msg_files)} message type files")
        print(f"\nSample message types:")
        for f in sorted(msg_files)[:10]:
            basename = os.path.basename(f).replace("_pb2.py", "")
            print(f"  - {basename}")
        print("  ... and more!")
        
        return True
    except Exception as e:
        print(f"\n✗ Failed to count messages: {e}")
        return False


def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("GZ-TRANSPORT INTEGRATION VERIFICATION")
    print("=" * 60)
    
    tests = [
        ("Import Test", test_imports),
        ("Message Creation Test", test_message_creation),
        ("Serialization Test", test_serialization),
        ("Message Count Test", count_available_messages),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL TESTS PASSED!")
        print("The gz-transport package with integrated gz-msgs is working correctly.")
    else:
        print("✗ SOME TESTS FAILED")
        print("Please check the error messages above.")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

