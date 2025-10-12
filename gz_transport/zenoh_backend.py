"""
Zenoh backend implementation for gz-transport-py.

This module provides Zenoh-based pub/sub transport as an alternative
to ZeroMQ, matching the C++ gz-transport implementation.
"""

import threading
import uuid
from typing import Callable, Optional, Any
try:
    import zenoh
    ZENOH_AVAILABLE = True
except ImportError:
    ZENOH_AVAILABLE = False


def sanitize_topic_for_zenoh(topic: str) -> str:
    """
    Sanitize a gz-transport topic for use as a Zenoh key expression.
    
    Zenoh key expressions cannot have:
    - Leading slashes
    - Trailing slashes
    - Empty chunks (consecutive slashes)
    
    Args:
        topic: The gz-transport topic (e.g., "/camera", "/world/model/sensor")
        
    Returns:
        Sanitized topic suitable for Zenoh (e.g., "camera", "world/model/sensor")
    """
    # Remove leading and trailing slashes
    topic = topic.strip('/')
    
    # Remove empty chunks (replace // with /)
    while '//' in topic:
        topic = topic.replace('//', '/')
    
    # If topic is empty after sanitization, use a default
    if not topic:
        topic = "gz_topic"
    
    return topic


class ZenohSession:
    """
    Singleton Zenoh session manager.
    
    Manages a shared Zenoh session for all nodes in the process,
    similar to the C++ implementation.
    """
    
    _instance: Optional['ZenohSession'] = None
    _lock = threading.Lock()
    
    def __init__(self):
        if not ZENOH_AVAILABLE:
            raise ImportError("zenoh module not available. Install with: pip install eclipse-zenoh")
        
        # Create Zenoh session with default config
        config = zenoh.Config()
        self.session = zenoh.open(config)
        self._ref_count = 0
        self._ref_lock = threading.Lock()
        
    @classmethod
    def get_instance(cls) -> 'ZenohSession':
        """Get or create the shared Zenoh session."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = ZenohSession()
            cls._instance._increment_ref()
            return cls._instance
    
    @classmethod
    def release_instance(cls):
        """Release a reference to the Zenoh session."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._decrement_ref()
                if cls._instance._ref_count <= 0:
                    cls._instance._shutdown()
                    cls._instance = None
    
    def _increment_ref(self):
        """Increment reference count."""
        with self._ref_lock:
            self._ref_count += 1
    
    def _decrement_ref(self):
        """Decrement reference count."""
        with self._ref_lock:
            self._ref_count -= 1
    
    def _shutdown(self):
        """Shutdown the Zenoh session."""
        if hasattr(self, 'session'):
            try:
                self.session.close()
            except:
                pass


class ZenohPublisher:
    """
    Zenoh-based publisher.
    
    Publishes messages using Zenoh's pub/sub system, with message type
    passed as an attachment (matching C++ implementation).
    """
    
    def __init__(self, topic: str, msg_type_name: str, session: ZenohSession, 
                 process_uuid: str, node_uuid: str, verbose: bool = False):
        self.topic = topic  # Keep original topic for reference
        self.msg_type_name = msg_type_name
        self.session = session
        self.process_uuid = process_uuid
        self.node_uuid = node_uuid
        self.verbose = verbose
        self._valid = True
        
        # Sanitize topic for Zenoh (remove leading/trailing slashes)
        zenoh_topic = sanitize_topic_for_zenoh(topic)
        self.zenoh_topic = zenoh_topic
        
        # Create Zenoh publisher
        self.z_publisher = self.session.session.declare_publisher(zenoh_topic)
        
        # Create liveliness token for discovery
        # Format: topic/process_uuid/node_uuid/MS/msg_type
        # MS = Message Subscriber pattern (matching C++)
        token_key = f"{zenoh_topic}/{process_uuid}/{node_uuid}/MS/{msg_type_name}"
        self.liveliness_token = self.session.session.liveliness().declare_token(token_key)
        
        if self.verbose:
            print(f"[ZenohPublisher] Created publisher for {topic} (Zenoh key: {zenoh_topic})")
    
    def publish(self, proto_msg: Any) -> bool:
        """
        Publish a protobuf message.
        
        Args:
            proto_msg: Protobuf message instance
            
        Returns:
            True if successful
        """
        if not self._valid:
            return False
        
        try:
            # Serialize the message
            msg_bytes = proto_msg.SerializeToString()
            
            # Create attachment with message type
            # This matches the C++ implementation which passes msg type as attachment
            attachment = self.msg_type_name.encode('utf-8')
            
            # Publish with attachment
            self.z_publisher.put(msg_bytes, attachment=attachment)
            
            if self.verbose:
                print(f"[ZenohPublisher] Published message on {self.topic}")
            
            return True
        except Exception as e:
            print(f"[ZenohPublisher] Error publishing: {e}")
            return False
    
    def publish_raw(self, msg_bytes: bytes) -> bool:
        """
        Publish raw bytes.
        
        Args:
            msg_bytes: Serialized message bytes
            
        Returns:
            True if successful
        """
        if not self._valid:
            return False
        
        try:
            # Create attachment with message type
            attachment = self.msg_type_name.encode('utf-8')
            
            # Publish with attachment
            self.z_publisher.put(msg_bytes, attachment=attachment)
            
            return True
        except Exception as e:
            print(f"[ZenohPublisher] Error publishing raw: {e}")
            return False
    
    def valid(self) -> bool:
        """Check if publisher is valid."""
        return self._valid
    
    def invalidate(self):
        """Invalidate the publisher."""
        self._valid = False
        try:
            if hasattr(self, 'liveliness_token'):
                self.liveliness_token.undeclare()
        except:
            pass


