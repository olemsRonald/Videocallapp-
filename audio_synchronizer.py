"""
M2 Task: Ensure real-time synchronization
OODA Audio Call System - Audio Synchronization Module

This module handles real-time audio synchronization between capture, transmission,
reception, and playback to minimize latency and ensure smooth audio communication.
"""

import time
import threading
import queue
import logging
import numpy as np
from typing import Optional, List, Tuple, Callable
from collections import deque
import statistics

logger = logging.getLogger(__name__)

class AudioSynchronizer:
    """
    Real-time audio synchronization manager
    
    Features:
    - Adaptive buffering based on network conditions
    - Latency measurement and compensation
    - Jitter detection and smoothing
    - Clock synchronization between peers
    - Audio quality monitoring and adjustment
    """
    
    def __init__(self,
                 target_latency_ms: float = 50.0,
                 max_latency_ms: float = 200.0,
                 min_buffer_size: int = 3,
                 max_buffer_size: int = 20,
                 jitter_threshold_ms: float = 10.0):
        """
        Initialize audio synchronizer
        
        Args:
            target_latency_ms: Target end-to-end latency in milliseconds
            max_latency_ms: Maximum acceptable latency in milliseconds
            min_buffer_size: Minimum buffer size in audio chunks
            max_buffer_size: Maximum buffer size in audio chunks
            jitter_threshold_ms: Jitter threshold for buffer adjustment
        """
        self.target_latency_ms = target_latency_ms
        self.max_latency_ms = max_latency_ms
        self.min_buffer_size = min_buffer_size
        self.max_buffer_size = max_buffer_size
        self.jitter_threshold_ms = jitter_threshold_ms
        
        # Synchronization state
        self.is_active = False
        self.sync_thread = None
        
        # Timing measurements
        self.latency_samples = deque(maxlen=100)
        self.jitter_samples = deque(maxlen=50)
        self.clock_offset = 0.0  # Offset between local and remote clocks
        
        # Buffer management
        self.current_buffer_size = (min_buffer_size + max_buffer_size) // 2
        self.buffer_adjustment_lock = threading.Lock()
        
        # Statistics
        self.sync_adjustments = 0
        self.buffer_underruns = 0
        self.buffer_overruns = 0
        self.quality_degradations = 0
        
        # Callbacks for buffer size changes
        self.buffer_size_callback: Optional[Callable] = None
        
        # Audio quality metrics
        self.audio_quality_samples = deque(maxlen=50)
        self.packet_loss_samples = deque(maxlen=20)
        
        logger.info(f"AudioSynchronizer initialized: target={target_latency_ms}ms, buffer={min_buffer_size}-{max_buffer_size}")
    
    def set_buffer_size_callback(self, callback: Callable[[int], None]):
        """
        Set callback for buffer size changes
        
        Args:
            callback: Function that takes new buffer size as parameter
        """
        self.buffer_size_callback = callback
        logger.info("Buffer size callback set")
    
    def add_latency_measurement(self, capture_time: float, playback_time: float):
        """
        Add latency measurement
        
        Args:
            capture_time: Timestamp when audio was captured
            playback_time: Timestamp when audio was played
        """
        latency_ms = (playback_time - capture_time) * 1000
        
        with self.buffer_adjustment_lock:
            self.latency_samples.append(latency_ms)
            
            # Calculate jitter if we have previous samples
            if len(self.latency_samples) >= 2:
                jitter_ms = abs(latency_ms - self.latency_samples[-2])
                self.jitter_samples.append(jitter_ms)
    
    def add_packet_loss_measurement(self, loss_rate: float):
        """
        Add packet loss measurement
        
        Args:
            loss_rate: Packet loss rate as percentage (0-100)
        """
        self.packet_loss_samples.append(loss_rate)
    
    def add_audio_quality_measurement(self, quality_score: float):
        """
        Add audio quality measurement
        
        Args:
            quality_score: Audio quality score (0-100, higher is better)
        """
        self.audio_quality_samples.append(quality_score)
    
    def get_current_latency(self) -> float:
        """Get current average latency in milliseconds"""
        if not self.latency_samples:
            return 0.0
        return statistics.mean(self.latency_samples)
    
    def get_current_jitter(self) -> float:
        """Get current average jitter in milliseconds"""
        if not self.jitter_samples:
            return 0.0
        return statistics.mean(self.jitter_samples)
    
    def get_current_packet_loss(self) -> float:
        """Get current average packet loss rate"""
        if not self.packet_loss_samples:
            return 0.0
        return statistics.mean(self.packet_loss_samples)
    
    def get_current_audio_quality(self) -> float:
        """Get current average audio quality score"""
        if not self.audio_quality_samples:
            return 100.0  # Assume good quality if no measurements
        return statistics.mean(self.audio_quality_samples)
    
    def _calculate_optimal_buffer_size(self) -> int:
        """Calculate optimal buffer size based on current conditions"""
        current_latency = self.get_current_latency()
        current_jitter = self.get_current_jitter()
        packet_loss = self.get_current_packet_loss()
        
        # Start with current buffer size
        optimal_size = self.current_buffer_size
        
        # Adjust based on latency
        if current_latency > self.max_latency_ms:
            # Latency too high, reduce buffer
            optimal_size = max(self.min_buffer_size, optimal_size - 2)
        elif current_latency < self.target_latency_ms * 0.5:
            # Latency very low, can increase buffer for stability
            optimal_size = min(self.max_buffer_size, optimal_size + 1)
        
        # Adjust based on jitter
        if current_jitter > self.jitter_threshold_ms:
            # High jitter, increase buffer for stability
            optimal_size = min(self.max_buffer_size, optimal_size + 1)
        
        # Adjust based on packet loss
        if packet_loss > 5.0:  # More than 5% packet loss
            # High packet loss, increase buffer
            optimal_size = min(self.max_buffer_size, optimal_size + 2)
        elif packet_loss < 1.0:  # Less than 1% packet loss
            # Low packet loss, can reduce buffer
            optimal_size = max(self.min_buffer_size, optimal_size - 1)
        
        return optimal_size
    
    def _adjust_buffer_size(self):
        """Adjust buffer size based on current conditions"""
        optimal_size = self._calculate_optimal_buffer_size()
        
        with self.buffer_adjustment_lock:
            if optimal_size != self.current_buffer_size:
                old_size = self.current_buffer_size
                self.current_buffer_size = optimal_size
                self.sync_adjustments += 1
                
                logger.info(f"Buffer size adjusted: {old_size} -> {optimal_size}")
                
                # Notify callback if set
                if self.buffer_size_callback:
                    try:
                        self.buffer_size_callback(optimal_size)
                    except Exception as e:
                        logger.error(f"Buffer size callback error: {e}")
    
    def _detect_quality_issues(self) -> List[str]:
        """Detect audio quality issues"""
        issues = []
        
        current_latency = self.get_current_latency()
        current_jitter = self.get_current_jitter()
        packet_loss = self.get_current_packet_loss()
        audio_quality = self.get_current_audio_quality()
        
        if current_latency > self.max_latency_ms:
            issues.append(f"High latency: {current_latency:.1f}ms")
        
        if current_jitter > self.jitter_threshold_ms:
            issues.append(f"High jitter: {current_jitter:.1f}ms")
        
        if packet_loss > 5.0:
            issues.append(f"High packet loss: {packet_loss:.1f}%")
        
        if audio_quality < 70.0:
            issues.append(f"Poor audio quality: {audio_quality:.1f}/100")
        
        return issues
    
    def _synchronization_worker(self):
        """Worker thread for continuous synchronization monitoring"""
        logger.info("Audio synchronization thread started")
        
        while self.is_active:
            try:
                # Adjust buffer size based on current conditions
                self._adjust_buffer_size()
                
                # Detect and log quality issues
                issues = self._detect_quality_issues()
                if issues:
                    logger.warning(f"Audio quality issues detected: {', '.join(issues)}")
                    self.quality_degradations += 1
                
                # Sleep before next adjustment cycle
                time.sleep(1.0)  # Adjust every second
                
            except Exception as e:
                logger.error(f"Synchronization worker error: {e}")
                break
        
        logger.info("Audio synchronization thread stopped")
    
    def start_synchronization(self):
        """Start audio synchronization monitoring"""
        if self.is_active:
            logger.warning("Audio synchronization already active")
            return
        
        try:
            self.is_active = True
            
            # Reset statistics
            self.sync_adjustments = 0
            self.buffer_underruns = 0
            self.buffer_overruns = 0
            self.quality_degradations = 0
            
            # Start synchronization thread
            self.sync_thread = threading.Thread(target=self._synchronization_worker)
            self.sync_thread.daemon = True
            self.sync_thread.start()
            
            logger.info("Audio synchronization started")
            
        except Exception as e:
            logger.error(f"Failed to start synchronization: {e}")
            self.is_active = False
            raise
    
    def stop_synchronization(self):
        """Stop audio synchronization monitoring"""
        if not self.is_active:
            return
        
        logger.info("Stopping audio synchronization...")
        
        # Stop synchronization flag
        self.is_active = False
        
        # Wait for thread to finish
        if self.sync_thread and self.sync_thread.is_alive():
            self.sync_thread.join(timeout=2.0)
        
        logger.info("Audio synchronization stopped")
    
    def get_synchronization_stats(self):
        """Get synchronization statistics"""
        return {
            'is_active': self.is_active,
            'current_latency_ms': self.get_current_latency(),
            'current_jitter_ms': self.get_current_jitter(),
            'current_packet_loss_percent': self.get_current_packet_loss(),
            'current_audio_quality': self.get_current_audio_quality(),
            'current_buffer_size': self.current_buffer_size,
            'target_latency_ms': self.target_latency_ms,
            'max_latency_ms': self.max_latency_ms,
            'sync_adjustments': self.sync_adjustments,
            'buffer_underruns': self.buffer_underruns,
            'buffer_overruns': self.buffer_overruns,
            'quality_degradations': self.quality_degradations,
            'latency_samples_count': len(self.latency_samples),
            'jitter_samples_count': len(self.jitter_samples)
        }
    
    def get_quality_assessment(self) -> str:
        """Get overall quality assessment"""
        current_latency = self.get_current_latency()
        current_jitter = self.get_current_jitter()
        packet_loss = self.get_current_packet_loss()
        audio_quality = self.get_current_audio_quality()
        
        # Calculate overall score
        latency_score = max(0, 100 - (current_latency / self.max_latency_ms) * 100)
        jitter_score = max(0, 100 - (current_jitter / self.jitter_threshold_ms) * 100)
        packet_loss_score = max(0, 100 - packet_loss * 10)  # 10% loss = 0 score
        
        overall_score = (latency_score + jitter_score + packet_loss_score + audio_quality) / 4
        
        if overall_score >= 90:
            return "Excellent"
        elif overall_score >= 75:
            return "Good"
        elif overall_score >= 60:
            return "Fair"
        elif overall_score >= 40:
            return "Poor"
        else:
            return "Very Poor"
    
    def force_buffer_adjustment(self, new_size: int):
        """Force buffer size adjustment"""
        if new_size < self.min_buffer_size or new_size > self.max_buffer_size:
            logger.warning(f"Buffer size {new_size} out of range [{self.min_buffer_size}, {self.max_buffer_size}]")
            return
        
        with self.buffer_adjustment_lock:
            old_size = self.current_buffer_size
            self.current_buffer_size = new_size
            
            logger.info(f"Buffer size manually adjusted: {old_size} -> {new_size}")
            
            # Notify callback if set
            if self.buffer_size_callback:
                try:
                    self.buffer_size_callback(new_size)
                except Exception as e:
                    logger.error(f"Buffer size callback error: {e}")
    
    def reset_measurements(self):
        """Reset all measurements and statistics"""
        with self.buffer_adjustment_lock:
            self.latency_samples.clear()
            self.jitter_samples.clear()
            self.audio_quality_samples.clear()
            self.packet_loss_samples.clear()
            
            self.sync_adjustments = 0
            self.buffer_underruns = 0
            self.buffer_overruns = 0
            self.quality_degradations = 0
            
            logger.info("Synchronization measurements reset")
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_synchronization()
        logger.info("AudioSynchronizer cleanup completed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()

# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    def buffer_size_changed(new_size):
        print(f"Buffer size changed to: {new_size}")
    
    try:
        # Create synchronizer instance
        synchronizer = AudioSynchronizer(target_latency_ms=50.0)
        synchronizer.set_buffer_size_callback(buffer_size_changed)
        
        # Start synchronization
        synchronizer.start_synchronization()
        
        # Simulate measurements
        print("Simulating audio measurements...")
        for i in range(20):
            # Simulate varying latency and jitter
            base_latency = 50 + np.random.normal(0, 10)
            capture_time = time.time()
            playback_time = capture_time + base_latency / 1000
            
            synchronizer.add_latency_measurement(capture_time, playback_time)
            synchronizer.add_packet_loss_measurement(np.random.uniform(0, 5))
            synchronizer.add_audio_quality_measurement(np.random.uniform(80, 100))
            
            time.sleep(0.5)
        
        # Show statistics
        stats = synchronizer.get_synchronization_stats()
        print(f"Synchronization stats: {stats}")
        print(f"Quality assessment: {synchronizer.get_quality_assessment()}")
        
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'synchronizer' in locals():
            synchronizer.cleanup()
