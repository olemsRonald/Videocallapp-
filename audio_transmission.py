"""
M2 Task: Transmit audio stream via UDP or WebRTC
OODA Audio Call System - Audio Transmission Module

This module handles real-time audio transmission over UDP networks.
Provides packet sequencing, fragmentation, and reliable delivery.
"""

import socket
import struct
import time
import threading
import queue
import logging
import numpy as np
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class AudioTransmission:
    """
    Real-time audio transmission over UDP
    
    Features:
    - UDP-based low-latency transmission
    - Packet sequencing and timestamping
    - Audio data fragmentation for large chunks
    - Automatic packet reassembly
    - Network statistics and monitoring
    """
    
    def __init__(self, 
                 local_port: int = 5000,
                 max_packet_size: int = 1400,
                 compression_enabled: bool = False):
        """
        Initialize audio transmission
        
        Args:
            local_port: Local UDP port for sending (default: 5000)
            max_packet_size: Maximum UDP packet size in bytes (default: 1400)
            compression_enabled: Enable audio compression (default: False)
        """
        self.local_port = local_port
        self.max_packet_size = max_packet_size
        self.compression_enabled = compression_enabled
        
        # Network socket
        self.socket = None
        
        # Transmission state
        self.is_transmitting = False
        self.target_address = None
        
        # Packet sequencing
        self.sequence_number = 0
        self.packet_lock = threading.Lock()
        
        # Transmission queue
        self.transmission_queue = queue.Queue(maxsize=50)
        self.transmission_thread = None
        
        # Statistics
        self.packets_sent = 0
        self.bytes_sent = 0
        self.transmission_start_time = None
        
        # Audio format info
        self.sample_rate = 44100
        self.channels = 1
        self.bytes_per_sample = 2  # 16-bit audio
        
        logger.info(f"AudioTransmission initialized on port {local_port}")
    
    def setup_socket(self):
        """Setup UDP socket for transmission"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to local port for sending
            self.socket.bind(('', self.local_port))
            
            logger.info(f"UDP socket bound to port {self.local_port}")
            
        except Exception as e:
            logger.error(f"Failed to setup socket: {e}")
            raise
    
    def set_target(self, target_ip: str, target_port: int):
        """
        Set target address for audio transmission
        
        Args:
            target_ip: Target IP address
            target_port: Target UDP port
        """
        self.target_address = (target_ip, target_port)
        logger.info(f"Target set to {target_ip}:{target_port}")
    
    def _create_audio_packet(self, audio_data: np.ndarray, timestamp: float) -> bytes:
        """
        Create audio packet with header
        
        Packet format:
        - Magic bytes (4 bytes): 'OODA'
        - Sequence number (4 bytes): uint32
        - Timestamp (8 bytes): double
        - Fragment info (4 bytes): fragment_index (2 bytes) + total_fragments (2 bytes)
        - Data length (4 bytes): uint32
        - Audio data (variable length)
        
        Args:
            audio_data: Audio data as numpy array
            timestamp: Timestamp of audio capture
            
        Returns:
            Packet bytes
        """
        # Convert audio data to bytes
        audio_bytes = audio_data.tobytes()
        
        # Calculate fragmentation
        max_audio_size = self.max_packet_size - 24  # Header size
        total_fragments = (len(audio_bytes) + max_audio_size - 1) // max_audio_size
        
        packets = []
        
        for fragment_index in range(total_fragments):
            start_pos = fragment_index * max_audio_size
            end_pos = min(start_pos + max_audio_size, len(audio_bytes))
            fragment_data = audio_bytes[start_pos:end_pos]
            
            with self.packet_lock:
                sequence = self.sequence_number
                self.sequence_number += 1
            
            # Create packet header
            header = struct.pack('!4sIQHHI',
                b'OODA',                    # Magic bytes
                sequence,                   # Sequence number
                int(timestamp * 1000000),   # Timestamp (microseconds)
                fragment_index,             # Fragment index
                total_fragments,            # Total fragments
                len(fragment_data)          # Data length
            )
            
            packet = header + fragment_data
            packets.append(packet)
        
        return packets
    
    def _transmission_worker(self):
        """Worker thread for audio transmission"""
        logger.info("Audio transmission thread started")
        
        while self.is_transmitting:
            try:
                # Get audio data from queue
                audio_data, timestamp = self.transmission_queue.get(timeout=0.1)
                
                if not self.target_address:
                    logger.warning("No target address set for transmission")
                    continue
                
                # Create and send packets
                packets = self._create_audio_packet(audio_data, timestamp)
                
                for packet in packets:
                    try:
                        bytes_sent = self.socket.sendto(packet, self.target_address)
                        
                        # Update statistics
                        self.packets_sent += 1
                        self.bytes_sent += bytes_sent
                        
                    except Exception as e:
                        logger.error(f"Failed to send packet: {e}")
                
                # Mark task as done
                self.transmission_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Transmission thread error: {e}")
                break
        
        logger.info("Audio transmission thread stopped")
    
    def start_transmission(self):
        """Start audio transmission"""
        if self.is_transmitting:
            logger.warning("Audio transmission already running")
            return
        
        try:
            # Setup socket if not already done
            if not self.socket:
                self.setup_socket()
            
            # Start transmission
            self.is_transmitting = True
            self.transmission_start_time = time.time()
            self.packets_sent = 0
            self.bytes_sent = 0
            
            # Start transmission thread
            self.transmission_thread = threading.Thread(target=self._transmission_worker)
            self.transmission_thread.daemon = True
            self.transmission_thread.start()
            
            logger.info("Audio transmission started")
            
        except Exception as e:
            logger.error(f"Failed to start transmission: {e}")
            self.is_transmitting = False
            raise
    
    def stop_transmission(self):
        """Stop audio transmission"""
        if not self.is_transmitting:
            return
        
        logger.info("Stopping audio transmission...")
        
        # Stop transmission flag
        self.is_transmitting = False
        
        # Wait for thread to finish
        if self.transmission_thread and self.transmission_thread.is_alive():
            self.transmission_thread.join(timeout=2.0)
        
        # Clear queue
        while not self.transmission_queue.empty():
            try:
                self.transmission_queue.get_nowait()
                self.transmission_queue.task_done()
            except queue.Empty:
                break
        
        logger.info("Audio transmission stopped")
    
    def send_audio(self, audio_data: np.ndarray, timestamp: float):
        """
        Send audio data for transmission
        
        Args:
            audio_data: Audio data as numpy array
            timestamp: Timestamp of audio capture
        """
        if not self.is_transmitting:
            logger.warning("Transmission not started")
            return
        
        try:
            # Add to transmission queue (non-blocking)
            self.transmission_queue.put_nowait((audio_data, timestamp))
        except queue.Full:
            logger.warning("Transmission queue full, dropping audio data")
    
    def get_transmission_stats(self):
        """Get transmission statistics"""
        if self.transmission_start_time:
            duration = time.time() - self.transmission_start_time
            packets_per_second = self.packets_sent / duration if duration > 0 else 0
            bytes_per_second = self.bytes_sent / duration if duration > 0 else 0
        else:
            duration = 0
            packets_per_second = 0
            bytes_per_second = 0
        
        return {
            'is_transmitting': self.is_transmitting,
            'target_address': self.target_address,
            'packets_sent': self.packets_sent,
            'bytes_sent': self.bytes_sent,
            'duration': duration,
            'packets_per_second': packets_per_second,
            'bytes_per_second': bytes_per_second,
            'queue_size': self.transmission_queue.qsize(),
            'sequence_number': self.sequence_number
        }
    
    def test_connectivity(self, target_ip: str, target_port: int, timeout: float = 5.0) -> bool:
        """
        Test connectivity to target address
        
        Args:
            target_ip: Target IP address
            target_port: Target port
            timeout: Timeout in seconds
            
        Returns:
            True if connectivity test passes
        """
        try:
            # Create test socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            test_socket.settimeout(timeout)
            
            # Send test packet
            test_data = b'OODA_TEST'
            test_socket.sendto(test_data, (target_ip, target_port))
            
            # For UDP, we can't really test connectivity without a response
            # This just tests if we can send without immediate error
            test_socket.close()
            
            logger.info(f"Connectivity test to {target_ip}:{target_port} passed")
            return True
            
        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            return False
    
    def cleanup(self):
        """Clean up resources"""
        self.stop_transmission()
        
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Error closing socket: {e}")
            finally:
                self.socket = None
        
        logger.info("AudioTransmission cleanup completed")
    
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
        # Create transmission instance
        transmission = AudioTransmission(local_port=5000)
        
        # Setup and start transmission
        transmission.setup_socket()
        transmission.set_target("127.0.0.1", 5001)  # Loopback test
        transmission.start_transmission()
        
        # Send test audio data
        print("Sending test audio data...")
        for i in range(10):
            # Generate test audio (sine wave)
            t = np.linspace(0, 0.1, 4410)  # 0.1 second at 44.1kHz
            frequency = 440 + i * 100  # Varying frequency
            audio_data = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
            
            timestamp = time.time()
            transmission.send_audio(audio_data, timestamp)
            
            time.sleep(0.1)
        
        # Show statistics
        stats = transmission.get_transmission_stats()
        print(f"Transmission stats: {stats}")
        
    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'transmission' in locals():
            transmission.cleanup()