class ZenohSubscriber:
    """
    Zenoh-based subscriber.
    
    Subscribes to messages using Zenoh's pub/sub system, with callback
    execution matching the C++ implementation pattern.
    """
    
    def __init__(self, topic: str, msg_type: type, callback: Callable, 
                 session: ZenohSession, process_uuid: str, node_uuid: str,
                 verbose: bool = False):
        self.topic = topic  # Keep original topic for reference
        self.msg_type = msg_type
        self.callback = callback
        self.session = session
        self.process_uuid = process_uuid
        self.node_uuid = node_uuid
        self.verbose = verbose
        self.running = True
        
        # Get message type name
        self.msg_type_name = (msg_type.DESCRIPTOR.full_name 
                             if hasattr(msg_type, 'DESCRIPTOR') 
                             else str(msg_type))
        
        # Sanitize topic for Zenoh (remove leading/trailing slashes)
        zenoh_topic = sanitize_topic_for_zenoh(topic)
        self.zenoh_topic = zenoh_topic
        
        # Create Zenoh subscriber with callback
        def zenoh_callback(sample):
            self._handle_sample(sample)
        
        self.z_subscriber = self.session.session.declare_subscriber(
            zenoh_topic, zenoh_callback
        )
        
        # Create liveliness token for discovery
        # Format: topic/process_uuid/node_uuid/MS/msg_type
        token_key = f"{zenoh_topic}/{process_uuid}/{node_uuid}/MS/{self.msg_type_name}"
        self.liveliness_token = self.session.session.liveliness().declare_token(token_key)
        
        if self.verbose:
            print(f"[ZenohSubscriber] Created subscriber for {topic} (Zenoh key: {zenoh_topic})")
    
    def _handle_sample(self, sample):
        """Handle incoming Zenoh sample."""
        if not self.running:
            return
        
        try:
            # Get the attachment (message type)
            attachment = sample.attachment
            
            if attachment is not None:
                # Decode attachment to get message type
                msg_type_from_attachment = attachment.decode('utf-8')
                
                # Check if message type matches (or if we accept any type)
                if msg_type_from_attachment != self.msg_type_name:
                    if self.verbose:
                        print(f"[ZenohSubscriber] Type mismatch: expected {self.msg_type_name}, "
                              f"got {msg_type_from_attachment}")
                    return
            else:
                if self.verbose:
                    print("[ZenohSubscriber] Warning: No attachment found, cannot verify message type")
            
            # Get the payload
            payload = sample.payload.to_bytes()
            
            # Deserialize and call callback
            msg = self.msg_type()
            msg.ParseFromString(payload)
            self.callback(msg)
            
            if self.verbose:
                print(f"[ZenohSubscriber] Received message on {self.topic}")
                
        except Exception as e:
            print(f"[ZenohSubscriber] Error handling sample: {e}")
    
    def stop(self):
        """Stop the subscriber."""
        self.running = False
        try:
            if hasattr(self, 'z_subscriber'):
                self.z_subscriber.undeclare()
            if hasattr(self, 'liveliness_token'):
                self.liveliness_token.undeclare()
        except:
            pass
        
        if self.verbose:
            print(f"[ZenohSubscriber] Stopped subscriber for {self.topic}")


def is_zenoh_available() -> bool:
    """Check if Zenoh is available."""
    return ZENOH_AVAILABLE

