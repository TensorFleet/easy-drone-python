#!/usr/bin/env python3
"""
Standalone YOLOv8 ONNX inference node.
Publishes detections over Zenoh as CDR-serialized vision_msgs/Detection2DArray.
"""
import argparse
import json
import os
import platform
import queue
import struct
import threading
import time
from typing import Optional, Tuple

import av
import cv2
import numpy as np
import onnxruntime as ort
import zenoh


def convert_xywh_to_xyxy(xywh_array: np.ndarray) -> np.ndarray:
    """Convert bounding boxes from [x_center, y_center, w, h] to [x1, y1, x2, y2]."""
    coord = np.copy(xywh_array)
    coord[..., 0] = xywh_array[..., 0] - xywh_array[..., 2] / 2
    coord[..., 1] = xywh_array[..., 1] - xywh_array[..., 3] / 2
    coord[..., 2] = xywh_array[..., 0] + xywh_array[..., 2] / 2
    coord[..., 3] = xywh_array[..., 1] + xywh_array[..., 3] / 2
    return coord




def serialize_detection2d_array_cdr(
    detections: list,
    frame_id: str = "camera_frame",
    sec: int = 0,
    nanosec: int = 0
) -> bytes:
    """
    Serialize vision_msgs/Detection2DArray to CDR (Common Data Representation).
    
    Message structure (simplified for YOLO use case):
    - std_msgs/Header header
      - builtin_interfaces/Time stamp (sec: int32, nanosec: uint32)
      - string frame_id
    - Detection2D[] detections
      - std_msgs/Header header (omitted for brevity, using empty)
      - ObjectHypothesisWithPose[] results
        - ObjectHypothesis hypothesis
          - string class_id
          - float64 score
        - geometry_msgs/PoseWithCovariance pose (omitted)
      - BoundingBox2D bbox
        - geometry_msgs/Pose2D center
          - float64 x, y, theta
        - float64 size_x, size_y
      - string id
    
    This is a minimal CDR serialization for compatibility with ROS 2 Humble.
    """
    buf = bytearray()
    
    # CDR encapsulation header (0x00 = Big Endian, 0x01 = Little Endian)
    buf.extend(b'\x00\x01\x00\x00')  # Little endian CDR
    
    # Header: stamp (sec: i32, nanosec: u32)
    buf.extend(struct.pack('<i', sec))
    buf.extend(struct.pack('<I', nanosec))
    
    # Header: frame_id (string: u32 length + data + padding)
    frame_id_bytes = frame_id.encode('utf-8')
    buf.extend(struct.pack('<I', len(frame_id_bytes) + 1))  # +1 for null terminator
    buf.extend(frame_id_bytes)
    buf.append(0)  # null terminator
    # Align to 4-byte boundary
    while len(buf) % 4 != 0:
        buf.append(0)
    
    # detections array length
    buf.extend(struct.pack('<I', len(detections)))
    
    for det in detections:
        # Detection2D header (empty for simplicity: sec=0, nanosec=0, frame_id="")
        buf.extend(struct.pack('<i', 0))  # sec
        buf.extend(struct.pack('<I', 0))  # nanosec
        buf.extend(struct.pack('<I', 1))  # frame_id length (empty string = 1 for null)
        buf.append(0)  # null terminator
        while len(buf) % 4 != 0:
            buf.append(0)
        
        # results array (ObjectHypothesisWithPose[])
        buf.extend(struct.pack('<I', 1))  # 1 result per detection
        
        # ObjectHypothesis: class_id (string)
        class_id_bytes = det['class_id'].encode('utf-8')
        buf.extend(struct.pack('<I', len(class_id_bytes) + 1))
        buf.extend(class_id_bytes)
        buf.append(0)
        while len(buf) % 4 != 0:
            buf.append(0)
        
        # ObjectHypothesis: score (float64)
        buf.extend(struct.pack('<d', det['score']))
        
        # PoseWithCovariance (36 doubles for pose + covariance, all zeros for simplicity)
        buf.extend(b'\x00' * (7 * 8 + 36 * 8))  # pose (x, y, z, qx, qy, qz, qw) + covariance
        
        # BoundingBox2D: center (Pose2D: x, y, theta)
        buf.extend(struct.pack('<d', det['bbox_center_x']))
        buf.extend(struct.pack('<d', det['bbox_center_y']))
        buf.extend(struct.pack('<d', 0.0))  # theta
        
        # BoundingBox2D: size_x, size_y
        buf.extend(struct.pack('<d', det['bbox_size_x']))
        buf.extend(struct.pack('<d', det['bbox_size_y']))
        
        # id (string)
        id_bytes = det['id'].encode('utf-8')
        buf.extend(struct.pack('<I', len(id_bytes) + 1))
        buf.extend(id_bytes)
        buf.append(0)
        while len(buf) % 4 != 0:
            buf.append(0)
    
    return bytes(buf)


