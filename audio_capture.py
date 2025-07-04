"""
M2 Task: Capture microphone input (using pyaudio)
OODA Audio Call System - Audio Capture Module

This module handles real-time microphone input capture using PyAudio.
Provides buffered audio capture with configurable sample rates and formats.
"""

import pyaudio
import numpy as np
import threading
import queue
import time
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class AudioCapture:
    """
    Real-time audio capture from microphone using PyAudio
    
    Features:
    - Configurable sample rate, channels, and format
    - Threaded capture for real-time performance
    - Audio buffering with queue management
    - Callback system for audio data processing
    - Automatic device detection and selection
    """
    
    def __init__(self, 
                 sample_rate: int = 44100,
                 channels: int = 1,
                 frames_per_buffer: int = 1024,
                 audio_format: int = pyaudio.paInt16,
                 device_index: Optional[int] = None):
        """
        Initialize audio capture
        
        Args:
            sample_rate: Audio sample rate in Hz (default: 44100)
            channels: Number of audio channels (default: 1 for mono)
            frames_per_buffer: Buffer size in frames (default: 1024)
            audio_format: PyAudio format (default: paInt16)
            device_index: Specific input device index (None for default)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames_per_buffer = frames_per_buffer
        self.audio_format = audio_format
        self.device_index = device_index
        
        # PyAudio instance
        self.audio = pyaudio.PyAudio()
        
        # Capture state
        self.is_capturing = False
        self.stream = None
        self.capture_thread = None
        
        # Audio buffer
        self.audio_queue = queue.Queue(maxsize=100)  # Buffer up to 100 chunks
        
        # Callbacks
        self.audio_callback: Optional[Callable] = None
        
        # Statistics
        self.frames_captured = 0
        self.capture_start_time = None
        
        logger.info(f"AudioCapture initialized: {sample_rate}Hz, {channels}ch, {frames_per_buffer} frames")
    
    def list_input_devices(self):
        """List available audio input devices"""
        devices = []
        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': device_info['name'],
                    'channels': device_info['maxInputChannels'],
                    'sample_rate': device_info['defaultSampleRate']
                })
        return devices
    
    def get_default_input_device(self):
        """Get default input device info"""
        try:
            default_device = self.audio.get_default_input_device_info()
            return {
                'index': default_device['index'],
                'name': default_device['name'],
                'channels': default_device['maxInputChannels'],
                'sample_rate': default_device['defaultSampleRate']
            }
        except Exception as e:
            logger.error(f"Failed to get default input device: {e}")
            return None
    
    def set_audio_callback(self, callback: Callable):
        """
        Set callback function for audio data
        
        Args:
            callback: Function that takes (audio_data, timestamp) as parameters
        """
        self.audio_callback = callback
        logger.info("Audio callback set")
    
    def _audio_stream_callback(self, in_data, frame_count, time_info, status):
        """Internal PyAudio stream callback"""
        if status:
            logger.warning(f"Audio stream status: {status}")
        
        # Convert audio data to numpy array
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        timestamp = time.time()
        
        # Add to queue (non-blocking)
        try:
            self.audio_queue.put_nowait((audio_data, timestamp))
        except queue.Full:
            logger.warning("Audio queue full, dropping frame")
        
        # Update statistics
        self.frames_captured += frame_count
        
        return (None, pyaudio.paContinue)
    
    def _capture_thread_worker(self):
        """Worker thread for processing captured audio"""
        logger.info("Audio capture thread started")
        
        while self.is_capturing:
            try:
                # Get audio data from queue (with timeout)
                audio_data, timestamp = self.audio_queue.get(timeout=0.1)
                
                # Call user callback if set
                if self.audio_callback:
                    try:
                        self.audio_callback(audio_data, timestamp)
                    except Exception as e:
                        logger.error(f"Audio callback error: {e}")
                
                # Mark task as done
                self.audio_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Capture thread error: {e}")
                break
        
        logger.info("Audio capture thread stopped")
    
    def start_capture(self):
        """Start audio capture"""
        if self.is_capturing:
            logger.warning("Audio capture already running")
            return
        
        try:
            # Open audio stream
            self.stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=self.frames_per_buffer,
                stream_callback=self._audio_stream_callback,
                start=False
            )
            
            # Start capture
            self.is_capturing = True
            self.capture_start_time = time.time()
            self.frames_captured = 0
            
            # Start processing thread
            self.capture_thread = threading.Thread(target=self._capture_thread_worker)
            self.capture_thread.daemon = True
            self.capture_thread.start()
            
            # Start audio stream
            self.stream.start_stream()
            
            logger.info("Audio capture started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start audio capture: {e}")
            self.is_capturing = False
            raise
    
    def stop_capture(self):
        """Stop audio capture"""
        if not self.is_capturing:
            return
        
        logger.info("Stopping audio capture...")
        
        # Stop capture flag
        self.is_capturing = False
        
        # Stop and close stream
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
            finally:
                self.stream = None
        
        # Wait for thread to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2.0)
        
        # Clear queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except queue.Empty:
                break
        
        logger.info("Audio capture stopped")
    
    def get_capture_stats(self):
        """Get capture statistics"""
        if self.capture_start_time:
            duration = time.time() - self.capture_start_time
            fps = self.frames_captured / duration if duration > 0 else 0
        else:
            duration = 0
            fps = 0
        
        return {
            'is_capturing': self.is_capturing,
            'frames_captured': self.frames_captured,
            'duration': duration,
            'frames_per_second': fps,
            'queue_size': self.audio_queue.qsize(),
            'sample_rate': self.sample_rate,
            'channels': self.channels
        }
    
    def get_audio_level(self, audio_data):
        """Calculate audio level (RMS) from audio data"""
        if len(audio_data) == 0:
            return 0.0
        
        # Calculate RMS (Root Mean Square)
        rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))
        
        # Convert to dB (with protection against log(0))
        if rms > 0:
            db = 20 * np.log10(rms / 32767.0)  # 32767 is max value for int16
        else:
            db = -96.0  # Silence threshold
        
        return max(db, -96.0)  # Clamp to reasonable minimum
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_capture()
        self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_capture()
        
        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
            finally:
                self.audio = None
        
        logger.info("AudioCapture cleanup completed")

# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    def audio_data_handler(audio_data, timestamp):
        """Example audio data handler"""
        level = AudioCapture.get_audio_level(None, audio_data)
        print(f"Audio level: {level:.1f} dB, Samples: {len(audio_data)}")
    
    try:
        # Create audio capture instance
        capture = AudioCapture(sample_rate=44100, channels=1)
        
        # List available devices
        print("Available input devices:")
        devices = capture.list_input_devices()
        for device in devices:
            print(f"  {device['index']}: {device['name']}")
        
        # Set callback and start capture
        capture.set_audio_callback(audio_data_handler)
        capture.start_capture()
        
        print("Capturing audio... Press Enter to stop")
        input()
        
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'capture' in locals():
            capture.stop_capture()
            capture.cleanup()
