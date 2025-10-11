#!/usr/bin/env python3
"""
Standalone YOLOv8 ONNX inference node.
Reads images directly from Gazebo via ZMQ (gz-transport).
Publishes detections over Zenoh as CDR-serialized vision_msgs/Detection2DArray.
"""
import argparse
import json
import os
import platform
import queue
import signal
import struct
import sys
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort
import zenoh

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from gz_transport_py import Node
    from gz.msgs.image_pb2 import Image
    from gz.msgs import image_pb2
except Exception as e:
    print("[YOLO] ERROR: gz-transport-py or gz-msgs not available.")
    print("Install gz-transport-py: cd gz-transport-py && pip install -e .")
    print("Install gz-msgs: cd gz-msgs-py && pip install -e .")
    raise


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
        self.gz_topic = args.gz_topic
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
        
        # Frame queue for processing
        self.frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=2)
        self._frame_count = 0
        self._last_frame_time = time.time()
        
        # Create visualization window if needed
        if self.visualize:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, 800, 600)
        
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
        
        # Respect GZ_PARTITION if set for discovery
        partition = os.getenv('GZ_PARTITION')
        if partition:
            print(f"[YOLO] Using GZ_PARTITION={partition}")
        
        # Create gz-transport node
        self.gz_node = Node(verbose=True)
        
        # Get manual publisher address if specified
        publisher_addr = args.publisher_address or os.getenv('GZ_PUBLISHER_ADDRESS')
        
        # Subscribe to Gazebo image topic
        ok = self.gz_node.subscribe(
            Image,
            self.gz_topic,
            self._on_gz_image,
            publisher_address=publisher_addr
        )
        if not ok:
            raise RuntimeError(f"Failed to subscribe to Gazebo topic: {self.gz_topic}")
        
        print(f"[YOLO] Subscribed to Gazebo topic: {self.gz_topic}")
        if publisher_addr:
            print(f"[YOLO] Direct connection to: {publisher_addr}")
        print("[YOLO] YOLO inference started.")
    
    def _on_gz_image(self, msg: Image) -> None:
        """Callback for Gazebo image messages."""
        try:
            # Convert Gazebo Image message to numpy array
            # Gazebo images are typically RGB format
            # Debug: print first time to see format
            if not hasattr(self, '_printed_format'):
                print(f"[YOLO] Image format: {msg.pixel_format_type} (RGB_INT8={image_pb2.RGB_INT8}, BGR_INT8={image_pb2.BGR_INT8})")
                print(f"[YOLO] Image size: {msg.width}x{msg.height}, data: {len(msg.data)} bytes")
                self._printed_format = True
            
            if msg.pixel_format_type == image_pb2.RGB_INT8:
                # RGB8 format
                img_array = np.frombuffer(msg.data, dtype=np.uint8)
                img_array = img_array.reshape((msg.height, msg.width, 3))
                # Convert RGB to BGR for OpenCV
                frame = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            elif msg.pixel_format_type == image_pb2.BGR_INT8:
                # Already BGR
                img_array = np.frombuffer(msg.data, dtype=np.uint8)
                frame = img_array.reshape((msg.height, msg.width, 3))
            else:
                print(f"[YOLO] WARNING: Unsupported pixel format: {msg.pixel_format_type}")
                return
            
            # Try to add to queue (non-blocking)
            try:
                self.frame_queue.put(frame, block=False)
                self._frame_count += 1
                
                # Print frame rate stats every 120 frames
                if self._frame_count % 120 == 0:
                    now = time.time()
                    elapsed = now - self._last_frame_time
                    fps = 120 / elapsed if elapsed > 0 else 0
                    print(f"[YOLO] Frame Reception Rate: {fps:.2f} FPS")
                    self._last_frame_time = now
            except queue.Full:
                # Queue is full, drop frame (inference is slower than input)
                pass
                
        except Exception as e:
            print(f"[YOLO] ERROR processing Gazebo image: {e}")
    
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
    
    def _watchdog_check(self) -> None:
        """Check if frames are being received and warn if not."""
        if self._frame_count == 0:
            print("[YOLO] WARNING: No frames received from Gazebo yet.")
            print("  Troubleshooting:")
            print(f"   - Verify publisher visible: gz topic -i -t {self.gz_topic}")
            print(f"   - Echo messages: gz topic -e -t {self.gz_topic}")
            print("   - Partitions: export GZ_PARTITION to match simulator if set")
            print("   - Check that Gazebo and this script run under same user env")
            print("   - Ensure gz-transport-py is properly installed")
    
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
        
        # Set up signal handlers
        def _stop_handler(_sig, _frm):
            print("\n[YOLO] Shutting down...")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, _stop_handler)
        signal.signal(signal.SIGTERM, _stop_handler)
        
        # Schedule watchdog check
        watchdog_timer = threading.Timer(5.0, self._watchdog_check)
        watchdog_timer.daemon = True
        watchdog_timer.start()
        
        try:
            while True:
                try:
                    frame = self.frame_queue.get(timeout=1.0)
                except queue.Empty:
                    print('[YOLO] WARNING: Frame queue empty - no frames received in 1 second')
                    print('[YOLO] Troubleshooting steps:')
                    print(f'  1. Verify topic is active: gz topic -i -t {self.gz_topic}')
                    print(f'  2. Echo messages: gz topic -e -t {self.gz_topic}')
                    print(f'  3. Check GZ_PARTITION environment variable')
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
            if self.visualize:
                cv2.destroyAllWindows()
            self.zenoh_session.close()
            self.gz_node.shutdown()
    
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
        description='YOLOv8 ONNX inference from Gazebo images with Zenoh publishing'
    )
    parser.add_argument('--gz-topic', required=True, help='Gazebo image topic (e.g., /camera)')
    parser.add_argument('--model', type=str, required=True, help='Path to ONNX model')
    parser.add_argument('--classes', type=str, required=True, help='Path to COCO classes JSON')
    parser.add_argument('--input-size', type=int, default=640, help='Model input size')
    parser.add_argument('--conf-threshold', type=float, default=0.5, help='Confidence threshold')
    parser.add_argument('--nms-threshold', type=float, default=0.45, help='NMS threshold')
    parser.add_argument('--zenoh-topic', type=str, default='rt/detections', help='Zenoh topic for detections')
    parser.add_argument('--zenoh-mode', type=str, default='peer', help='Zenoh mode: peer or client')
    parser.add_argument('--zenoh-connect', type=str, default='', help='Zenoh router endpoint (e.g., tcp/42.42.1.1:7447)')
    parser.add_argument('--visualize', action='store_true', help='Show visualization window with detections')
    parser.add_argument('--publisher-address', help='Direct publisher address (bypasses discovery). Format: tcp://host:port')
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    node = YoloPublisher(args)
    node.run()


if __name__ == '__main__':
    main()

