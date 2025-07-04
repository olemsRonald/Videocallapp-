"""
OODA Video Call System - Video Capture Module
M2 Task: Capture webcam feed (with opencv-python)

This module handles real-time webcam capture using OpenCV with optimized performance
for at least 15 FPS as required by M2/M3 specifications.
"""

import cv2
import threading
import time
import logging
import queue
import numpy as np
from typing import Optional, Callable, Tuple
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class VideoConfig:
    """Video capture configuration"""
    width: int = 640
    height: int = 480
    fps: int = 30  # Target FPS (will be optimized to maintain at least 15 FPS)
    format: str = 'BGR'  # OpenCV default format
    codec: str = 'MJPG'  # MJPEG codec for better performance
    buffer_size: int = 2  # Small buffer for low latency

class VideoCapture:
    """
    Real-time video capture using OpenCV
    M2 Task: Capture webcam feed (with opencv-python)
    M2/M3 Task: Optimize framerate (at least 15 FPS)
    """
    
    def __init__(self, device_id: int = 0, config: Optional[VideoConfig] = None):
        self.device_id = device_id
        self.config = config or VideoConfig()
        
        # Video capture objects
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_capturing = False
        self.capture_thread: Optional[threading.Thread] = None
        
        # Frame management
        self.frame_queue = queue.Queue(maxsize=self.config.buffer_size)
        self.current_frame: Optional[np.ndarray] = None
        self.frame_callback: Optional[Callable[[np.ndarray], None]] = None
        
        # Performance monitoring
        self.frames_captured = 0
        self.start_time = None
        self.last_fps_check = 0
        self.actual_fps = 0.0
        
        # Frame processing optimization
        self.frame_skip_count = 0
        self.target_frame_interval = 1.0 / self.config.fps
        self.last_frame_time = 0
        
        logger.info(f"🎥 VideoCapture initialized: device {device_id}, target {self.config.fps} FPS")
    
    def get_available_cameras(self) -> list:
        """Get list of available camera devices"""
        cameras = []
        
        # Test up to 10 camera indices
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    cameras.append({
                        'id': i,
                        'name': f'Camera {i}',
                        'resolution': f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}"
                    })
                cap.release()
        
        logger.info(f"📹 Found {len(cameras)} available cameras")
        return cameras
    
    def start_capture(self, frame_callback: Optional[Callable[[np.ndarray], None]] = None) -> bool:
        """
        Start video capture
        M2 Task: Capture webcam feed (with opencv-python)
        """
        if self.is_capturing:
            logger.warning("Video capture already running")
            return True
        
        try:
            # Initialize camera
            self.cap = cv2.VideoCapture(self.device_id)
            
            if not self.cap.isOpened():
                logger.error(f"Failed to open camera {self.device_id}")
                return False
            
            # Configure camera settings for optimal performance
            self._configure_camera()
            
            # Set callback
            self.frame_callback = frame_callback
            
            # Start capture thread
            self.is_capturing = True
            self.start_time = time.time()
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()
            
            logger.info(f"✅ Video capture started: {self.config.width}x{self.config.height} @ {self.config.fps} FPS")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start video capture: {e}")
            self.cleanup()
            return False
    
    def _configure_camera(self):
        """Configure camera settings for optimal performance"""
        if not self.cap:
            return
        
        # Set resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        
        # Set FPS
        self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        
        # Set codec for better performance
        fourcc = cv2.VideoWriter_fourcc(*self.config.codec)
        self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        
        # Reduce buffer size for lower latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # Auto exposure and focus for better quality
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        
        # Log actual settings
        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        logger.info(f"📷 Camera configured: {actual_width}x{actual_height} @ {actual_fps} FPS")
    
    def _capture_loop(self):
        """
        Main capture loop with FPS optimization
        M2/M3 Task: Optimize framerate (at least 15 FPS)
        """
        logger.info("🎬 Video capture loop started")
        
        while self.is_capturing and self.cap:
            try:
                current_time = time.time()
                
                # Frame rate control - ensure we don't exceed target FPS
                time_since_last_frame = current_time - self.last_frame_time
                if time_since_last_frame < self.target_frame_interval:
                    time.sleep(0.001)  # Small sleep to prevent CPU spinning
                    continue
                
                # Capture frame
                ret, frame = self.cap.read()
                
                if not ret:
                    logger.warning("Failed to capture frame")
                    continue
                
                # Update timing
                self.last_frame_time = current_time
                self.frames_captured += 1
                
                # Store current frame
                self.current_frame = frame.copy()
                
                # Add to queue (non-blocking)
                try:
                    self.frame_queue.put_nowait(frame.copy())
                except queue.Full:
                    # Remove oldest frame and add new one
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put_nowait(frame.copy())
                    except queue.Empty:
                        pass
                
                # Call frame callback if provided
                if self.frame_callback:
                    try:
                        self.frame_callback(frame.copy())
                    except Exception as e:
                        logger.error(f"Frame callback error: {e}")
                
                # Update FPS statistics every second
                if current_time - self.last_fps_check >= 1.0:
                    self._update_fps_stats(current_time)
                
            except Exception as e:
                logger.error(f"Capture loop error: {e}")
                break
        
        logger.info("🎬 Video capture loop ended")
    
    def _update_fps_stats(self, current_time: float):
        """Update FPS statistics and optimize if needed"""
        if self.start_time:
            elapsed = current_time - self.start_time
            if elapsed > 0:
                self.actual_fps = self.frames_captured / elapsed
                
                # Log FPS every 5 seconds
                if int(current_time) % 5 == 0:
                    logger.info(f"📊 Video FPS: {self.actual_fps:.1f} (target: {self.config.fps})")
                
                # Optimize if FPS is too low (below 15 FPS requirement)
                if self.actual_fps < 15.0 and elapsed > 5.0:  # Give 5 seconds to stabilize
                    self._optimize_performance()
        
        self.last_fps_check = current_time
    
    def _optimize_performance(self):
        """
        Optimize performance to maintain at least 15 FPS
        M2/M3 Task: Optimize framerate (at least 15 FPS)
        """
        logger.warning(f"⚡ Optimizing performance: current FPS {self.actual_fps:.1f} < 15")
        
        # Reduce resolution if needed
        if self.config.width > 320:
            self.config.width = max(320, self.config.width // 2)
            self.config.height = max(240, self.config.height // 2)
            
            if self.cap:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            
            logger.info(f"📉 Reduced resolution to {self.config.width}x{self.config.height}")
        
        # Reduce target FPS slightly to allow for processing overhead
        if self.config.fps > 20:
            self.config.fps = max(20, self.config.fps - 5)
            self.target_frame_interval = 1.0 / self.config.fps
            
            if self.cap:
                self.cap.set(cv2.CAP_PROP_FPS, self.config.fps)
            
            logger.info(f"📉 Reduced target FPS to {self.config.fps}")
    
    def get_frame(self) -> Optional[np.ndarray]:
        """Get the latest captured frame"""
        return self.current_frame.copy() if self.current_frame is not None else None
    
    def get_frame_from_queue(self) -> Optional[np.ndarray]:
        """Get frame from queue (non-blocking)"""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def stop_capture(self):
        """Stop video capture"""
        if not self.is_capturing:
            return
        
        logger.info("🛑 Stopping video capture")
        self.is_capturing = False
        
        # Wait for capture thread to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
        
        self.cleanup()
        
        # Log final statistics
        if self.start_time:
            total_time = time.time() - self.start_time
            final_fps = self.frames_captured / total_time if total_time > 0 else 0
            logger.info(f"📊 Final stats: {self.frames_captured} frames, {final_fps:.1f} FPS avg")
    
    def cleanup(self):
        """Clean up resources"""
        if self.cap:
            self.cap.release()
            self.cap = None
        
        # Clear frame queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
        
        self.current_frame = None
        logger.info("🧹 Video capture cleanup completed")
    
    def get_capture_stats(self) -> dict:
        """Get capture statistics"""
        return {
            'is_capturing': self.is_capturing,
            'frames_captured': self.frames_captured,
            'actual_fps': self.actual_fps,
            'target_fps': self.config.fps,
            'resolution': f"{self.config.width}x{self.config.height}",
            'device_id': self.device_id,
            'queue_size': self.frame_queue.qsize(),
            'performance_ok': self.actual_fps >= 15.0
        }

# Demo/Test function
def demo_video_capture():
    """Demo function to test video capture"""
    print("🎥 OODA Video Capture Demo")
    print("=" * 40)
    
    capture = VideoCapture()
    
    # Get available cameras
    cameras = capture.get_available_cameras()
    print(f"Available cameras: {cameras}")
    
    def frame_callback(frame):
        # Display frame (for demo purposes)
        cv2.imshow('OODA Video Capture', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            capture.stop_capture()
    
    # Start capture
    if capture.start_capture(frame_callback):
        print("✅ Video capture started. Press 'q' to quit.")
        
        # Keep running until stopped
        try:
            while capture.is_capturing:
                time.sleep(0.1)
                stats = capture.get_capture_stats()
                if stats['frames_captured'] % 150 == 0:  # Print stats every ~5 seconds
                    print(f"📊 Stats: {stats['actual_fps']:.1f} FPS, {stats['frames_captured']} frames")
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
        
        capture.stop_capture()
        cv2.destroyAllWindows()
    else:
        print("❌ Failed to start video capture")

if __name__ == "__main__":
    demo_video_capture()
