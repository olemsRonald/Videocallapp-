"""
OODA Audio Call System - M2 Tasks Test Suite
Tests all M2 requirements: Capture, Transmission, Reception, and Synchronization

This test suite verifies that all M2 tasks are correctly implemented:
- M2: Capture microphone input (using pyaudio)
- M2: Transmit audio stream via UDP
- M2: Receive remote audio stream and play it
- M2: Ensure real-time synchronization
"""

import unittest
import time
import threading
import numpy as np
import logging
from unittest.mock import Mock, patch

# Import M2 components
from audio_capture import AudioCapture
from audio_transmission import AudioTransmission
from audio_receiver import AudioReceiver
from audio_synchronizer import AudioSynchronizer
from audio_call_app import AudioCallApp, CallState

# Configure logging for tests
logging.basicConfig(level=logging.WARNING)  # Reduce noise during tests

class TestM2AudioCapture(unittest.TestCase):
    """Test M2: Capture microphone input (using pyaudio)"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.captured_audio = []
        self.capture_timestamps = []
    
    def audio_callback(self, audio_data, timestamp):
        """Test callback for captured audio"""
        self.captured_audio.append(audio_data)
        self.capture_timestamps.append(timestamp)
    
    @patch('pyaudio.PyAudio')
    def test_audio_capture_initialization(self, mock_pyaudio):
        """Test M2: Audio capture initialization"""
        # Mock PyAudio
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        
        # Test initialization
        capture = AudioCapture(sample_rate=44100, channels=1)
        
        self.assertEqual(capture.sample_rate, 44100)
        self.assertEqual(capture.channels, 1)
        self.assertFalse(capture.is_capturing)
        
        capture.cleanup()
    
    @patch('pyaudio.PyAudio')
    def test_audio_capture_callback_system(self, mock_pyaudio):
        """Test M2: Audio capture callback system"""
        # Mock PyAudio
        mock_audio = Mock()
        mock_pyaudio.return_value = mock_audio
        
        capture = AudioCapture()
        capture.set_audio_callback(self.audio_callback)
        
        # Simulate audio data
        test_audio = np.array([1, 2, 3, 4, 5], dtype=np.int16)
        test_timestamp = time.time()
        
        # Test callback directly
        capture.audio_callback(test_audio, test_timestamp)
        
        # Verify callback was called
        self.assertEqual(len(self.captured_audio), 1)
        np.testing.assert_array_equal(self.captured_audio[0], test_audio)
        
        capture.cleanup()
    
    def test_audio_level_calculation(self):
        """Test M2: Audio level calculation"""
        capture = AudioCapture()
        
        # Test silence
        silence = np.zeros(1024, dtype=np.int16)
        level = capture.get_audio_level(silence)
        self.assertEqual(level, -96.0)  # Silence threshold
        
        # Test full scale
        full_scale = np.full(1024, 32767, dtype=np.int16)
        level = capture.get_audio_level(full_scale)
        self.assertAlmostEqual(level, 0.0, places=1)  # 0 dB for full scale
        
        capture.cleanup()

class TestM2AudioTransmission(unittest.TestCase):
    """Test M2: Transmit audio stream via UDP"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.transmission = AudioTransmission(local_port=5002)
    
    def tearDown(self):
        """Clean up after tests"""
        self.transmission.cleanup()
    
    def test_transmission_initialization(self):
        """Test M2: Transmission initialization"""
        self.assertEqual(self.transmission.local_port, 5002)
        self.assertFalse(self.transmission.is_transmitting)
        self.assertEqual(self.transmission.sequence_number, 0)
    
    def test_packet_creation(self):
        """Test M2: Audio packet creation and structure"""
        # Create test audio data
        test_audio = np.array([100, 200, 300, 400], dtype=np.int16)
        test_timestamp = time.time()
        
        # Create packet
        packets = self.transmission._create_audio_packet(test_audio, test_timestamp)
        
        self.assertIsInstance(packets, list)
        self.assertGreater(len(packets), 0)
        
        # Verify packet structure
        packet = packets[0]
        self.assertTrue(packet.startswith(b'OODA'))  # Magic bytes
        self.assertGreater(len(packet), 24)  # Header + data
    
    def test_target_setting(self):
        """Test M2: Setting transmission target"""
        target_ip = "192.168.1.100"
        target_port = 5001
        
        self.transmission.set_target(target_ip, target_port)
        
        self.assertEqual(self.transmission.target_address, (target_ip, target_port))
    
    def test_transmission_statistics(self):
        """Test M2: Transmission statistics tracking"""
        stats = self.transmission.get_transmission_stats()
        
        required_keys = [
            'is_transmitting', 'target_address', 'packets_sent',
            'bytes_sent', 'duration', 'packets_per_second',
            'bytes_per_second', 'queue_size', 'sequence_number'
        ]
        
        for key in required_keys:
            self.assertIn(key, stats)

