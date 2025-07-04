# Bidirectional Audio Call Application

A Python-based application for real-time audio communication over local networks without requiring internet connectivity.

## Features

- **Bidirectional Audio Calls**: Full-duplex audio communication between peers
- **Microphone Capture**: Real-time audio input using PyAudio
- **Network Transmission**: UDP-based audio streaming with packet management
- **Audio Playback**: Low-latency audio output with buffering
- **Real-time Synchronization**: Adaptive buffering and jitter management
- **Network Discovery**: Automatic peer discovery on local networks
- **Simple Interface**: Command-line interface for easy testing

## Requirements

- Python 3.7+
- Audio input device (microphone)
- Audio output device (speakers/headphones)
- Local network connectivity (Wi-Fi or Ethernet)

## Installation

1. **Clone or download the project files**

2. **Run the setup script**:
   ```bash
   python setup.py
   ```
   
   This will install all required dependencies:
   - pyaudio (audio capture/playback)
   - aiortc (WebRTC support)
   - numpy (audio processing)
   - websockets (network communication)

3. **Verify audio devices**:
   The setup script will check for available audio devices. Make sure you have both input and output devices available.

## Usage

### Interactive Mode
```bash
python audio_call_cli.py
```

This starts an interactive menu where you can:
1. Discover peers on the network
2. Call a specific peer
3. Listen for incoming calls
4. Exit the application

### Command Line Options

**Discover peers**:
```bash
python audio_call_cli.py discover
```

**Listen for incoming calls**:
```bash
python audio_call_cli.py listen
```

**Call a specific peer**:
```bash
python audio_call_cli.py call 192.168.1.100
```

## How It Works

### Audio Capture (M2)
- Uses PyAudio to capture microphone input
- Configurable sample rate (default: 44.1kHz)
- Real-time audio buffering with queue management
- Automatic device detection and initialization

### Audio Transmission (M2)
- UDP-based packet transmission for low latency
- Packet sequencing and timestamp management
- Automatic packet fragmentation for large audio chunks
- Configurable transmission parameters

### Audio Reception and Playback (M2)
- UDP packet reception with multi-threading
- Packet reassembly for fragmented audio data
- Real-time audio playback through speakers
- Buffer management to prevent underruns/overruns

### Real-time Synchronization (M2)
- Adaptive buffering based on network conditions
- Jitter measurement and compensation
- Latency monitoring and adjustment
- Packet dropping for old/delayed packets

### Network Discovery
- UDP broadcast for peer discovery
- Automatic local IP detection
- Periodic presence announcements
- Peer timeout and cleanup

## Network Configuration

The application uses the following ports:
- **Port 5000**: Audio data transmission (UDP)
- **Port 5001**: Network discovery (UDP broadcast)

Make sure these ports are not blocked by firewalls.

## Testing

### Single Machine Testing
1. Start the first instance in listen mode:
   ```bash
   python audio_call_cli.py listen
   ```

2. Start the second instance and call localhost:
   ```bash
   python audio_call_cli.py call 127.0.0.1
   ```

### Network Testing
1. On the first computer, start in listen mode:
   ```bash
   python audio_call_cli.py listen
   ```

2. On the second computer, discover peers:
   ```bash
   python audio_call_cli.py discover
   ```

3. Call the discovered peer:
   ```bash
   python audio_call_cli.py call <peer_ip>
   ```

## Troubleshooting

### No Audio Devices Found
- Check that your microphone and speakers are properly connected
- Verify audio drivers are installed and working
- Try running the setup script again to check device status

### Network Discovery Issues
- Ensure both computers are on the same local network
- Check firewall settings for UDP ports 5000 and 5001
- Verify network connectivity with ping

### Audio Quality Issues
- Check microphone and speaker volume levels
- Reduce background noise
- Ensure stable network connection
- Monitor application logs for buffer underruns

### High Latency
- Check network quality and bandwidth
- Reduce audio buffer sizes in configuration
- Ensure no other high-bandwidth applications are running

## Configuration

You can modify audio parameters in the respective modules:

**Audio Capture** (`audio_capture.py`):
- `sample_rate`: Audio sample rate (default: 44100 Hz)
- `channels`: Number of channels (default: 1 - mono)
- `chunk_size`: Audio chunk size (default: 1024 samples)

**Audio Transmission** (`audio_transmission.py`):
- `port`: UDP port for transmission (default: 5000)
- `max_packet_size`: Maximum UDP packet size (default: 1024 bytes)

**Audio Synchronization** (`audio_synchronizer.py`):
- `target_latency_ms`: Target latency (default: 100ms)
- `max_jitter_ms`: Maximum acceptable jitter (default: 50ms)

## Architecture

```
┌─────────────────┐    UDP/5000     ┌─────────────────┐
│   Computer A    │ ◄──────────────► │   Computer B    │
│                 │                 │                 │
│ ┌─────────────┐ │                 │ ┌─────────────┐ │
│ │ Microphone  │ │                 │ │ Microphone  │ │
│ └─────────────┘ │                 │ └─────────────┘ │
│ ┌─────────────┐ │                 │ ┌─────────────┐ │
│ │ Speakers    │ │                 │ │ Speakers    │ │
│ └─────────────┘ │                 │ └─────────────┘ │
│                 │                 │                 │
│ Audio Call App  │                 │ Audio Call App  │
└─────────────────┘                 └─────────────────┘
```

## License

This project is for educational and development purposes.
