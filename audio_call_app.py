"""
OODA Audio Call System - Main Application
Integrates all M2 tasks: Capture, Transmission, Reception, and Synchronization

This is the main application that coordinates all audio call components
to provide bidirectional real-time audio communication.
"""

import asyncio
import logging
import time
import threading
from typing import Optional, Dict, Any
from enum import Enum

from audio_capture import AudioCapture
from audio_transmission import AudioTransmission
from audio_receiver import AudioReceiver
from audio_synchronizer import AudioSynchronizer

logger = logging.getLogger(__name__)

class CallState(Enum):
    """Call state enumeration"""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"

class AudioCallApp:
    """
    Main OODA Audio Call Application
    
    Integrates all M2 components:
    - M2: Capture microphone input (using pyaudio)
    - M2: Transmit audio stream via UDP
    - M2: Receive remote audio stream and play it
    - M2: Ensure real-time synchronization
    """
    
    def __init__(self,
                 local_port: int = 5000,
                 listen_port: int = 5001,
                 sample_rate: int = 44100,
                 channels: int = 1,
                 frames_per_buffer: int = 1024):
        """
        Initialize audio call application
        
        Args:
            local_port: Local port for sending audio
            listen_port: Port for receiving audio
            sample_rate: Audio sample rate in Hz
            channels: Number of audio channels
            frames_per_buffer: Buffer size for audio processing
        """
        self.local_port = local_port
        self.listen_port = listen_port
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames_per_buffer = frames_per_buffer
        
        # Call state
        self.call_state = CallState.IDLE
        self.remote_address = None
        self.call_start_time = None
        
        # M2 Components
        self.audio_capture: Optional[AudioCapture] = None
        self.audio_transmission: Optional[AudioTransmission] = None
        self.audio_receiver: Optional[AudioReceiver] = None
        self.audio_synchronizer: Optional[AudioSynchronizer] = None
        
        # Statistics
        self.call_duration = 0.0
        self.total_calls = 0
        
        logger.info(f"AudioCallApp initialized: {local_port}->{listen_port}, {sample_rate}Hz")
    
    def _initialize_components(self):
        """Initialize all M2 audio components"""
        try:
            # M2: Initialize audio capture (microphone input)
            self.audio_capture = AudioCapture(
                sample_rate=self.sample_rate,
                channels=self.channels,
                frames_per_buffer=self.frames_per_buffer
            )
            
            # M2: Initialize audio transmission (UDP stream)
            self.audio_transmission = AudioTransmission(
                local_port=self.local_port
            )
            
            # M2: Initialize audio receiver (remote stream playback)
            self.audio_receiver = AudioReceiver(
                listen_port=self.listen_port,
                sample_rate=self.sample_rate,
                channels=self.channels,
                frames_per_buffer=self.frames_per_buffer
            )
            
            # M2: Initialize audio synchronizer (real-time sync)
            self.audio_synchronizer = AudioSynchronizer(
                target_latency_ms=50.0,
                max_latency_ms=200.0
            )
            
            # Set up component interactions
            self._setup_component_callbacks()
            
            logger.info("All M2 components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    def _setup_component_callbacks(self):
        """Setup callbacks between components for M2 integration"""
        
        # M2: Connect capture to transmission
        def audio_capture_callback(audio_data, timestamp):
            """Forward captured audio to transmission"""
            if self.audio_transmission and self.call_state == CallState.CONNECTED:
                self.audio_transmission.send_audio(audio_data, timestamp)
                
                # M2: Add synchronization measurement
                if self.audio_synchronizer:
                    # Estimate playback time (current time + network latency)
                    estimated_playback_time = time.time() + 0.05  # 50ms estimate
                    self.audio_synchronizer.add_latency_measurement(timestamp, estimated_playback_time)
        
        self.audio_capture.set_audio_callback(audio_capture_callback)
        
        # M2: Connect synchronizer to receiver for buffer management
        def buffer_size_callback(new_size):
            """Adjust receiver buffer based on synchronizer recommendations"""
            if self.audio_receiver:
                self.audio_receiver.buffer_size = new_size
                logger.info(f"Receiver buffer size adjusted to {new_size}")
        
        self.audio_synchronizer.set_buffer_size_callback(buffer_size_callback)
    
    def start_call(self, remote_ip: str, remote_port: int) -> bool:
        """
        Start an audio call to remote peer
        
        Args:
            remote_ip: Remote peer IP address
            remote_port: Remote peer port
            
        Returns:
            True if call started successfully
        """
        if self.call_state != CallState.IDLE:
            logger.warning(f"Cannot start call in state: {self.call_state}")
            return False
        
        try:
            logger.info(f"Starting call to {remote_ip}:{remote_port}")
            self.call_state = CallState.CONNECTING
            self.remote_address = (remote_ip, remote_port)
            
            # Initialize components if not already done
            if not self.audio_capture:
                self._initialize_components()
            
            # M2: Setup transmission target
            self.audio_transmission.set_target(remote_ip, remote_port)
            
            # M2: Start all components in correct order
            
            # 1. Start synchronizer first
            self.audio_synchronizer.start_synchronization()
            
            # 2. Start receiver for incoming audio
            self.audio_receiver.start_reception()
            self.audio_receiver.start_playback()
            
            # 3. Start transmission
            self.audio_transmission.start_transmission()
            
            # 4. Start capture last (begins audio flow)
            self.audio_capture.start_capture()
            
            # Update call state
            self.call_state = CallState.CONNECTED
            self.call_start_time = time.time()
            self.total_calls += 1
            
            logger.info("Audio call started successfully - All M2 components active")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start call: {e}")
            self.call_state = CallState.ERROR
            self._cleanup_call()
            return False
    
    def end_call(self):
        """End the current audio call"""
        if self.call_state not in [CallState.CONNECTED, CallState.CONNECTING]:
            logger.warning(f"No active call to end (state: {self.call_state})")
            return
        
        logger.info("Ending audio call")
        self.call_state = CallState.DISCONNECTING
        
        # Calculate call duration
        if self.call_start_time:
            self.call_duration = time.time() - self.call_start_time
        
        self._cleanup_call()
        
        self.call_state = CallState.IDLE
        self.remote_address = None
        self.call_start_time = None
        
        logger.info(f"Audio call ended (duration: {self.call_duration:.1f}s)")
    
    def _cleanup_call(self):
        """Clean up all M2 components after call"""
        try:
            # M2: Stop all components in reverse order
            
            # 1. Stop capture first (stops audio flow)
            if self.audio_capture:
                self.audio_capture.stop_capture()
            
            # 2. Stop transmission
            if self.audio_transmission:
                self.audio_transmission.stop_transmission()
            
            # 3. Stop receiver
            if self.audio_receiver:
                self.audio_receiver.stop_playback()
                self.audio_receiver.stop_reception()
            
            # 4. Stop synchronizer last
            if self.audio_synchronizer:
                self.audio_synchronizer.stop_synchronization()
            
            logger.info("All M2 components stopped")
            
        except Exception as e:
            logger.error(f"Error during call cleanup: {e}")
    
    def get_call_status(self) -> Dict[str, Any]:
        """Get current call status and statistics"""
        status = {
            'call_state': self.call_state.value,
            'remote_address': self.remote_address,
            'call_duration': time.time() - self.call_start_time if self.call_start_time else 0,
            'total_calls': self.total_calls,
            'components_active': {
                'capture': self.audio_capture.is_capturing if self.audio_capture else False,
                'transmission': self.audio_transmission.is_transmitting if self.audio_transmission else False,
                'reception': self.audio_receiver.is_receiving if self.audio_receiver else False,
                'playback': self.audio_receiver.is_playing if self.audio_receiver else False,
                'synchronization': self.audio_synchronizer.is_active if self.audio_synchronizer else False
            }
        }
        
        # Add component statistics if available
        if self.call_state == CallState.CONNECTED:
            if self.audio_capture:
                status['capture_stats'] = self.audio_capture.get_capture_stats()
            
            if self.audio_transmission:
                status['transmission_stats'] = self.audio_transmission.get_transmission_stats()
            
            if self.audio_receiver:
                status['reception_stats'] = self.audio_receiver.get_reception_stats()
            
            if self.audio_synchronizer:
                status['synchronization_stats'] = self.audio_synchronizer.get_synchronization_stats()
                status['audio_quality'] = self.audio_synchronizer.get_quality_assessment()
        
        return status
    
    def is_call_active(self) -> bool:
        """Check if call is currently active"""
        return self.call_state == CallState.CONNECTED
    
    def get_audio_devices(self) -> Dict[str, Any]:
        """Get available audio devices"""
        if not self.audio_capture:
            self._initialize_components()
        
        return {
            'input_devices': self.audio_capture.list_input_devices(),
            'default_input': self.audio_capture.get_default_input_device()
        }
    
    def test_connectivity(self, remote_ip: str, remote_port: int) -> bool:
        """Test network connectivity to remote peer"""
        if not self.audio_transmission:
            self._initialize_components()
        
        return self.audio_transmission.test_connectivity(remote_ip, remote_port)
    
    def cleanup(self):
        """Clean up all resources"""
        logger.info("Cleaning up AudioCallApp")
        
        # End any active call
        if self.call_state in [CallState.CONNECTED, CallState.CONNECTING]:
            self.end_call()
        
        # Clean up all M2 components
        if self.audio_capture:
            self.audio_capture.cleanup()
            self.audio_capture = None
        
        if self.audio_transmission:
            self.audio_transmission.cleanup()
            self.audio_transmission = None
        
        if self.audio_receiver:
            self.audio_receiver.cleanup()
            self.audio_receiver = None
        
        if self.audio_synchronizer:
            self.audio_synchronizer.cleanup()
            self.audio_synchronizer = None
        
        logger.info("AudioCallApp cleanup completed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()

# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def main():
        """Main async function for testing"""
        try:
            # Create audio call application
            app = AudioCallApp(local_port=5000, listen_port=5001)
            
            print("OODA Audio Call System - M2 Implementation")
            print("==========================================")
            print("All M2 tasks integrated:")
            print("✓ M2: Capture microphone input (using pyaudio)")
            print("✓ M2: Transmit audio stream via UDP")
            print("✓ M2: Receive remote audio stream and play it")
            print("✓ M2: Ensure real-time synchronization")
            print()
            
            # Show available devices
            devices = app.get_audio_devices()
            print("Available audio devices:")
            for device in devices['input_devices']:
                print(f"  {device['index']}: {device['name']}")
            print()
            
            # Test connectivity
            print("Testing connectivity to localhost...")
            if app.test_connectivity("127.0.0.1", 5001):
                print("✓ Connectivity test passed")
            else:
                print("✗ Connectivity test failed")
            print()
            
            # Interactive mode
            print("Commands:")
            print("  call <ip> <port> - Start call to remote peer")
            print("  end              - End current call")
            print("  status           - Show call status")
            print("  quit             - Exit application")
            print()
            
            while True:
                try:
                    command = input("OODA> ").strip().split()
                    
                    if not command:
                        continue
                    
                    if command[0] == "quit":
                        break
                    elif command[0] == "call" and len(command) == 3:
                        ip, port = command[1], int(command[2])
                        if app.start_call(ip, port):
                            print(f"✓ Call started to {ip}:{port}")
                        else:
                            print(f"✗ Failed to start call to {ip}:{port}")
                    elif command[0] == "end":
                        app.end_call()
                        print("✓ Call ended")
                    elif command[0] == "status":
                        status = app.get_call_status()
                        print(f"Call state: {status['call_state']}")
                        if status['remote_address']:
                            print(f"Remote: {status['remote_address']}")
                            print(f"Duration: {status['call_duration']:.1f}s")
                            if 'audio_quality' in status:
                                print(f"Quality: {status['audio_quality']}")
                    else:
                        print("Invalid command")
                        
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"Error: {e}")
            
        except Exception as e:
            print(f"Application error: {e}")
        finally:
            if 'app' in locals():
                app.cleanup()
    
    # Run the application
    asyncio.run(main())
