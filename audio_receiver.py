"""
M2 Task: Receive remote audio stream and play it
OODA Audio Call System - Audio Receiver Module

This module handles real-time audio reception and playback over UDP networks.
Provides packet reassembly, buffering, and synchronized playback.
"""

import socket
import struct
import time
import threading
import queue
import logging
import numpy as np
import pyaudio
from typing import Optional, Dict, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)

class AudioReceiver:
    """
    Real-time audio reception and playback over UDP
    
    Features:
    - UDP packet reception and reassembly
    - Audio buffering for smooth playback
    - Packet sequence handling and reordering
    - Jitter compensation and latency management
    - Real-time audio playback using PyAudio
    """
    
    def __init__(self,
                 listen_port: int = 5001,
                 sample_rate: int = 44100,
                 channels: int = 1,
                 frames_per_buffer: int = 1024,
                 audio_format: int = pyaudio.paInt16,
                 buffer_size: int = 10):
        """
        Initialize audio receiver
        
        Args:
            listen_port: UDP port to listen on (default: 5001)
            sample_rate: Audio sample rate in Hz (default: 44100)
            channels: Number of audio channels (default: 1)
            frames_per_buffer: Buffer size for playback (default: 1024)
            audio_format: PyAudio format (default: paInt16)
            buffer_size: Number of audio chunks to buffer (default: 10)
        """
        self.listen_port = listen_port
        self.sample_rate = sample_rate
        self.channels = channels
        self.frames_per_buffer = frames_per_buffer
        self.audio_format = audio_format
        self.buffer_size = buffer_size
        
        # Network socket
        self.socket = None
        
        # PyAudio instance
        self.audio = pyaudio.PyAudio()
        self.playback_stream = None
        
        # Reception state
        self.is_receiving = False
        self.is_playing = False
        
        # Threading
        self.reception_thread = None
        self.playback_thread = None
        
        # Packet reassembly
        self.packet_fragments = defaultdict(dict)  # sequence -> {fragment_index: data}
        self.fragment_lock = threading.Lock()
        
        # Audio buffering
        self.audio_buffer = queue.Queue(maxsize=buffer_size)
        self.playback_queue = queue.Queue(maxsize=buffer_size * 2)
        
        # Statistics
        self.packets_received = 0
        self.bytes_received = 0
        self.packets_lost = 0
        self.last_sequence = -1
        self.reception_start_time = None
        
        # Timing and synchronization
        self.first_packet_time = None
        self.playback_start_time = None
        self.latency_samples = []
        
        logger.info(f"AudioReceiver initialized on port {listen_port}")
    
    def setup_socket(self):
        """Setup UDP socket for reception"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('', self.listen_port))
            
            logger.info(f"UDP socket listening on port {self.listen_port}")
            
        except Exception as e:
            logger.error(f"Failed to setup socket: {e}")
            raise
    
    def setup_playback(self):
        """Setup PyAudio playback stream"""
        try:
            self.playback_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                frames_per_buffer=self.frames_per_buffer,
                start=False
            )
            
            logger.info("Audio playback stream created")
            
        except Exception as e:
            logger.error(f"Failed to setup playback: {e}")
            raise
    
    def _parse_audio_packet(self, packet_data: bytes) -> Optional[Tuple]:
        """
        Parse received audio packet
        
        Returns:
            Tuple of (sequence, timestamp, fragment_index, total_fragments, audio_data)
            or None if packet is invalid
        """
        try:
            if len(packet_data) < 24:  # Minimum header size
                return None
            
            # Parse header
            magic, sequence, timestamp_us, fragment_index, total_fragments, data_length = \
                struct.unpack('!4sIQHHI', packet_data[:24])
            
            if magic != b'OODA':
                logger.warning("Invalid packet magic")
                return None
            
            # Extract audio data
            audio_data = packet_data[24:24 + data_length]
            
            if len(audio_data) != data_length:
                logger.warning("Packet data length mismatch")
                return None
            
            timestamp = timestamp_us / 1000000.0  # Convert to seconds
            
            return (sequence, timestamp, fragment_index, total_fragments, audio_data)
            
        except Exception as e:
            logger.error(f"Failed to parse packet: {e}")
            return None
    
    def _reassemble_audio_packet(self, sequence: int, timestamp: float, 
                                fragment_index: int, total_fragments: int, 
                                fragment_data: bytes) -> Optional[Tuple]:
        """
        Reassemble fragmented audio packet
        
        Returns:
            Tuple of (timestamp, complete_audio_data) if packet is complete, None otherwise
        """
        with self.fragment_lock:
            # Store fragment
            self.packet_fragments[sequence][fragment_index] = fragment_data
            
            # Check if all fragments received
            if len(self.packet_fragments[sequence]) == total_fragments:
                # Reassemble complete packet
                complete_data = b''
                for i in range(total_fragments):
                    if i in self.packet_fragments[sequence]:
                        complete_data += self.packet_fragments[sequence][i]
                    else:
                        # Missing fragment
                        logger.warning(f"Missing fragment {i} for sequence {sequence}")
                        return None
                
                # Clean up fragments
                del self.packet_fragments[sequence]
                
                # Convert to numpy array
                audio_data = np.frombuffer(complete_data, dtype=np.int16)
                
                return (timestamp, audio_data)
        
        return None
    
    def _reception_worker(self):
        """Worker thread for packet reception"""
        logger.info("Audio reception thread started")
        
        while self.is_receiving:
            try:
                # Receive packet with timeout
                self.socket.settimeout(0.1)
                packet_data, addr = self.socket.recvfrom(2048)
                
                # Update statistics
                self.packets_received += 1
                self.bytes_received += len(packet_data)
                
                # Parse packet
                parsed = self._parse_audio_packet(packet_data)
                if not parsed:
                    continue
                
                sequence, timestamp, fragment_index, total_fragments, fragment_data = parsed
                
                # Track packet loss
                if self.last_sequence >= 0 and sequence > self.last_sequence + 1:
                    lost = sequence - self.last_sequence - 1
                    self.packets_lost += lost
                    logger.warning(f"Lost {lost} packets (sequence gap: {self.last_sequence} -> {sequence})")
                
                self.last_sequence = max(self.last_sequence, sequence)
                
                # Reassemble packet
                reassembled = self._reassemble_audio_packet(
                    sequence, timestamp, fragment_index, total_fragments, fragment_data
                )
                
                if reassembled:
                    packet_timestamp, audio_data = reassembled
                    
                    # Calculate latency
                    current_time = time.time()
                    latency = current_time - packet_timestamp
                    self.latency_samples.append(latency)
                    
                    # Keep only recent latency samples
                    if len(self.latency_samples) > 100:
                        self.latency_samples = self.latency_samples[-100:]
                    
                    # Add to audio buffer
                    try:
                        self.audio_buffer.put_nowait((packet_timestamp, audio_data))
                    except queue.Full:
                        logger.warning("Audio buffer full, dropping packet")
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_receiving:  # Only log if we're supposed to be receiving
                    logger.error(f"Reception error: {e}")
                break
        
        logger.info("Audio reception thread stopped")
    
    def _playback_worker(self):
        """Worker thread for audio playback"""
        logger.info("Audio playback thread started")
        
        while self.is_playing:
            try:
                # Get audio data from buffer
                timestamp, audio_data = self.audio_buffer.get(timeout=0.1)
                
                # Convert to bytes for playback
                audio_bytes = audio_data.tobytes()
                
                # Play audio
                if self.playback_stream and self.playback_stream.is_active():
                    self.playback_stream.write(audio_bytes)
                
                # Mark task as done
                self.audio_buffer.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                if self.is_playing:  # Only log if we're supposed to be playing
                    logger.error(f"Playback error: {e}")
                break
        
        logger.info("Audio playback thread stopped")
    
    def start_reception(self):
        """Start audio reception"""
        if self.is_receiving:
            logger.warning("Audio reception already running")
            return
        
        try:
            # Setup socket if not already done
            if not self.socket:
                self.setup_socket()
            
            # Start reception
            self.is_receiving = True
            self.reception_start_time = time.time()
            self.packets_received = 0
            self.bytes_received = 0
            self.packets_lost = 0
            self.last_sequence = -1
            
            # Start reception thread
            self.reception_thread = threading.Thread(target=self._reception_worker)
            self.reception_thread.daemon = True
            self.reception_thread.start()
            
            logger.info("Audio reception started")
            
        except Exception as e:
            logger.error(f"Failed to start reception: {e}")
            self.is_receiving = False
            raise
    
    def start_playback(self):
        """Start audio playback"""
        if self.is_playing:
            logger.warning("Audio playback already running")
            return
        
        try:
            # Setup playback if not already done
            if not self.playback_stream:
                self.setup_playback()
            
            # Start playback
            self.is_playing = True
            self.playback_start_time = time.time()
            
            # Start playback thread
            self.playback_thread = threading.Thread(target=self._playback_worker)
            self.playback_thread.daemon = True
            self.playback_thread.start()
            
            # Start audio stream
            self.playback_stream.start_stream()
            
            logger.info("Audio playback started")
            
        except Exception as e:
            logger.error(f"Failed to start playback: {e}")
            self.is_playing = False
            raise
    
    def stop_reception(self):
        """Stop audio reception"""
        if not self.is_receiving:
            return
        
        logger.info("Stopping audio reception...")
        
        # Stop reception flag
        self.is_receiving = False
        
        # Wait for thread to finish
        if self.reception_thread and self.reception_thread.is_alive():
            self.reception_thread.join(timeout=2.0)
        
        logger.info("Audio reception stopped")
    
    def stop_playback(self):
        """Stop audio playback"""
        if not self.is_playing:
            return
        
        logger.info("Stopping audio playback...")
        
        # Stop playback flag
        self.is_playing = False
        
        # Stop audio stream
        if self.playback_stream:
            try:
                self.playback_stream.stop_stream()
            except Exception as e:
                logger.error(f"Error stopping playback stream: {e}")
        
        # Wait for thread to finish
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=2.0)
        
        # Clear buffers
        while not self.audio_buffer.empty():
            try:
                self.audio_buffer.get_nowait()
                self.audio_buffer.task_done()
            except queue.Empty:
                break
        
        logger.info("Audio playback stopped")
    
    def get_reception_stats(self):
        """Get reception statistics"""
        if self.reception_start_time:
            duration = time.time() - self.reception_start_time
            packets_per_second = self.packets_received / duration if duration > 0 else 0
            bytes_per_second = self.bytes_received / duration if duration > 0 else 0
        else:
            duration = 0
            packets_per_second = 0
            bytes_per_second = 0
        
        # Calculate average latency
        avg_latency = np.mean(self.latency_samples) if self.latency_samples else 0
        
        # Calculate packet loss rate
        total_expected = self.packets_received + self.packets_lost
        loss_rate = (self.packets_lost / total_expected * 100) if total_expected > 0 else 0
        
        return {
            'is_receiving': self.is_receiving,
            'is_playing': self.is_playing,
            'packets_received': self.packets_received,
            'bytes_received': self.bytes_received,
            'packets_lost': self.packets_lost,
            'loss_rate_percent': loss_rate,
            'duration': duration,
            'packets_per_second': packets_per_second,
            'bytes_per_second': bytes_per_second,
            'buffer_size': self.audio_buffer.qsize(),
            'average_latency': avg_latency,
            'sample_rate': self.sample_rate,
            'channels': self.channels
        }
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_reception()
        self.stop_playback()
        
        if self.playback_stream:
            try:
                self.playback_stream.close()
            except Exception as e:
                logger.error(f"Error closing playback stream: {e}")
            finally:
                self.playback_stream = None
        
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Error closing socket: {e}")
            finally:
                self.socket = None
        
        if self.audio:
            try:
                self.audio.terminate()
            except Exception as e:
                logger.error(f"Error terminating PyAudio: {e}")
            finally:
                self.audio = None
        
        logger.info("AudioReceiver cleanup completed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.cleanup()

# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    try:
        # Create receiver instance
        receiver = AudioReceiver(listen_port=5001)
        
        # Start reception and playback
        receiver.start_reception()
        receiver.start_playback()
        
        print("Receiving and playing audio... Press Enter to stop")
        input()
        
        # Show statistics
        stats = receiver.get_reception_stats()
        print(f"Reception stats: {stats}")
        
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'receiver' in locals():
            receiver.cleanup()
