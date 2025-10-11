#!/usr/bin/env python3
"""
Alternative YOLO implementation using OpenCV's FFMPEG backend instead of PyAV.
This may be more reliable for some UDP stream formats.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the main image_yolo module
from image_yolo import *

class YoloPublisherOpenCVFFMPEG(YoloPublisher):
    """YOLO publisher using OpenCV's FFMPEG backend for UDP streams."""
    
    def _open_video_capture(self) -> None:
        """Open video capture using OpenCV's FFMPEG backend."""
        if self.input_is_gstreamer:
            # Use OpenCV with FFMPEG backend for UDP streams
            url = f"udp://127.0.0.1:{self.udp_port}"
            print(f"[YOLO] Attempting to open UDP stream on port {self.udp_port} using OpenCV+FFMPEG...")
            print(f"[YOLO] Stream URL: {url}")
            
            # Set FFMPEG-specific environment variables
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp|fflags;nobuffer|flags;low_delay'
            
            max_retries = 3
            for attempt in range(max_retries):
                print(f"[YOLO] Attempt {attempt + 1}/{max_retries}...")
                
                try:
                    # Open with CAP_FFMPEG backend
                    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                    
                    # Wait a moment for stream to initialize
                    time.sleep(1)
                    
                    # Try to read a test frame
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            print(f"[YOLO] UDP stream opened successfully using OpenCV+FFMPEG!")
                            print(f"[YOLO] Frame size: {frame.shape}")
                            self._capture = cap
                            return
                        else:
                            print(f"[YOLO] Stream opened but could not read frame")
                            cap.release()
                    else:
                        print(f"[YOLO] Could not open stream")
                        
                except Exception as e:
                    print(f"[YOLO] Error: {e}")
                
                if attempt < max_retries - 1:
                    print(f"[YOLO] Retrying in 2s...")
                    time.sleep(2)
            
            print(f"\n[YOLO] ERROR: Failed to open UDP stream after {max_retries} attempts")
            print("\n[YOLO] Troubleshooting:")
            print(f"  1. Test with ffplay:")
            print(f"     ffplay -fflags nobuffer udp://127.0.0.1:{self.udp_port}")
            print(f"")
            print(f"  2. Check OpenCV build info:")
            print(f"     python3 -c 'import cv2; print(cv2.getBuildInformation())'")
            raise RuntimeError("Failed to open UDP video source")
        else:
            # Use parent class method for file playback
            super()._open_video_capture()
    
    def _frame_reader_loop(self) -> None:
        """Simplified frame reader for OpenCV."""
        frames_received = 0
        start_time = time.time()
        consecutive_failures = 0
        MAX_FAILURES = 30
        
        while self._is_running.is_set():
            if self._capture is None:
                time.sleep(0.01)
                continue
            
            ok, frame = self._capture.read()
            
            if not ok or frame is None:
                if not self.input_is_gstreamer:
                    # Video file ended, loop back
                    self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    print("[YOLO] Video file ended, looping...")
                    time.sleep(0.01)
                    continue
                
                # UDP stream failure
                consecutive_failures += 1
                if consecutive_failures > MAX_FAILURES:
                    print("[YOLO] Stream lost, attempting reconnection...")
                    try:
                        if self._capture is not None:
                            self._capture.release()
                            self._capture = None
                    except Exception:
                        pass
                    try:
                        self._open_video_capture()
                        consecutive_failures = 0
                        print("[YOLO] Reconnected successfully!")
                    except Exception as e:
                        print(f"[YOLO] Reconnection failed: {e}")
                time.sleep(0.01)
                continue
            
            # Successful read
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


def main() -> None:
    """Entry point using OpenCV+FFMPEG backend."""
    args = parse_args()
    print("[YOLO] Using OpenCV+FFMPEG backend (alternative to PyAV)")
    node = YoloPublisherOpenCVFFMPEG(args)
    node.run()


if __name__ == '__main__':
    main()