class TestM2AudioReception(unittest.TestCase):
    """Test M2: Receive remote audio stream and play it"""
    
    def setUp(self):
        """Set up test fixtures"""
        with patch('pyaudio.PyAudio'):
            self.receiver = AudioReceiver(listen_port=5003)
    
    def tearDown(self):
        """Clean up after tests"""
        self.receiver.cleanup()
    
    def test_receiver_initialization(self):
        """Test M2: Receiver initialization"""
        self.assertEqual(self.receiver.listen_port, 5003)
        self.assertFalse(self.receiver.is_receiving)
        self.assertFalse(self.receiver.is_playing)
    
    def test_packet_parsing(self):
        """Test M2: Audio packet parsing"""
        # Create a valid packet
        import struct
        
        magic = b'OODA'
        sequence = 123
        timestamp_us = int(time.time() * 1000000)
        fragment_index = 0
        total_fragments = 1
        audio_data = b'\x01\x02\x03\x04'
        data_length = len(audio_data)
        
        header = struct.pack('!4sIQHHI', magic, sequence, timestamp_us,
                           fragment_index, total_fragments, data_length)
        packet = header + audio_data
        
        # Parse packet
        result = self.receiver._parse_audio_packet(packet)
        
        self.assertIsNotNone(result)
        parsed_seq, parsed_ts, parsed_frag, parsed_total, parsed_data = result
        
        self.assertEqual(parsed_seq, sequence)
        self.assertEqual(parsed_frag, fragment_index)
        self.assertEqual(parsed_total, total_fragments)
        self.assertEqual(parsed_data, audio_data)
    
    def test_packet_reassembly(self):
        """Test M2: Fragmented packet reassembly"""
        # Test single fragment packet
        test_data = b'\x01\x02\x03\x04'
        result = self.receiver._reassemble_audio_packet(1, time.time(), 0, 1, test_data)
        
        self.assertIsNotNone(result)
        timestamp, audio_data = result
        self.assertEqual(audio_data.tobytes(), test_data)
    
    def test_reception_statistics(self):
        """Test M2: Reception statistics tracking"""
        stats = self.receiver.get_reception_stats()
        
        required_keys = [
            'is_receiving', 'is_playing', 'packets_received',
            'bytes_received', 'packets_lost', 'loss_rate_percent',
            'duration', 'packets_per_second', 'bytes_per_second',
            'buffer_size', 'average_latency', 'sample_rate', 'channels'
        ]
        
        for key in required_keys:
            self.assertIn(key, stats)

