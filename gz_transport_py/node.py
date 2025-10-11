"""
Node implementation - main interface for pub/sub communication.
"""

import os
import zmq
import uuid
import threading
import time
from typing import Callable, Dict, List, Optional, Any
from .discovery import Discovery, PublisherInfo
from .publisher import Publisher
from .options import NodeOptions, AdvertiseOptions, SubscribeOptions, Scope
from .zenoh_backend import (
    ZenohSession, ZenohPublisher, ZenohSubscriber, is_zenoh_available
)


class Subscriber:
    """Internal subscriber representation."""
    
    def __init__(self, topic: str, callback: Callable, msg_type: type, socket: zmq.Socket):
        self.topic = topic
        self.callback = callback
        self.msg_type = msg_type
        self.socket = socket
        self.running = True
        self.thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start subscriber thread."""
        self.thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop subscriber thread."""
        self.running = False
        # Don't join daemon threads - they'll terminate with the process
        # if self.thread:
        #     self.thread.join(timeout=0.1)
    
    def _recv_loop(self):
        """Receive messages in a loop."""
        # Set socket timeout
        self.socket.setsockopt(zmq.RCVTIMEO, 100)
        
        while self.running:
            try:
                # Receive multipart message [topic, data]
                parts = self.socket.recv_multipart()
                if len(parts) >= 2:
                    topic = parts[0].decode('utf-8')
                    msg_bytes = parts[1]
                    
                    # Deserialize and call callback
                    try:
                        msg = self.msg_type()
                        msg.ParseFromString(msg_bytes)
                        self.callback(msg)
                    except Exception as e:
                        print(f"[Subscriber] Callback error: {e}")
            except zmq.Again:
                # Timeout, continue
                continue
            except Exception as e:
                if self.running:
                    print(f"[Subscriber] Receive error: {e}")