class YoloPublisher:
    """Standalone YOLO inference node publishing over Zenoh."""
    
    def __init__(self, args: argparse.Namespace):
        self.architecture = platform.machine()
        self.input_is_gstreamer = args.use_gstreamer
        self.udp_port = args.udp_port
        self.video_path = args.video
        self.model_path = args.model
        self.classes_path = args.classes
        self.input_size = args.input_size
        self.conf_threshold = args.conf_threshold
        self.nms_threshold = args.nms_threshold
        self.zenoh_topic = args.zenoh_topic
        self.visualize = args.visualize
        self.window_name = "YOLO Inference"
        
        # Load COCO classes
        with open(self.classes_path, 'r') as f:
            class_map = json.load(f)
            self.class_index_to_name = {int(k): v for k, v in class_map.items()}
        
        # Generate colors for visualization
        import matplotlib.pyplot as plt
        colors_rgba = plt.cm.hsv(np.linspace(0, 1, len(self.class_index_to_name)))
        self.colors = (colors_rgba[:, [2, 1, 0]] * 255).astype(np.uint8)
        
        # Create ONNX session
        self.session = self._create_onnx_session(self.model_path)
        self.input_name = self.session.get_inputs()[0].name
        print(f"[YOLO] Execution providers: {self.session.get_providers()}")
        
        # Open video capture with retry logic
        self.frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=2)
        self._is_running = threading.Event()
        self._is_running.set()
        self._capture: Optional[cv2.VideoCapture] = None
        self._av_container: Optional[av.container.InputContainer] = None
        self._open_video_capture()
        
        # Create visualization window if needed
        if self.visualize:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, 800, 600)
        
        # Start frame capture thread
        self._capture_thread = threading.Thread(target=self._frame_reader_loop, daemon=True)
        self._capture_thread.start()
        
        # Initialize Zenoh session
        zenoh_config = zenoh.Config()
        if args.zenoh_mode:
            zenoh_config.insert_json5("mode", f'"{args.zenoh_mode}"')
        if args.zenoh_connect:
            zenoh_config.insert_json5("connect/endpoints", f'["{args.zenoh_connect}"]')
        self.zenoh_session = zenoh.open(zenoh_config)
        self.zenoh_pub = self.zenoh_session.declare_publisher(
            self.zenoh_topic,
            encoding=zenoh.Encoding.ZENOH_BYTES
        )
        print(f"[YOLO] Zenoh publisher ready on topic: {self.zenoh_topic}")
        print("[YOLO] YOLO inference started.")
    
    def _create_onnx_session(self, model_path: str) -> ort.InferenceSession:
        """Create ONNX Runtime session with appropriate execution provider."""
        if self.architecture == 'x86_64':
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        elif self.architecture == 'aarch64':
            cache_path = os.path.expanduser("~/.cache/tensorrt")
            os.makedirs(cache_path, exist_ok=True)
            providers = [
                ("TensorrtExecutionProvider", {
                    'trt_engine_cache_enable': True,
                    'trt_engine_cache_path': cache_path,
                }),
                "CPUExecutionProvider"
            ]
        else:
            providers = ["CPUExecutionProvider"]
        return ort.InferenceSession(model_path, providers=providers)
    
    def _open_video_capture(self) -> None:
        """Open video capture (PyAV for UDP or OpenCV for file) with retry logic."""
        if self.input_is_gstreamer:
            # Use PyAV for UDP H264 streams (much more reliable than OpenCV+GStreamer)
            url = f"udp://127.0.0.1:{self.udp_port}?fifo_size=1000000&overrun_nonfatal=1"
            print(f"[YOLO] Attempting to open UDP stream on port {self.udp_port} using PyAV (FFmpeg)...")
            print(f"[YOLO] Stream URL: {url}")
            print(f"[YOLO] Waiting for UDP data (this will timeout if no stream is available)...")
            
            # Try to open with retries
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # FFmpeg options to prevent hanging and add timeout
                    container = av.open(url, options={
                        'timeout': '5000000',  # 5 second timeout in microseconds
                        'max_delay': '500000',  # 0.5 second max delay
                        'fflags': 'nobuffer',  # Minimize buffering
                        'flags': 'low_delay',  # Low latency mode
                        'analyzeduration': '1000000',  # 1 second to analyze stream
                        'probesize': '1000000',  # 1MB probe size
                    }, timeout=5.0)  # PyAV timeout in seconds
                    
                    # Test if we can get a stream
                    if container.streams.video:
                        print(f"[YOLO] UDP stream opened successfully using PyAV!")
                        print(f"[YOLO] Video codec: {container.streams.video[0].codec_context.name}")
                        self._av_container = container
                        return
                    else:
                        print(f"[YOLO] No video stream found in container")
                        container.close()
                except av.error.TimeoutError:
                    print(f"[YOLO] Attempt {attempt + 1}/{max_retries}: Timeout waiting for UDP stream")
                    if attempt < max_retries - 1:
                        print(f"[YOLO] Retrying in 2s...")
                        time.sleep(2)
                except Exception as e:
                    print(f"[YOLO] Attempt {attempt + 1}/{max_retries} failed: {e}")
                    if attempt < max_retries - 1:
                        print(f"[YOLO] Retrying in 2s...")
                        time.sleep(2)
            
            print(f"\n[YOLO] ERROR: Failed to open UDP stream after {max_retries} attempts")
            print("\n[YOLO] Common causes:")
            print(f"  - No video stream is being sent to port {self.udp_port}")
            print(f"  - Video source (drone, simulator, etc.) is not running")
            print(f"  - Firewall blocking UDP port {self.udp_port}")
            print(f"  - Wrong port number (check video source configuration)")
            print("\n[YOLO] Troubleshooting steps:")
            print(f"  1. Verify video source is running and sending UDP stream")
            print(f"")
            print(f"  2. Test if UDP packets are arriving:")
            print(f"     sudo tcpdump -i lo udp port {self.udp_port} -c 10")
            print(f"     (Install with: sudo apt-get install tcpdump)")
            print(f"     Should show packets if stream is active")
            print(f"")
            print(f"  3. Test stream with ffplay:")
            print(f"     ffplay -fflags nobuffer -flags low_delay udp://127.0.0.1:{self.udp_port}")
            print(f"     (Install with: sudo apt-get install ffmpeg)")
            print(f"")
            print(f"  4. Test with GStreamer:")
            print(f"     gst-launch-1.0 udpsrc port={self.udp_port} ! fakesink dump=true")
            print(f"     (Should show 'chain' messages if receiving data)")
            print(f"")
            print(f"  5. Check network statistics:")
            print(f"     netstat -su | grep -i udp")
            print(f"     (Look for UDP receive errors or dropped packets)")
            raise RuntimeError("Failed to open UDP video source")
        else:
            # Use OpenCV for video files
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                print(f"\n[YOLO] ERROR: Failed to open video file: {self.video_path}")
                print("\n[YOLO] Troubleshooting steps:")
                print(f"  1. Verify the file exists:")
                print(f"     ls -lh {self.video_path}")
                print(f"")
                print(f"  2. Check file format and codec:")
                print(f"     ffprobe -v error -show_format -show_streams {self.video_path}")
                print(f"     (Install with: sudo apt-get install ffmpeg)")
                print(f"")
                print(f"  3. Try playing with ffplay:")
                print(f"     ffplay {self.video_path}")
                raise RuntimeError(f"Failed to open video file: {self.video_path}")
            print(f"[YOLO] Video file opened successfully: {self.video_path}")
            self._capture = cap
    
    def _frame_reader_loop(self) -> None:
        """Background thread to continuously read frames."""
        frames_received = 0
        start_time = time.time()
        consecutive_failures = 0
        MAX_FAILURES = 30  # ~3 seconds at 10ms sleep
        
        while self._is_running.is_set():
            frame = None
            ok = False
            
            try:
                if self.input_is_gstreamer:
                    # PyAV-based UDP stream reading
                    if self._av_container is None:
                        time.sleep(0.01)
                        continue
                    
                    try:
                        for packet in self._av_container.demux(video=0):
                            for av_frame in packet.decode():
                                # Convert PyAV frame to numpy array (BGR format for OpenCV compatibility)
                                frame = av_frame.to_ndarray(format='bgr24')
                                ok = True
                                break
                            if ok:
                                break
                    except av.error.EOFError:
                        print("[YOLO] Stream ended (EOF)")
                        ok = False
                    except Exception as e:
                        print(f"[YOLO] Error reading from PyAV stream: {e}")
                        ok = False
                else:
                    # OpenCV-based file reading
                    if self._capture is None:
                        time.sleep(0.01)
                        continue
                    ok, frame = self._capture.read()
                
                if not ok or frame is None:
                    if not self.input_is_gstreamer:
                        # Video file ended, loop back to start
                        if self._capture is not None:
                            self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            print("[YOLO] Video file ended, looping...")
                        time.sleep(0.01)
                        continue

                    # UDP stream: track failures and attempt reconnection
                    consecutive_failures += 1
                    if consecutive_failures > MAX_FAILURES:
                        print("[YOLO] Stream lost, attempting reconnection...")
                        try:
                            # Release current container and try to reopen
                            if self._av_container is not None:
                                self._av_container.close()
                                self._av_container = None
                        except Exception:
                            pass
                        try:
                            self._open_video_capture()
                            consecutive_failures = 0
                            print("[YOLO] Reconnected successfully!")
                        except Exception as e:
                            print(f"[YOLO] ERROR: Reconnection failed: {e}")
                            print("\n[YOLO] Troubleshooting steps:")
                            print(f"  1. Check if stream is still available:")
                            print(f"     ffplay udp://127.0.0.1:{self.udp_port}")
                            print(f"")
                            print(f"  2. Check system logs for network issues:")
                            print(f"     dmesg | tail -n 50")
                    time.sleep(0.01)
                    continue
                
                # Reset on successful read
                consecutive_failures = 0
                try:
                    self.frame_queue.put(frame, timeout=0.05)
                    frames_received += 1
                except queue.Full:
                    pass
                if frames_received and frames_received % 120 == 0:
                    elapsed = time.time() - start_time
                    fps = frames_received / elapsed if elapsed > 0 else 0.0
                    print(f"[YOLO] Frame Reception Rate: {fps:.2f} FPS")
                    frames_received = 0
                    start_time = time.time()
                    
            except Exception as e:
                print(f"[YOLO] Unexpected error in frame reader loop: {e}")
                time.sleep(0.01)
    
    def _preprocess(self, bgr_frame: np.ndarray) -> np.ndarray:
        """Preprocess frame for YOLO inference."""
        img = cv2.resize(bgr_frame, (self.input_size, self.input_size))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.transpose(2, 0, 1).astype(np.float32) / 255.0
        img = np.expand_dims(img, axis=0)
        return img
    
    def _postprocess(
        self, preds: np.ndarray, orig_w: int, orig_h: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Post-process YOLO predictions (NMS, scaling)."""
        boxes = preds[:, :4]
        cls_scores = preds[:, 4:]
        cls_ids = np.argmax(cls_scores, axis=1)
        confidences = np.max(cls_scores, axis=1)
        
        mask = confidences > self.conf_threshold
        boxes_masked = boxes[mask]
        confs_masked = confidences[mask]
        cls_ids_masked = cls_ids[mask]
        
        if len(boxes_masked) == 0:
            return np.array([]), np.array([]), np.array([])
        
        boxes_for_nms = convert_xywh_to_xyxy(boxes_masked)
        indices = cv2.dnn.NMSBoxes(
            boxes_for_nms.tolist(),
            confs_masked.tolist(),
            self.conf_threshold,
            self.nms_threshold
        )
        
        final_boxes = boxes_masked[indices]
        final_scores = confs_masked[indices]
        final_classes = cls_ids_masked[indices]
        
        final_boxes = convert_xywh_to_xyxy(final_boxes)
        scale_w, scale_h = orig_w / self.input_size, orig_h / self.input_size
        final_boxes[:, [0, 2]] *= scale_w
        final_boxes[:, [1, 3]] *= scale_h
        return final_boxes, final_scores, final_classes
    
    def _publish_zenoh(
        self, boxes: np.ndarray, scores: np.ndarray, classes: np.ndarray
    ) -> None:
        """Publish detections over Zenoh as CDR-serialized Detection2DArray."""
        detections = []
        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes[i]
            class_name = self.class_index_to_name[int(classes[i])]
            detections.append({
                'class_id': class_name,
                'score': float(scores[i]),
                'bbox_center_x': float((x1 + x2) / 2.0),
                'bbox_center_y': float((y1 + y2) / 2.0),
                'bbox_size_x': float(x2 - x1),
                'bbox_size_y': float(y2 - y1),
                'id': class_name,
            })
        
        # Serialize and publish
        cdr_payload = serialize_detection2d_array_cdr(
            detections,
            frame_id="camera_frame",
            sec=int(time.time()),
            nanosec=int((time.time() % 1) * 1e9)
        )
        self.zenoh_pub.put(cdr_payload)
    
    def run(self) -> None:
        """Main inference loop."""
        inferences = 0
        start_time = time.time()
        try:
            while True:
                try:
                    frame = self.frame_queue.get(timeout=1.0)
                except queue.Empty:
                    print('[YOLO] WARNING: Frame queue empty - no frames received in 1 second')
                    if self.input_is_gstreamer:
                        print('[YOLO] Troubleshooting steps:')
                        print(f'  1. Verify stream is active:')
                        print(f'     gst-launch-1.0 udpsrc port={self.udp_port} ! fakesink dump=true')
                    else:
                        print(f'[YOLO] Troubleshooting steps:')
                        print(f'  1. Check video file is accessible:')
                        print(f'     ls -lh {self.video_path}')
                        print(f'  2. Check frame reader thread status')
                    continue
                
                h0, w0 = frame.shape[:2]
                inp = self._preprocess(frame)
                outputs = self.session.run(None, {self.input_name: inp})
                preds = np.squeeze(outputs[0]).transpose()
                boxes, scores, classes = self._postprocess(preds, w0, h0)
                
                inferences += 1
                if inferences % 120 == 0:
                    elapsed = time.time() - start_time
                    fps = inferences / elapsed if elapsed > 0 else 0.0
                    print(f"[YOLO] Inference Rate: {fps:.2f} FPS")
                    inferences = 0
                    start_time = time.time()
                
                self._publish_zenoh(boxes, scores, classes)
                
                # Visualize if enabled
                if self.visualize:
                    self._draw_detections(frame, boxes, scores, classes)
                    cv2.imshow(self.window_name, frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("\n[YOLO] 'q' pressed, shutting down...")
                        break
        except KeyboardInterrupt:
            print("\n[YOLO] Shutting down...")
        finally:
            self._is_running.clear()
            self._capture_thread.join(timeout=1.0)
            if self._capture is not None:
                self._capture.release()
            if self._av_container is not None:
                self._av_container.close()
            if self.visualize:
                cv2.destroyAllWindows()
            self.zenoh_session.close()
    
    def _draw_detections(
        self, frame: np.ndarray, boxes: np.ndarray, scores: np.ndarray, classes: np.ndarray
    ) -> None:
        """Draw bounding boxes and labels on frame."""
        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes[i].astype(int)
            conf = scores[i]
            class_id = int(classes[i])
            class_name = self.class_index_to_name[class_id]
            color = tuple(self.colors[class_id, [2, 1, 0]].tolist())
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{class_name} {conf:.2f}", (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Standalone YOLOv8 ONNX inference with Zenoh publishing'
    )
    parser.add_argument('--model', type=str, default='yolov8n.onnx', help='Path to ONNX model')
    parser.add_argument('--classes', type=str, default='coco.json', help='Path to COCO classes JSON')
    parser.add_argument('--input-size', type=int, default=640, help='Model input size')
    parser.add_argument('--conf-threshold', type=float, default=0.5, help='Confidence threshold')
    parser.add_argument('--nms-threshold', type=float, default=0.45, help='NMS threshold')
    parser.add_argument('--use-gstreamer', action='store_true', help='Use GStreamer UDP H264')
    parser.add_argument('--udp-port', type=int, default=5600, help='UDP port for GStreamer')
    parser.add_argument('--video', type=str, default='sample.mp4', help='Video file (if not GStreamer)')
    parser.add_argument('--zenoh-topic', type=str, default='rt/detections', help='Zenoh topic for detections')
    parser.add_argument('--zenoh-mode', type=str, default='peer', help='Zenoh mode: peer or client')
    parser.add_argument('--zenoh-connect', type=str, default='', help='Zenoh router endpoint (e.g., tcp/42.42.1.1:7447)')
    parser.add_argument('--visualize', action='store_true', help='Show visualization window with detections')
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    node = YoloPublisher(args)
    node.run()


if __name__ == '__main__':
    main()

