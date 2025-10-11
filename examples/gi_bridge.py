#!/usr/bin/env python3
"""
Gazebo → GStreamer video bridge

Subscribes to a Gazebo Harmonic image topic (gz-transport) and pushes raw RGB
frames into a GStreamer pipeline that encodes to H.264 and streams via UDP.

Sends raw H.264 stream (no RTP encapsulation) for simpler decoding.

Defaults to software x264 encoder, auto-switches to NVENC if available.

This version uses gz-transport-py (custom Python library).
"""
import argparse
import os
import signal
import sys

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from gz_transport_py import Node
    from gz.msgs.image_pb2 import Image
except Exception as e:
    print("[gz_video_bridge] ERROR: gz-transport-py or gz-msgs not available.")
    print("Install gz-transport-py: cd gz-transport-py && pip install -e .")
    print("Install gz-msgs: cd gz-msgs-py && pip install -e .")
    raise


class GzToGStreamerBridge:
    def __init__(self, args: argparse.Namespace) -> None:
        self.gz_topic = args.gz_topic
        self.udp_host = args.ip
        self.udp_port = args.port
        self.framerate = args.fps
        self.use_nvenc = args.encoder == 'nvenc'
        self.bitrate_kbps = args.bitrate

        Gst.init(None)

        pipeline_str = self._build_pipeline()
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.appsrc = self.pipeline.get_by_name('py_source')
        if self.appsrc is None:
            raise RuntimeError("appsrc 'py_source' not found in pipeline")

        # Respect GZ_PARTITION if set for discovery
        partition = os.getenv('GZ_PARTITION')
        if partition:
            print(f"[gz_video_bridge] Using GZ_PARTITION={partition}")

        # Create node with verbose output
        self.node = Node(verbose=True)
        
        # Get manual publisher address if specified
        publisher_addr = args.publisher_address or os.getenv('GZ_PUBLISHER_ADDRESS')
        
        # Subscribe to image topic
        # Note: gz-transport-py uses (msg_type, topic, callback) order
        ok = self.node.subscribe(
            Image, 
            self.gz_topic, 
            self._on_new_gz_frame,
            publisher_address=publisher_addr
        )
        if not ok:
            raise RuntimeError(f"Failed to subscribe to Gazebo topic: {self.gz_topic}")

        self.main_loop = GLib.MainLoop()

    def _build_pipeline(self) -> str:
        encoder = (
            f"nvh264enc preset=low-latency-hq bitrate={self.bitrate_kbps} rc-mode=cbr ! "
            if self.use_nvenc else
            f"x264enc speed-preset=ultrafast tune=zerolatency bitrate={self.bitrate_kbps} ! "
        )

        # Note: caps set dynamically on first frame since width/height are unknown
        # Sending raw H.264 over UDP (no RTP encapsulation)
        pipeline = (
            "appsrc name=py_source format=time is-live=true do-timestamp=true ! "
            "videoconvert ! "
            f"{encoder}"
            "h264parse ! "  # Parse H.264 stream for proper framing
            f"udpsink host={self.udp_host} port={self.udp_port}"
        )
        return pipeline

    def _on_new_gz_frame(self, msg: Image) -> None:
        if self.appsrc is None:
            return

        # Set caps lazily on first frame
        if self.appsrc.get_property('caps') is None:
            caps_str = (
                f"video/x-raw,format=RGB,width={msg.width},height={msg.height},"
                f"framerate={self.framerate}/1"
            )
            caps = Gst.Caps.from_string(caps_str)
            self.appsrc.set_property('caps', caps)
            print(f"[gz_video_bridge] Configured caps: {caps_str}")

        # Wrap the underlying bytes as a Gst.Buffer
        try:
            # Zero-copy wrap (no memcpy) if supported; msg.data is bytes-like
            buf = Gst.Buffer.new_wrapped(msg.data)
        except Exception:
            # Fallback: allocate and copy
            buf = Gst.Buffer.new_allocate(None, len(msg.data), None)
            buf.fill(0, msg.data)

        ret = self.appsrc.emit('push-buffer', buf)
        if ret != Gst.FlowReturn.OK:
            print(f"[gz_video_bridge] WARN: push-buffer returned {ret}")

    def run(self) -> None:
        self.pipeline.set_state(Gst.State.PLAYING)
        print(f"[gz_video_bridge] Streaming raw H.264 to udp://{self.udp_host}:{self.udp_port}")
        print(f"[gz_video_bridge] Subscribed: {self.gz_topic}")
        print(f"[gz_video_bridge] Note: Sending raw H.264, not RTP (no rtph264pay)")

        # Watchdog: warn if no frames for N seconds
        def _watchdog():
            # After 5 seconds, if caps still None, likely no frames
            src = self.appsrc
            if src is not None and src.get_property('caps') is None:
                print("[gz_video_bridge] WARNING: No frames received from Gazebo yet.")
                print("  Troubleshooting:")
                print("   - Verify publisher visible: gz topic -i -t", self.gz_topic)
                print("   - Echo messages: gz topic -e -t", self.gz_topic)
                print("   - Partitions: export GZ_PARTITION to match simulator if set")
                print("   - Check that Gazebo and this bridge run under same user env")
                print("   - Ensure gz-transport-py is properly installed")

        GLib.timeout_add_seconds(5, _watchdog)

        def _stop_loop(_sig, _frm):
            try:
                self.main_loop.quit()
            except Exception:
                pass

        signal.signal(signal.SIGINT, _stop_loop)
        signal.signal(signal.SIGTERM, _stop_loop)

        try:
            self.main_loop.run()
        finally:
            print("[gz_video_bridge] Shutting down...")
            self.pipeline.set_state(Gst.State.NULL)
            self.node.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Gazebo → GStreamer UDP H.264 bridge (raw H.264, no RTP)')
    parser.add_argument('--gz-topic', default='/camera', help='Gazebo image topic')
    parser.add_argument('--ip', default=os.getenv('GSTREAMER_UDP_HOST', '127.0.0.1'), help='Destination IP')
    parser.add_argument('--port', type=int, default=int(os.getenv('GSTREAMER_UDP_PORT', '5600')), help='Destination UDP port')
    parser.add_argument('--fps', type=int, default=30, help='Assumed frame rate for caps')
    parser.add_argument('--bitrate', type=int, default=1500, help='Target bitrate (kbps)')
    parser.add_argument('--encoder', choices=['x264', 'nvenc', 'auto'], default=os.getenv('GST_ENCODER', 'x264'), help='H.264 encoder to use')
    parser.add_argument('--publisher-address', help='Direct publisher address (bypasses discovery). Format: tcp://host:port')
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Handle 'auto' encoder selection
    if args.encoder == 'auto':
        if os.path.exists('/dev/nvidiactl'):
            args.encoder = 'nvenc'
        else:
            args.encoder = 'x264'

    bridge = GzToGStreamerBridge(args)
    bridge.run()


if __name__ == '__main__':
    main()

