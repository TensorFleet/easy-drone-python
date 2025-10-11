"""
Discovery protocol implementation using UDP multicast.

This implements a simplified version of the gz-transport discovery protocol.
"""

import socket
import struct
import threading
import time
import uuid
import json
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, asdict
from .options import Scope


# Discovery message types
class MsgType:
    ADVERTISE = "advertise"
    UNADVERTISE = "unadvertise"
    SUBSCRIBE = "subscribe"
    HEARTBEAT = "heartbeat"
    BYE = "bye"


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
    """
    
    # Default discovery settings
    MULTICAST_GROUP = '239.255.0.7'
    MULTICAST_PORT = 11317
    HEARTBEAT_INTERVAL = 1.0  # seconds
    SILENCE_TIMEOUT = 3.0     # seconds
    
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
        
        # Storage for discovered publishers
        self.publishers: Dict[str, List[PublisherInfo]] = {}
        self.last_heartbeat: Dict[str, float] = {}
        
        # Callbacks
        self.connection_callbacks: List[Callable] = []
        self.disconnection_callbacks: List[Callable] = []
        
        # Threading
        self.running = False
        self.lock = threading.RLock()
        self.recv_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        
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
        
        if self.verbose:
            print(f"[Discovery] Started (UUID: {self.process_uuid})")
    
    def _shutdown(self):
        """Internal shutdown method (called by release_instance)."""
        with self.lock:
            if not self.running:
                return
            self.running = False
        
        # Send BYE message
        self._send_message(MsgType.BYE, {})
        
        # Wait for threads
        if self.recv_thread:
            self.recv_thread.join(timeout=1.0)
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=1.0)
        
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
        self._send_message(MsgType.ADVERTISE, pub_info.to_dict())
        
        if self.verbose:
            print(f"[Discovery] Advertised: {pub_info.topic}")
    
    def unadvertise(self, topic: str, node_uuid: str):
        """Unadvertise a publisher."""
        with self.lock:
            self.local_publishers = [
                p for p in self.local_publishers 
                if not (p.topic == topic and p.node_uuid == node_uuid)
            ]
        
        self._send_message(MsgType.UNADVERTISE, {
            'topic': topic,
            'node_uuid': node_uuid,
            'process_uuid': self.process_uuid
        })
        
        if self.verbose:
            print(f"[Discovery] Unadvertised: {topic}")
    
    def discover(self, topic: str) -> List[PublisherInfo]:
        """Request discovery of a topic."""
        # Send subscribe request
        self._send_message(MsgType.SUBSCRIBE, {'topic': topic})
        
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
    
    def _send_message(self, msg_type: str, data: dict):
        """Send a discovery message."""
        message = {
            'type': msg_type,
            'process_uuid': self.process_uuid,
            'data': data
        }
        
        msg_bytes = json.dumps(message).encode('utf-8')
        
        try:
            self.sock.sendto(
                msg_bytes,
                (self.MULTICAST_GROUP, self.MULTICAST_PORT)
            )
        except Exception as e:
            if self.verbose:
                print(f"[Discovery] Error sending message: {e}")
    
    def _recv_loop(self):
        """Receive and process discovery messages."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
                self._handle_message(data, addr)
            except socket.timeout:
                # Check for stale publishers
                self._check_timeouts()
            except Exception as e:
                if self.running and self.verbose:
                    print(f"[Discovery] Receive error: {e}")
    
    def _handle_message(self, data: bytes, addr):
        """Handle received discovery message."""
        try:
            message = json.loads(data.decode('utf-8'))
            
            msg_type = message['type']
            process_uuid = message['process_uuid']
            msg_data = message['data']
            
            # Ignore our own messages
            if process_uuid == self.process_uuid:
                return
            
            # Update heartbeat timestamp
            with self.lock:
                self.last_heartbeat[process_uuid] = time.time()
            
            if msg_type == MsgType.ADVERTISE:
                self._handle_advertise(msg_data)
            elif msg_type == MsgType.UNADVERTISE:
                self._handle_unadvertise(msg_data)
            elif msg_type == MsgType.SUBSCRIBE:
                self._handle_subscribe(msg_data)
            elif msg_type == MsgType.HEARTBEAT:
                pass  # Already updated timestamp
            elif msg_type == MsgType.BYE:
                self._handle_bye(process_uuid)
                
        except Exception as e:
            if self.verbose:
                print(f"[Discovery] Error handling message: {e}")
    
    def _handle_advertise(self, data: dict):
        """Handle ADVERTISE message."""
        pub_info = PublisherInfo.from_dict(data)
        
        # Check scope
        if pub_info.scope == Scope.PROCESS.value:
            return  # Don't register remote PROCESS scope publishers
        
        with self.lock:
            topic = pub_info.topic
            if topic not in self.publishers:
                self.publishers[topic] = []
            
            # Check if already exists
            exists = any(
                p.process_uuid == pub_info.process_uuid and 
                p.node_uuid == pub_info.node_uuid
                for p in self.publishers[topic]
            )
            
            if not exists:
                self.publishers[topic].append(pub_info)
                
                if self.verbose:
                    print(f"[Discovery] New publisher: {topic} from {pub_info.process_uuid[:8]}")
                
                # Trigger callbacks
                for callback in self.connection_callbacks:
                    try:
                        callback(pub_info)
                    except Exception as e:
                        if self.verbose:
                            print(f"[Discovery] Callback error: {e}")
    
    def _handle_unadvertise(self, data: dict):
        """Handle UNADVERTISE message."""
        topic = data['topic']
        node_uuid = data['node_uuid']
        process_uuid = data['process_uuid']
        
        with self.lock:
            if topic in self.publishers:
                removed = [
                    p for p in self.publishers[topic]
                    if p.process_uuid == process_uuid and p.node_uuid == node_uuid
                ]
                
                self.publishers[topic] = [
                    p for p in self.publishers[topic]
                    if not (p.process_uuid == process_uuid and p.node_uuid == node_uuid)
                ]
                
                if not self.publishers[topic]:
                    del self.publishers[topic]
                
                # Trigger callbacks
                for pub in removed:
                    for callback in self.disconnection_callbacks:
                        try:
                            callback(pub)
                        except Exception as e:
                            if self.verbose:
                                print(f"[Discovery] Callback error: {e}")
    
    def _handle_subscribe(self, data: dict):
        """Handle SUBSCRIBE message - respond with our advertised topics."""
        topic = data['topic']
        
        with self.lock:
            # Check if we have this topic
            matching_pubs = [
                p for p in self.local_publishers 
                if p.topic == topic
            ]
        
        # Send ADVERTISE for matching topics
        for pub in matching_pubs:
            self._send_message(MsgType.ADVERTISE, pub.to_dict())
    
    def _handle_bye(self, process_uuid: str):
        """Handle BYE message - remove all publishers from this process."""
        with self.lock:
            removed_pubs = []
            for topic in list(self.publishers.keys()):
                removed = [
                    p for p in self.publishers[topic]
                    if p.process_uuid == process_uuid
                ]
                removed_pubs.extend(removed)
                
                self.publishers[topic] = [
                    p for p in self.publishers[topic]
                    if p.process_uuid != process_uuid
                ]
                
                if not self.publishers[topic]:
                    del self.publishers[topic]
            
            # Remove heartbeat entry
            self.last_heartbeat.pop(process_uuid, None)
            
            # Trigger callbacks
            for pub in removed_pubs:
                for callback in self.disconnection_callbacks:
                    try:
                        callback(pub)
                    except Exception as e:
                        if self.verbose:
                            print(f"[Discovery] Callback error: {e}")
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats and re-advertise topics."""
        while self.running:
            time.sleep(self.HEARTBEAT_INTERVAL)
            
            if not self.running:
                break
            
            # Send heartbeat
            self._send_message(MsgType.HEARTBEAT, {})
            
            # Re-advertise all local publishers
            with self.lock:
                pubs = self.local_publishers.copy()
            
            for pub in pubs:
                self._send_message(MsgType.ADVERTISE, pub.to_dict())
    
    def _check_timeouts(self):
        """Check for stale publishers that haven't sent heartbeats."""
        current_time = time.time()
        
        with self.lock:
            stale_processes = [
                puuid for puuid, last_time in self.last_heartbeat.items()
                if current_time - last_time > self.SILENCE_TIMEOUT
            ]
        
        # Remove stale publishers
        for process_uuid in stale_processes:
            self._handle_bye(process_uuid)