class Node:
    """
    A transport node for pub/sub communication.
    
    Provides methods to advertise topics, subscribe to topics,
    and discover other nodes on the network.
    """
    
    # Shared process UUID for all nodes in this process
    _process_uuid: Optional[str] = None
    _process_uuid_lock = threading.Lock()
    
    @classmethod
    def _get_process_uuid(cls) -> str:
        """Get or create the shared process UUID."""
        with cls._process_uuid_lock:
            if cls._process_uuid is None:
                cls._process_uuid = str(uuid.uuid4())
            return cls._process_uuid
    
    def __init__(self, options: Optional[NodeOptions] = None, verbose: bool = False):
        self.options = options or NodeOptions()
        self.verbose = verbose
        
        # Get shared process UUID and generate unique node UUID
        self.process_uuid = Node._get_process_uuid()
        self.node_uuid = str(uuid.uuid4())
        
        # Determine transport implementation (zeromq or zenoh)
        self.implementation = os.environ.get('GZ_TRANSPORT_IMPLEMENTATION', 'zeromq').lower()
        
        # Validate implementation
        if self.implementation not in ['zeromq', 'zenoh']:
            print(f"[Node] Warning: Unrecognized GZ_TRANSPORT_IMPLEMENTATION: {self.implementation}")
            print(f"[Node] Falling back to zeromq")
            self.implementation = 'zeromq'
        
        # Check if Zenoh is available when requested
        if self.implementation == 'zenoh':
            if not is_zenoh_available():
                print("[Node] Warning: Zenoh implementation requested but zenoh module not available")
                print("[Node] Falling back to zeromq. Install zenoh with: pip install eclipse-zenoh")
                self.implementation = 'zeromq'
        
        # Initialize backend-specific resources
        self.context = None
        self.zenoh_session = None
        
        if self.implementation == 'zeromq':
            # ZeroMQ context
            self.context = zmq.Context()
        elif self.implementation == 'zenoh':
            # Zenoh session
            try:
                self.zenoh_session = ZenohSession.get_instance()
            except Exception as e:
                print(f"[Node] Error creating Zenoh session: {e}")
                print("[Node] Falling back to zeromq")
                self.implementation = 'zeromq'
                self.context = zmq.Context()
        
        # Publishers and subscribers
        self.publishers: Dict[str, Publisher] = {}
        self.publisher_sockets: Dict[str, zmq.Socket] = {}  # Only for ZeroMQ
        self.subscribers: Dict[str, Subscriber] = {}  # Only for ZeroMQ
        self.zenoh_publishers: Dict[str, ZenohPublisher] = {}  # Only for Zenoh
        self.zenoh_subscribers: Dict[str, ZenohSubscriber] = {}  # Only for Zenoh
        
        # Get shared discovery instance (only used for ZeroMQ)
        if self.implementation == 'zeromq':
            self.discovery = Discovery.get_instance(self.process_uuid, verbose=verbose)
            self.discovery.on_connection(self._on_publisher_discovered)
        
        # Wait a bit for initialization
        time.sleep(0.1)
        
        if self.verbose:
            print(f"[Node] Created (UUID: {self.node_uuid}, Implementation: {self.implementation})")
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.shutdown()
        except:
            pass  # Ignore errors during cleanup
    
    def shutdown(self):
        """Shutdown the node."""
        if self.implementation == 'zeromq':
            # Stop all ZeroMQ subscribers
            for sub in list(self.subscribers.values()):
                try:
                    sub.stop()
                except:
                    pass
            
            # Close all ZeroMQ sockets
            for socket in list(self.publisher_sockets.values()):
                try:
                    socket.close()
                except:
                    pass
            
            # Terminate ZeroMQ context
            if hasattr(self, 'context') and self.context:
                try:
                    self.context.term()
                except:
                    pass
            
            # Release discovery reference
            if hasattr(self, 'discovery'):
                try:
                    Discovery.release_instance()
                except:
                    pass
        
        elif self.implementation == 'zenoh':
            # Stop all Zenoh subscribers
            for sub in list(self.zenoh_subscribers.values()):
                try:
                    sub.stop()
                except:
                    pass
            
            # Invalidate all Zenoh publishers
            for pub in list(self.zenoh_publishers.values()):
                try:
                    pub.invalidate()
                except:
                    pass
            
            # Release Zenoh session
            if hasattr(self, 'zenoh_session') and self.zenoh_session:
                try:
                    ZenohSession.release_instance()
                except:
                    pass
        
        if self.verbose:
            print("[Node] Shutdown complete")
    
    def advertise(self, topic: str, msg_type: type, 
                  options: Optional[AdvertiseOptions] = None) -> Publisher:
        """
        Advertise a topic for publishing.
        
        Args:
            topic: Topic name
            msg_type: Protobuf message type (class)
            options: Advertise options
            
        Returns:
            Publisher instance
        """
        options = options or AdvertiseOptions()
        
        # Apply namespace/partition
        full_topic = self._build_topic_name(topic)
        
        # Get message type name
        msg_type_name = msg_type.DESCRIPTOR.full_name if hasattr(msg_type, 'DESCRIPTOR') else str(msg_type)
        
        if self.implementation == 'zeromq':
            # Check if already advertised
            if full_topic in self.publishers:
                return self.publishers[full_topic]
            
            # Create ZeroMQ PUB socket
            socket = self.context.socket(zmq.PUB)
            port = socket.bind_to_random_port('tcp://*')
            address = f"tcp://localhost:{port}"
            
            # Store socket
            self.publisher_sockets[full_topic] = socket
            
            # Create publisher
            publisher = Publisher(socket, full_topic, msg_type_name, address)
            self.publishers[full_topic] = publisher
            
            # Advertise via discovery
            pub_info = PublisherInfo(
                topic=full_topic,
                msg_type=msg_type_name,
                address=address,
                process_uuid=self.process_uuid,
                node_uuid=self.node_uuid,
                scope=options.scope.value
            )
            self.discovery.advertise(pub_info)
            
            if self.verbose:
                print(f"[Node] Advertised: {full_topic} at {address}")
            
            return publisher
        
        elif self.implementation == 'zenoh':
            # Check if already advertised
            if full_topic in self.zenoh_publishers:
                # Return a Publisher wrapper
                z_pub = self.zenoh_publishers[full_topic]
                return Publisher(None, full_topic, msg_type_name, "", zenoh_publisher=z_pub)
            
            # Create Zenoh publisher
            z_pub = ZenohPublisher(
                topic=full_topic,
                msg_type_name=msg_type_name,
                session=self.zenoh_session,
                process_uuid=self.process_uuid,
                node_uuid=self.node_uuid,
                verbose=self.verbose
            )
            self.zenoh_publishers[full_topic] = z_pub
            
            if self.verbose:
                print(f"[Node] Advertised (Zenoh): {full_topic}")
            
            # Return a Publisher wrapper
            return Publisher(None, full_topic, msg_type_name, "", zenoh_publisher=z_pub)
    
    def subscribe(self, msg_type: type, topic: str, callback: Callable[[Any], None],
                  options: Optional[SubscribeOptions] = None,
                  publisher_address: Optional[str] = None) -> bool:
        """
        Subscribe to a topic.
        
        Args:
            msg_type: Protobuf message type (class)
            topic: Topic name
            callback: Callback function that receives messages
            options: Subscribe options
            publisher_address: Optional direct publisher address (bypasses discovery)
                              Format: "tcp://host:port"
            
        Returns:
            True if successful
        """
        options = options or SubscribeOptions()
        
        # Apply namespace/partition
        full_topic = self._build_topic_name(topic)
        
        if self.implementation == 'zeromq':
            # Check if already subscribed
            if full_topic in self.subscribers:
                if self.verbose:
                    print(f"[Node] Already subscribed to: {full_topic}")
                return True
            
            # Create ZeroMQ SUB socket
            socket = self.context.socket(zmq.SUB)
            socket.setsockopt_string(zmq.SUBSCRIBE, full_topic)
            
            # Create subscriber
            subscriber = Subscriber(full_topic, callback, msg_type, socket)
            self.subscribers[full_topic] = subscriber
            
            if publisher_address:
                # Manual connection - bypass discovery
                try:
                    socket.connect(publisher_address)
                    if self.verbose:
                        print(f"[Node] Connected directly to: {publisher_address}")
                except Exception as e:
                    if self.verbose:
                        print(f"[Node] Error connecting to {publisher_address}: {e}")
                    return False
            else:
                # Discover publishers
                publishers = self.discovery.discover(full_topic)
                
                # Connect to known publishers
                for pub_info in publishers:
                    self._connect_subscriber(socket, pub_info)
            
            # Start subscriber thread
            subscriber.start()
            
            if self.verbose:
                print(f"[Node] Subscribed to: {full_topic}")
            
            return True
        
        elif self.implementation == 'zenoh':
            # Check if already subscribed
            if full_topic in self.zenoh_subscribers:
                if self.verbose:
                    print(f"[Node] Already subscribed to: {full_topic}")
                return True
            
            # Create Zenoh subscriber
            z_sub = ZenohSubscriber(
                topic=full_topic,
                msg_type=msg_type,
                callback=callback,
                session=self.zenoh_session,
                process_uuid=self.process_uuid,
                node_uuid=self.node_uuid,
                verbose=self.verbose
            )
            self.zenoh_subscribers[full_topic] = z_sub
            
            if self.verbose:
                print(f"[Node] Subscribed (Zenoh): {full_topic}")
            
            return True
    
    def unsubscribe(self, topic: str) -> bool:
        """
        Unsubscribe from a topic.
        
        Args:
            topic: Topic name
            
        Returns:
            True if successful
        """
        full_topic = self._build_topic_name(topic)
        
        if self.implementation == 'zeromq':
            if full_topic in self.subscribers:
                sub = self.subscribers[full_topic]
                sub.stop()
                sub.socket.close()
                del self.subscribers[full_topic]
                
                if self.verbose:
                    print(f"[Node] Unsubscribed from: {full_topic}")
                return True
        
        elif self.implementation == 'zenoh':
            if full_topic in self.zenoh_subscribers:
                sub = self.zenoh_subscribers[full_topic]
                sub.stop()
                del self.zenoh_subscribers[full_topic]
                
                if self.verbose:
                    print(f"[Node] Unsubscribed (Zenoh) from: {full_topic}")
                return True
        
        return False
    
    def unadvertise(self, topic: str) -> bool:
        """
        Unadvertise a topic.
        
        Args:
            topic: Topic name
            
        Returns:
            True if successful
        """
        full_topic = self._build_topic_name(topic)
        
        if self.implementation == 'zeromq':
            if full_topic in self.publishers:
                pub = self.publishers[full_topic]
                pub.invalidate()
                
                # Close socket
                if full_topic in self.publisher_sockets:
                    self.publisher_sockets[full_topic].close()
                    del self.publisher_sockets[full_topic]
                
                del self.publishers[full_topic]
                
                # Notify discovery
                self.discovery.unadvertise(full_topic, self.node_uuid)
                
                if self.verbose:
                    print(f"[Node] Unadvertised: {full_topic}")
                return True
        
        elif self.implementation == 'zenoh':
            if full_topic in self.zenoh_publishers:
                pub = self.zenoh_publishers[full_topic]
                pub.invalidate()
                del self.zenoh_publishers[full_topic]
                
                if self.verbose:
                    print(f"[Node] Unadvertised (Zenoh): {full_topic}")
                return True
        
        return False
    
    def topic_list(self) -> List[str]:
        """
        Get list of all known topics.
        
        Returns:
            List of topic names
        """
        if self.implementation == 'zeromq':
            return self.discovery.get_all_topics()
        elif self.implementation == 'zenoh':
            # For Zenoh, return topics we know about (advertised or subscribed)
            topics = set()
            topics.update(self.zenoh_publishers.keys())
            topics.update(self.zenoh_subscribers.keys())
            return list(topics)
        return []
    
    def advertised_topics(self) -> List[str]:
        """
        Get list of topics advertised by this node.
        
        Returns:
            List of topic names
        """
        if self.implementation == 'zeromq':
            return list(self.publishers.keys())
        elif self.implementation == 'zenoh':
            return list(self.zenoh_publishers.keys())
        return []
    
    def subscribed_topics(self) -> List[str]:
        """
        Get list of topics subscribed by this node.
        
        Returns:
            List of topic names
        """
        if self.implementation == 'zeromq':
            return list(self.subscribers.keys())
        elif self.implementation == 'zenoh':
            return list(self.zenoh_subscribers.keys())
        return []
    
    def _build_topic_name(self, topic: str) -> str:
        """Build full topic name with namespace and partition."""
        # Apply remapping
        topic = self.options.get_remapped_topic(topic)
        
        # Add namespace
        if self.options.namespace:
            if not topic.startswith('/'):
                topic = '/' + topic
            topic = f"/{self.options.namespace}{topic}"
        
        # Add partition (prefix with @)
        if self.options.partition:
            topic = f"@{self.options.partition}@{topic}"
        
        return topic
    
    def _on_publisher_discovered(self, pub_info: PublisherInfo):
        """Handle discovery of a new publisher."""
        # Check if we have a subscriber for this topic
        if pub_info.topic in self.subscribers:
            subscriber = self.subscribers[pub_info.topic]
            self._connect_subscriber(subscriber.socket, pub_info)
            
            if self.verbose:
                print(f"[Node] Connected subscriber to new publisher: {pub_info.topic}")
    
    def _connect_subscriber(self, socket: zmq.Socket, pub_info: PublisherInfo):
        """Connect a subscriber socket to a publisher."""
        try:
            socket.connect(pub_info.address)
            if self.verbose:
                print(f"[Node] Connected to {pub_info.address}")
        except Exception as e:
            if self.verbose:
                print(f"[Node] Error connecting to {pub_info.address}: {e}")

