"""
Discovery protocol implementation using protobuf messages.

This implements gz-transport discovery protocol using the actual
protobuf Discovery message format for compatibility with C++ gz-transport.
"""

import socket
import struct
import threading
import time
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, asdict
from .options import Scope

# Import gz.msgs Discovery protobuf
try:
    from gz.msgs.discovery_pb2 import Discovery as DiscoveryMsg
    from gz.msgs.header_pb2 import Header
except ImportError:
    raise ImportError("gz.msgs not available. Install with: pip install -e .")


@dataclass
class PublisherInfo:
    """Information about a publisher."""
    topic: str
    msg_type: str
    address: str  # ZeroMQ address
    process_uuid: str
    node_uuid: str
    scope: str = "all"
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)


class Discovery:
    """
    Handles discovery of publishers and subscribers via UDP multicast.
    Uses protobuf messages for compatibility with C++ gz-transport.
    """
    
    # Default discovery settings
    MULTICAST_GROUP = '239.255.0.7'
    MULTICAST_PORT = 11317
    HEARTBEAT_INTERVAL = 1.0  # seconds
    SILENCE_TIMEOUT = 5.0     # seconds (increased for C++ compatibility)
    PROTOCOL_VERSION = 9       # gz-transport protocol version
    
    # Shared instance per process
    _instance: Optional['Discovery'] = None
    _instance_lock = threading.Lock()
    _ref_count = 0
    
    @classmethod
    def get_instance(cls, process_uuid: str, verbose: bool = False) -> 'Discovery':
        """Get or create the shared discovery instance for this process."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(process_uuid, verbose, _shared=True)
                cls._instance.start()
            cls._ref_count += 1
            return cls._instance
    
    @classmethod
    def release_instance(cls):
        """Release a reference to the shared instance."""
        with cls._instance_lock:
            cls._ref_count -= 1
            if cls._ref_count <= 0 and cls._instance is not None:
                cls._instance._shutdown()
                cls._instance = None
                cls._ref_count = 0
    
    def __init__(self, process_uuid: str, verbose: bool = False, _shared: bool = False):
        if not _shared and Discovery._instance is not None:
            raise RuntimeError("Use Discovery.get_instance() to get the shared instance")
        
        self.process_uuid = process_uuid
        self.verbose = verbose
        
        # Storage for discovered publishers (keyed by topic)
        self.publishers: Dict[str, List[PublisherInfo]] = {}
        # Store by publisher identifier (process_uuid:node_uuid:topic)
        self.publisher_map: Dict[str, PublisherInfo] = {}
        self.last_heartbeat: Dict[str, float] = {}
        
        # Callbacks
        self.connection_callbacks: List[Callable] = []
        self.disconnection_callbacks: List[Callable] = []
        
        # Threading
        self.running = False
        self.lock = threading.RLock()
        self.recv_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.cleanup_thread: Optional[threading.Thread] = None
        
        # Local publishers (advertised by this process)
        self.local_publishers: List[PublisherInfo] = []
        
        # Setup multicast socket
        self._setup_socket()
    
    def _setup_socket(self):
        """Setup UDP multicast socket."""
        # Create socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Bind to the multicast port
        self.sock.bind(('', self.MULTICAST_PORT))
        
        # Join multicast group
        mreq = struct.pack('4sL', 
                          socket.inet_aton(self.MULTICAST_GROUP),
                          socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        # Set timeout for non-blocking receive
        self.sock.settimeout(0.1)
    
    def start(self):
        """Start discovery service."""
        with self.lock:
            if self.running:
                return
            self.running = True
        
        # Start receive thread
        self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.recv_thread.start()
        
        # Start heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        
        if self.verbose:
            print(f"[Discovery] Started (UUID: {self.process_uuid}, Protocol: protobuf)")
    
    def _shutdown(self):
        """Internal shutdown method (called by release_instance)."""
        with self.lock:
            if not self.running:
                return
            self.running = False
        
        # Send BYE message
        self._send_bye()
        
        # Wait for threads
        if self.recv_thread:
            self.recv_thread.join(timeout=1.0)
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=1.0)
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=1.0)
        
        self.sock.close()
        
        if self.verbose:
            print("[Discovery] Stopped")
    
    def stop(self):
        """Stop discovery service (deprecated - use release_instance)."""
        # For backward compatibility
        self._shutdown()
    
    def advertise(self, pub_info: PublisherInfo):
        """Advertise a new publisher."""
        with self.lock:
            self.local_publishers.append(pub_info)
        
        # Broadcast advertisement
        self._send_advertise(pub_info)
        
        if self.verbose:
            print(f"[Discovery] Advertised: {pub_info.topic}")
    
    def unadvertise(self, topic: str, node_uuid: str):
        """Unadvertise a publisher."""
        with self.lock:
            pub_to_remove = None
            for p in self.local_publishers:
                if p.topic == topic and p.node_uuid == node_uuid:
                    pub_to_remove = p
                    break
            
            if pub_to_remove:
                self.local_publishers.remove(pub_to_remove)
                self._send_unadvertise(pub_to_remove)
        
        if self.verbose:
            print(f"[Discovery] Unadvertised: {topic}")
    
    def discover(self, topic: str) -> List[PublisherInfo]:
        """Request discovery of a topic."""
        # Send subscribe request
        self._send_subscribe(topic)
        
        # Return any already known publishers
        with self.lock:
            return self.publishers.get(topic, []).copy()
    
    def get_publishers(self, topic: str) -> List[PublisherInfo]:
        """Get all known publishers for a topic."""
        with self.lock:
            return self.publishers.get(topic, []).copy()
    
    def get_all_topics(self) -> List[str]:
        """Get list of all known topics."""
        with self.lock:
            return list(self.publishers.keys())
    
    def on_connection(self, callback: Callable[[PublisherInfo], None]):
        """Register callback for new publisher discovery."""
        self.connection_callbacks.append(callback)
    
    def on_disconnection(self, callback: Callable[[PublisherInfo], None]):
        """Register callback for publisher disconnection."""
        self.disconnection_callbacks.append(callback)
    
    # =========================================================================
    # Protobuf Message Creation and Sending
    # =========================================================================
    
    def _send_advertise(self, pub_info: PublisherInfo):
        """Send ADVERTISE message using protobuf."""
        disc = DiscoveryMsg()
        disc.version = self.PROTOCOL_VERSION
        disc.process_uuid = self.process_uuid
        disc.type = DiscoveryMsg.ADVERTISE
        
        # Fill publisher info
        pub = disc.pub
        pub.topic = pub_info.topic
        pub.address = pub_info.address
        pub.process_uuid = pub_info.process_uuid
        pub.node_uuid = pub_info.node_uuid
        
        # Map scope
        if pub_info.scope == "process":
            pub.scope = DiscoveryMsg.Publisher.PROCESS
        elif pub_info.scope == "host":
            pub.scope = DiscoveryMsg.Publisher.HOST
        else:
            pub.scope = DiscoveryMsg.Publisher.ALL
        
        # Fill message publisher info
        msg_pub = pub.msg_pub
        msg_pub.ctrl = pub_info.address
        msg_pub.msg_type = pub_info.msg_type
        msg_pub.throttled = False
        msg_pub.msgs_per_sec = 0
        
        self._send_protobuf(disc)
    
    def _send_unadvertise(self, pub_info: PublisherInfo):
        """Send UNADVERTISE message using protobuf."""
        disc = DiscoveryMsg()
        disc.version = self.PROTOCOL_VERSION
        disc.process_uuid = self.process_uuid
        disc.type = DiscoveryMsg.UNADVERTISE
        
        pub = disc.pub
        pub.topic = pub_info.topic
        pub.process_uuid = pub_info.process_uuid
        pub.node_uuid = pub_info.node_uuid
        
        self._send_protobuf(disc)
    
    def _send_subscribe(self, topic: str):
        """Send SUBSCRIBE message using protobuf."""
        disc = DiscoveryMsg()
        disc.version = self.PROTOCOL_VERSION
        disc.process_uuid = self.process_uuid
        disc.type = DiscoveryMsg.SUBSCRIBE
        
        sub = disc.sub
        sub.topic = topic
        
        self._send_protobuf(disc)
    
    def _send_heartbeat(self):
        """Send HEARTBEAT message using protobuf."""
        disc = DiscoveryMsg()
        disc.version = self.PROTOCOL_VERSION
        disc.process_uuid = self.process_uuid
        disc.type = DiscoveryMsg.HEARTBEAT
        
        self._send_protobuf(disc)
    
    def _send_bye(self):
        """Send BYE message using protobuf."""
        disc = DiscoveryMsg()
        disc.version = self.PROTOCOL_VERSION
        disc.process_uuid = self.process_uuid
        disc.type = DiscoveryMsg.BYE
        
        self._send_protobuf(disc)
    
    def _send_protobuf(self, disc_msg: DiscoveryMsg):
        """Send a protobuf discovery message via multicast."""
        try:
            msg_bytes = disc_msg.SerializeToString()
            self.sock.sendto(
                msg_bytes,
                (self.MULTICAST_GROUP, self.MULTICAST_PORT)
            )
        except Exception as e:
            if self.verbose:
                print(f"[Discovery] Error sending protobuf message: {e}")
    
    # =========================================================================
    # Message Reception and Parsing
    # =========================================================================
    
    def _recv_loop(self):
        """Receive and process discovery messages."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
                self._handle_protobuf_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running and self.verbose:
                    print(f"[Discovery] Error in recv loop: {e}")
    
    def _handle_protobuf_message(self, data: bytes, addr: tuple):
        """Handle incoming protobuf discovery message."""
        try:
            disc = DiscoveryMsg()
            disc.ParseFromString(data)
            
            # Ignore messages from ourselves
            if disc.process_uuid == self.process_uuid:
                return
            
            msg_type = DiscoveryMsg.Type.Name(disc.type)
            
            if disc.type == DiscoveryMsg.ADVERTISE:
                self._handle_advertise(disc)
            elif disc.type == DiscoveryMsg.UNADVERTISE:
                self._handle_unadvertise(disc)
            elif disc.type == DiscoveryMsg.SUBSCRIBE:
                self._handle_subscribe(disc)
            elif disc.type == DiscoveryMsg.HEARTBEAT:
                self._handle_heartbeat(disc)
            elif disc.type == DiscoveryMsg.BYE:
                self._handle_bye(disc)
            
        except Exception as e:
            if self.verbose:
                print(f"[Discovery] Error parsing protobuf message: {e}")
    
    def _handle_advertise(self, disc: DiscoveryMsg):
        """Handle ADVERTISE message."""
        pub = disc.pub
        
        # Map scope back to string
        if pub.scope == DiscoveryMsg.Publisher.PROCESS:
            scope_str = "process"
        elif pub.scope == DiscoveryMsg.Publisher.HOST:
            scope_str = "host"
        else:
            scope_str = "all"
        
        # Get message type
        msg_type = pub.msg_pub.msg_type if pub.HasField('msg_pub') else ""
        
        pub_info = PublisherInfo(
            topic=pub.topic,
            msg_type=msg_type,
            address=pub.address,
            process_uuid=pub.process_uuid,
            node_uuid=pub.node_uuid,
            scope=scope_str
        )
        
        pub_id = f"{pub.process_uuid}:{pub.node_uuid}:{pub.topic}"
        
        with self.lock:
            # Check if this is a new publisher
            is_new = pub_id not in self.publisher_map
            
            # Add to our maps
            self.publisher_map[pub_id] = pub_info
            self.last_heartbeat[pub_id] = time.time()
            
            # Add to topic-based index
            if pub.topic not in self.publishers:
                self.publishers[pub.topic] = []
            
            # Update or add to topic list
            existing = [p for p in self.publishers[pub.topic] 
                       if p.process_uuid == pub.process_uuid and p.node_uuid == pub.node_uuid]
            if existing:
                # Update existing
                idx = self.publishers[pub.topic].index(existing[0])
                self.publishers[pub.topic][idx] = pub_info
            else:
                # Add new
                self.publishers[pub.topic].append(pub_info)
        
        # Notify callbacks for new publishers
        if is_new:
            if self.verbose:
                print(f"[Discovery] Discovered publisher: {pub.topic} @ {pub.address}")
            for callback in self.connection_callbacks:
                try:
                    callback(pub_info)
                except Exception as e:
                    if self.verbose:
                        print(f"[Discovery] Error in connection callback: {e}")
    
    def _handle_unadvertise(self, disc: DiscoveryMsg):
        """Handle UNADVERTISE message."""
        pub = disc.pub
        pub_id = f"{pub.process_uuid}:{pub.node_uuid}:{pub.topic}"
        
        with self.lock:
            if pub_id in self.publisher_map:
                pub_info = self.publisher_map[pub_id]
                del self.publisher_map[pub_id]
                if pub_id in self.last_heartbeat:
                    del self.last_heartbeat[pub_id]
                
                # Remove from topic list
                if pub.topic in self.publishers:
                    self.publishers[pub.topic] = [
                        p for p in self.publishers[pub.topic]
                        if not (p.process_uuid == pub.process_uuid and p.node_uuid == pub.node_uuid)
                    ]
                    if not self.publishers[pub.topic]:
                        del self.publishers[pub.topic]
                
                # Notify callbacks
                for callback in self.disconnection_callbacks:
                    try:
                        callback(pub_info)
                    except Exception as e:
                        if self.verbose:
                            print(f"[Discovery] Error in disconnection callback: {e}")
    
    def _handle_subscribe(self, disc: DiscoveryMsg):
        """Handle SUBSCRIBE message - respond with our publishers."""
        sub = disc.sub
        requested_topic = sub.topic
        
        # Send our publishers for this topic
        with self.lock:
            for pub_info in self.local_publishers:
                if pub_info.topic == requested_topic or requested_topic == "":
                    self._send_advertise(pub_info)
    
    def _handle_heartbeat(self, disc: DiscoveryMsg):
        """Handle HEARTBEAT message."""
        # Update heartbeat timestamp for all publishers from this process
        with self.lock:
            for pub_id in list(self.last_heartbeat.keys()):
                if pub_id.startswith(disc.process_uuid + ":"):
                    self.last_heartbeat[pub_id] = time.time()
    
    def _handle_bye(self, disc: DiscoveryMsg):
        """Handle BYE message - remove all publishers from this process."""
        with self.lock:
            # Find all publishers from this process
            to_remove = [pid for pid in self.publisher_map.keys() 
                        if pid.startswith(disc.process_uuid + ":")]
            
            for pub_id in to_remove:
                if pub_id in self.publisher_map:
                    pub_info = self.publisher_map[pub_id]
                    del self.publisher_map[pub_id]
                    if pub_id in self.last_heartbeat:
                        del self.last_heartbeat[pub_id]
                    
                    # Remove from topic list
                    if pub_info.topic in self.publishers:
                        self.publishers[pub_info.topic] = [
                            p for p in self.publishers[pub_info.topic]
                            if not (p.process_uuid == pub_info.process_uuid and 
                                   p.node_uuid == pub_info.node_uuid)
                        ]
                        if not self.publishers[pub_info.topic]:
                            del self.publishers[pub_info.topic]
    
    # =========================================================================
    # Background Threads
    # =========================================================================
    
    def _heartbeat_loop(self):
        """Send periodic heartbeat messages."""
        while self.running:
            time.sleep(self.HEARTBEAT_INTERVAL)
            if self.running:
                self._send_heartbeat()
                # Re-advertise our publishers periodically
                with self.lock:
                    for pub_info in self.local_publishers:
                        self._send_advertise(pub_info)
    
    def _cleanup_loop(self):
        """Remove stale publishers that haven't sent heartbeats."""
        while self.running:
            time.sleep(1.0)
            if not self.running:
                break
            
            now = time.time()
            with self.lock:
                # Find stale publishers
                stale = [
                    pub_id for pub_id, last_time in self.last_heartbeat.items()
                    if now - last_time > self.SILENCE_TIMEOUT
                ]
                
                # Remove stale publishers
                for pub_id in stale:
                    if pub_id in self.publisher_map:
                        pub_info = self.publisher_map[pub_id]
                        if self.verbose:
                            print(f"[Discovery] Removing stale publisher: {pub_info.topic}")
                        
                        del self.publisher_map[pub_id]
                        del self.last_heartbeat[pub_id]
                        
                        # Remove from topic list
                        if pub_info.topic in self.publishers:
                            self.publishers[pub_info.topic] = [
                                p for p in self.publishers[pub_info.topic]
                                if p.process_uuid != pub_info.process_uuid or 
                                   p.node_uuid != pub_info.node_uuid
                            ]
                            if not self.publishers[pub_info.topic]:
                                del self.publishers[pub_info.topic]