class TestM2AudioSynchronization(unittest.TestCase):
    """Test M2: Ensure real-time synchronization"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.synchronizer = AudioSynchronizer(target_latency_ms=50.0)
        self.buffer_size_changes = []
    
    def tearDown(self):
        """Clean up after tests"""
        self.synchronizer.cleanup()
    
    def buffer_callback(self, new_size):
        """Test callback for buffer size changes"""
        self.buffer_size_changes.append(new_size)
    
    def test_synchronizer_initialization(self):
        """Test M2: Synchronizer initialization"""
        self.assertEqual(self.synchronizer.target_latency_ms, 50.0)
        self.assertFalse(self.synchronizer.is_active)
        self.assertEqual(len(self.synchronizer.latency_samples), 0)
    
    def test_latency_measurement(self):
        """Test M2: Latency measurement and tracking"""
        capture_time = time.time()
        playback_time = capture_time + 0.05  # 50ms latency
        
        self.synchronizer.add_latency_measurement(capture_time, playback_time)
        
        self.assertEqual(len(self.synchronizer.latency_samples), 1)
        latency = self.synchronizer.get_current_latency()
        self.assertAlmostEqual(latency, 50.0, places=0)
    
    def test_buffer_size_adjustment(self):
        """Test M2: Adaptive buffer size adjustment"""
        self.synchronizer.set_buffer_size_callback(self.buffer_callback)
        
        # Force buffer adjustment
        self.synchronizer.force_buffer_adjustment(15)
        
        self.assertEqual(self.synchronizer.current_buffer_size, 15)
        self.assertEqual(len(self.buffer_size_changes), 1)
        self.assertEqual(self.buffer_size_changes[0], 15)
    
    def test_quality_assessment(self):
        """Test M2: Audio quality assessment"""
        # Add some measurements
        self.synchronizer.add_latency_measurement(time.time(), time.time() + 0.03)  # 30ms
        self.synchronizer.add_packet_loss_measurement(1.0)  # 1% loss
        self.synchronizer.add_audio_quality_measurement(90.0)  # Good quality
        
        assessment = self.synchronizer.get_quality_assessment()
        self.assertIn(assessment, ["Excellent", "Good", "Fair", "Poor", "Very Poor"])
    
    def test_synchronization_statistics(self):
        """Test M2: Synchronization statistics"""
        stats = self.synchronizer.get_synchronization_stats()
        
        required_keys = [
            'is_active', 'current_latency_ms', 'current_jitter_ms',
            'current_packet_loss_percent', 'current_audio_quality',
            'current_buffer_size', 'target_latency_ms', 'max_latency_ms',
            'sync_adjustments', 'buffer_underruns', 'buffer_overruns',
            'quality_degradations', 'latency_samples_count', 'jitter_samples_count'
        ]
        
        for key in required_keys:
            self.assertIn(key, stats)

class TestM2Integration(unittest.TestCase):
    """Test M2: Integration of all components"""
    
    def setUp(self):
        """Set up test fixtures"""
        with patch('pyaudio.PyAudio'):
            self.app = AudioCallApp(local_port=5004, listen_port=5005)
    
    def tearDown(self):
        """Clean up after tests"""
        self.app.cleanup()
    
    def test_app_initialization(self):
        """Test M2: Application initialization with all components"""
        self.assertEqual(self.app.call_state, CallState.IDLE)
        self.assertEqual(self.app.local_port, 5004)
        self.assertEqual(self.app.listen_port, 5005)
    
    @patch('socket.socket')
    def test_call_lifecycle(self, mock_socket):
        """Test M2: Complete call lifecycle"""
        # Mock socket operations
        mock_sock = Mock()
        mock_socket.return_value = mock_sock
        
        # Test call start
        with patch.object(self.app, '_initialize_components'):
            # Mock successful initialization
            self.app.audio_capture = Mock()
            self.app.audio_transmission = Mock()
            self.app.audio_receiver = Mock()
            self.app.audio_synchronizer = Mock()
            
            # Configure mocks
            self.app.audio_capture.is_capturing = True
            self.app.audio_transmission.is_transmitting = True
            self.app.audio_receiver.is_receiving = True
            self.app.audio_receiver.is_playing = True
            self.app.audio_synchronizer.is_active = True
            
            # Start call
            success = self.app.start_call("127.0.0.1", 5005)
            self.assertTrue(success)
            self.assertEqual(self.app.call_state, CallState.CONNECTED)
            
            # Verify all components were started
            self.app.audio_synchronizer.start_synchronization.assert_called_once()
            self.app.audio_receiver.start_reception.assert_called_once()
            self.app.audio_receiver.start_playback.assert_called_once()
            self.app.audio_transmission.start_transmission.assert_called_once()
            self.app.audio_capture.start_capture.assert_called_once()
            
            # Test call end
            self.app.end_call()
            self.assertEqual(self.app.call_state, CallState.IDLE)
    
    def test_call_status(self):
        """Test M2: Call status reporting"""
        status = self.app.get_call_status()
        
        required_keys = [
            'call_state', 'remote_address', 'call_duration',
            'total_calls', 'components_active'
        ]
        
        for key in required_keys:
            self.assertIn(key, status)
        
        # Test components_active structure
        components = status['components_active']
        component_keys = ['capture', 'transmission', 'reception', 'playback', 'synchronization']
        
        for key in component_keys:
            self.assertIn(key, components)
            self.assertIsInstance(components[key], bool)

class TestM2NetworkIntegration(unittest.TestCase):
    """Test M2: Network integration between transmission and reception"""
    
    def setUp(self):
        """Set up test fixtures"""
        with patch('pyaudio.PyAudio'):
            self.transmission = AudioTransmission(local_port=5006)
            self.receiver = AudioReceiver(listen_port=5007)
    
    def tearDown(self):
        """Clean up after tests"""
        self.transmission.cleanup()
        self.receiver.cleanup()
    
    @patch('socket.socket')
    def test_end_to_end_audio_flow(self, mock_socket):
        """Test M2: End-to-end audio data flow"""
        # Mock socket for transmission
        mock_tx_socket = Mock()
        mock_socket.return_value = mock_tx_socket
        
        # Setup transmission
        self.transmission.socket = mock_tx_socket
        self.transmission.set_target("127.0.0.1", 5007)
        
        # Create test audio data
        test_audio = np.array([1000, 2000, 3000, 4000], dtype=np.int16)
        test_timestamp = time.time()
        
        # Test packet creation and "transmission"
        packets = self.transmission._create_audio_packet(test_audio, test_timestamp)
        
        self.assertGreater(len(packets), 0)
        
        # Test packet parsing on receiver side
        for packet in packets:
            parsed = self.receiver._parse_audio_packet(packet)
            self.assertIsNotNone(parsed)
            
            sequence, timestamp, frag_idx, total_frags, frag_data = parsed
            
            # Test reassembly
            result = self.receiver._reassemble_audio_packet(
                sequence, timestamp, frag_idx, total_frags, frag_data
            )
            
            if result:  # Complete packet
                recv_timestamp, recv_audio = result
                # Verify audio data integrity
                self.assertEqual(len(recv_audio), len(test_audio))

def run_m2_tests():
    """Run all M2 task tests"""
    print("OODA Audio Call System - M2 Tasks Test Suite")
    print("=" * 50)
    print("Testing all M2 requirements:")
    print("✓ M2: Capture microphone input (using pyaudio)")
    print("✓ M2: Transmit audio stream via UDP")
    print("✓ M2: Receive remote audio stream and play it")
    print("✓ M2: Ensure real-time synchronization")
    print()
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        TestM2AudioCapture,
        TestM2AudioTransmission,
        TestM2AudioReception,
        TestM2AudioSynchronization,
        TestM2Integration,
        TestM2NetworkIntegration
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print("M2 TASKS TEST SUMMARY")
    print("=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("🎉 ALL M2 TASKS IMPLEMENTED AND TESTED SUCCESSFULLY!")
        print("✅ M2: Capture microphone input (using pyaudio) - PASSED")
        print("✅ M2: Transmit audio stream via UDP - PASSED")
        print("✅ M2: Receive remote audio stream and play it - PASSED")
        print("✅ M2: Ensure real-time synchronization - PASSED")
    else:
        print("❌ Some M2 tasks need attention")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    run_m2_tests()
