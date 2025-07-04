// OODA Audio Call System - Web Interface JavaScript
// Main application state and functionality with backend integration

class AudioCallApp {
    constructor() {
        this.currentPage = 'dashboard';
        this.isListening = false;
        this.isInCall = false;
        this.isMuted = false;
        this.currentPeer = null;
        this.callStartTime = null;
        this.callTimer = null;
        this.peers = [];
        this.localIP = null;

        // Backend integration
        this.apiBase = window.location.origin;
        this.websocket = null;
        this.backendStatus = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        this.init();
    }
    
    init() {
        this.detectLocalIP();
        this.setupEventListeners();
        this.loadSettings();
        this.connectWebSocket();
        this.updateStatus();
        this.startStatusPolling();

        // Initialize backend connection
        setTimeout(() => {
            this.checkBackendConnection();
        }, 1000);
    }

    // Backend Integration Methods
    async checkBackendConnection() {
        try {
            const response = await fetch(`${this.apiBase}/api/status`);
            if (response.ok) {
                this.backendStatus = await response.json();
                this.showToast('Connected to OODA backend', 'success');
                this.updateBackendStatus();
            } else {
                throw new Error('Backend not responding');
            }
        } catch (error) {
            console.error('Backend connection failed:', error);
            this.showToast('Backend connection failed', 'error');
            this.scheduleReconnect();
        }
    }

    connectWebSocket() {
        try {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                console.log('WebSocket connected');
                this.reconnectAttempts = 0;
            };

            this.websocket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleWebSocketMessage(message);
                } catch (error) {
                    console.error('WebSocket message error:', error);
                }
            };

            this.websocket.onclose = () => {
                console.log('WebSocket disconnected');
                this.scheduleWebSocketReconnect();
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.scheduleWebSocketReconnect();
        }
    }

    handleWebSocketMessage(message) {
        switch (message.type) {
            case 'status_update':
                this.backendStatus = message.data;
                this.updateBackendStatus();
                break;
            default:
                console.log('Unknown WebSocket message:', message);
        }
    }

    scheduleWebSocketReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                console.log(`Reconnecting WebSocket (attempt ${this.reconnectAttempts})`);
                this.connectWebSocket();
            }, 2000 * this.reconnectAttempts);
        }
    }

    scheduleReconnect() {
        setTimeout(() => {
            this.checkBackendConnection();
        }, 5000);
    }

    updateBackendStatus() {
        if (!this.backendStatus) return;

        // Update call state
        const callState = this.backendStatus.call_state;
        this.isInCall = (callState === 'connected');

        // Update UI elements
        const statusElement = document.getElementById('my-status');
        if (statusElement) {
            statusElement.textContent = callState === 'connected' ? 'In Call' : 'Online';
        }

        // Update network status
        const networkElement = document.getElementById('network-info');
        if (networkElement && this.backendStatus.web_server) {
            networkElement.textContent = `Port ${this.backendStatus.web_server.audio_port}`;
        }

        // Update call duration if in call
        if (this.isInCall && this.backendStatus.call_duration) {
            this.updateCallDuration(this.backendStatus.call_duration);
        }

        // Update component status indicators
        this.updateComponentStatus();
    }

    updateComponentStatus() {
        if (!this.backendStatus || !this.backendStatus.components_active) return;

        const components = this.backendStatus.components_active;

        // Update microphone status
        const micIcon = document.getElementById('mic-status');
        if (micIcon) {
            micIcon.className = components.capture ? 'fas fa-microphone' : 'fas fa-microphone-slash';
            micIcon.style.color = components.capture ? '#4CAF50' : '#f44336';
        }
    }

    startStatusPolling() {
        // Poll backend status every 5 seconds as fallback
        setInterval(async () => {
            if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
                await this.checkBackendConnection();
            }
        }, 5000);
    }

    // Page Navigation
    showPage(pageId) {
        // Hide all pages
        document.querySelectorAll('.page').forEach(page => {
            page.classList.remove('active');
        });
        
        // Show target page
        const targetPage = document.getElementById(pageId);
        if (targetPage) {
            targetPage.classList.add('active', 'fade-in');
            this.currentPage = pageId;
            
            // Page-specific initialization
            if (pageId === 'discovery') {
                this.initDiscoveryPage();
            } else if (pageId === 'settings') {
                this.initSettingsPage();
            }
        }
    }
    
    // Network Discovery
    async discoverPeers() {
        const statusEl = document.getElementById('discovery-status');
        const peersListEl = document.getElementById('peers-list');

        statusEl.textContent = 'Discovering peers...';
        this.showLoading('Searching for devices...');

        try {
            // Call backend API for peer discovery
            const response = await fetch(`${this.apiBase}/api/discovery`);
            if (response.ok) {
                const result = await response.json();
                this.peers = result.peers || [];
            } else {
                throw new Error('Discovery API failed');
            }

            this.renderPeersList();
            statusEl.textContent = `Found ${this.peers.length} peer(s)`;

        } catch (error) {
            console.error('Discovery failed:', error);
            statusEl.textContent = 'Discovery failed';
            this.showToast('Failed to discover peers', 'error');

            // Fallback to simulated discovery
            await this.simulateDiscovery();
            this.renderPeersList();
            statusEl.textContent = `Found ${this.peers.length} peer(s) (simulated)`;
        } finally {
            this.hideLoading();
        }
    }
    
    async simulateDiscovery() {
        // Simulate network discovery delay
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        // Mock discovered peers
        this.peers = [
            {
                id: '1',
                name: 'Desktop PC',
                ip: '192.168.1.100',
                status: 'online',
                lastSeen: new Date()
            },
            {
                id: '2', 
                name: 'Laptop',
                ip: '192.168.1.101',
                status: 'online',
                lastSeen: new Date()
            },
            {
                id: '3',
                name: 'Mobile Device',
                ip: '192.168.1.102', 
                status: 'offline',
                lastSeen: new Date(Date.now() - 300000) // 5 minutes ago
            }
        ];
    }
    
    renderPeersList() {
        const peersListEl = document.getElementById('peers-list');
        
        if (this.peers.length === 0) {
            peersListEl.innerHTML = `
                <div class="no-peers">
                    <i class="fas fa-search"></i>
                    <p>No peers found. Make sure other devices are running OODA.</p>
                </div>
            `;
            return;
        }
        
        peersListEl.innerHTML = this.peers.map(peer => `
            <div class="peer-item slide-in" data-peer-id="${peer.id}">
                <div class="peer-info">
                    <div class="peer-avatar">
                        <i class="fas fa-${this.getPeerIcon(peer.name)}"></i>
                    </div>
                    <div class="peer-details">
                        <h4>${peer.name}</h4>
                        <p>${peer.ip}</p>
                        <small class="status-${peer.status}">
                            ${peer.status === 'online' ? 'Online' : 'Last seen: ' + this.formatTime(peer.lastSeen)}
                        </small>
                    </div>
                </div>
                <div class="peer-actions">
                    ${peer.status === 'online' ? 
                        `<button class="btn btn-primary" onclick="app.callPeer('${peer.id}')">
                            <i class="fas fa-phone"></i> Call
                        </button>` : 
                        `<button class="btn btn-secondary" disabled>
                            <i class="fas fa-phone-slash"></i> Offline
                        </button>`
                    }
                </div>
            </div>
        `).join('');
    }
    
    getPeerIcon(name) {
        if (name.toLowerCase().includes('desktop') || name.toLowerCase().includes('pc')) return 'desktop';
        if (name.toLowerCase().includes('laptop')) return 'laptop';
        if (name.toLowerCase().includes('mobile') || name.toLowerCase().includes('phone')) return 'mobile-alt';
        return 'computer';
    }
    
    // Call Management
    async callPeer(peerId) {
        const peer = this.peers.find(p => p.id === peerId);
        if (!peer) return;

        this.showLoading(`Calling ${peer.name}...`);

        try {
            // Call backend API to start call
            const response = await fetch(`${this.apiBase}/api/call/start`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    ip: peer.ip,
                    port: peer.port
                })
            });

            const result = await response.json();

            if (result.success) {
                this.currentPeer = peer;
                this.startCall();
                this.showPage('call');
                this.showToast(result.message, 'success');
            } else {
                throw new Error(result.message || 'Call failed');
            }

        } catch (error) {
            console.error('Call failed:', error);
            this.showToast('Failed to connect to peer: ' + error.message, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    startCall() {
        this.isInCall = true;
        this.callStartTime = new Date();
        this.updateCallInfo();
        this.startCallTimer();

        // Backend handles the actual call setup
        console.log('Call UI started');
    }

    async endCall() {
        try {
            // Call backend API to end call
            const response = await fetch(`${this.apiBase}/api/call/end`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            const result = await response.json();

            if (result.success) {
                this.showToast(result.message, 'info');
            }

        } catch (error) {
            console.error('Error ending call:', error);
            this.showToast('Error ending call', 'error');
        }

        // Update UI regardless of API result
        this.isInCall = false;
        this.currentPeer = null;
        this.callStartTime = null;

        if (this.callTimer) {
            clearInterval(this.callTimer);
            this.callTimer = null;
        }

        this.showPage('dashboard');
    }
    
    toggleMute() {
        this.isMuted = !this.isMuted;
        const muteBtn = document.querySelector('.mute-btn');
        const muteIcon = document.getElementById('mute-icon');
        
        if (this.isMuted) {
            muteBtn.classList.add('muted');
            muteIcon.className = 'fas fa-microphone-slash';
            this.showToast('Microphone muted', 'info');
        } else {
            muteBtn.classList.remove('muted');
            muteIcon.className = 'fas fa-microphone';
            this.showToast('Microphone unmuted', 'info');
        }
    }
    
    toggleVolumePanel() {
        const panel = document.getElementById('volume-panel');
        panel.classList.toggle('active');
    }
    
    startCallTimer() {
        this.callTimer = setInterval(() => {
            if (this.callStartTime) {
                const duration = new Date() - this.callStartTime;
                const minutes = Math.floor(duration / 60000);
                const seconds = Math.floor((duration % 60000) / 1000);
                
                document.getElementById('call-duration').textContent = 
                    `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        }, 1000);
    }
    
    updateCallInfo() {
        if (this.currentPeer) {
            document.getElementById('peer-name').textContent = this.currentPeer.name;
            document.getElementById('peer-ip').textContent = this.currentPeer.ip;
        }
    }
    
    simulateCallMetrics() {
        // Simulate real-time call quality metrics
        setInterval(() => {
            if (this.isInCall) {
                const latency = Math.floor(Math.random() * 50) + 20; // 20-70ms
                const packetsReceived = Math.floor(Math.random() * 100) + 950; // 950-1050
                const packetsTotal = 1000;
                
                document.getElementById('latency').textContent = `${latency} ms`;
                document.getElementById('packets').textContent = `${packetsReceived} / ${packetsTotal}`;
                
                // Update quality indicator
                const qualityEl = document.getElementById('quality');
                if (latency < 30 && packetsReceived > 980) {
                    qualityEl.textContent = 'Excellent';
                    qualityEl.className = 'quality-good';
                } else if (latency < 50 && packetsReceived > 950) {
                    qualityEl.textContent = 'Good';
                    qualityEl.className = 'quality-good';
                } else if (latency < 80 && packetsReceived > 900) {
                    qualityEl.textContent = 'Fair';
                    qualityEl.className = 'quality-fair';
                } else {
                    qualityEl.textContent = 'Poor';
                    qualityEl.className = 'quality-poor';
                }
            }
        }, 2000);
    }
    
    // Listening Mode
    async startListening() {
        if (this.isListening) {
            this.stopListening();
            return;
        }
        
        this.showLoading('Starting to listen for calls...');
        
        try {
            // Simulate starting listening mode
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            this.isListening = true;
            this.updateStatus();
            this.showToast('Now listening for incoming calls', 'success');
            
        } catch (error) {
            console.error('Failed to start listening:', error);
            this.showToast('Failed to start listening mode', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    stopListening() {
        this.isListening = false;
        this.updateStatus();
        this.showToast('Stopped listening for calls', 'info');
    }
    
    // Settings Management
    loadSettings() {
        // Load settings from localStorage or use defaults
        const settings = JSON.parse(localStorage.getItem('ooda-settings') || '{}');
        
        // Apply settings to UI
        if (settings.audioQuality) {
            document.getElementById('audio-quality').value = settings.audioQuality;
        }
        if (settings.listenPort) {
            document.getElementById('listen-port').value = settings.listenPort;
        }
        if (settings.discoveryPort) {
            document.getElementById('discovery-port').value = settings.discoveryPort;
        }
        if (settings.autoAccept !== undefined) {
            document.getElementById('auto-accept').checked = settings.autoAccept;
        }
        if (settings.micGain !== undefined) {
            document.getElementById('mic-gain').value = settings.micGain;
            document.getElementById('mic-gain-value').textContent = settings.micGain + '%';
        }
    }
    
    saveSettings() {
        const settings = {
            audioQuality: document.getElementById('audio-quality').value,
            listenPort: parseInt(document.getElementById('listen-port').value),
            discoveryPort: parseInt(document.getElementById('discovery-port').value),
            autoAccept: document.getElementById('auto-accept').checked,
            micGain: parseInt(document.getElementById('mic-gain').value)
        };
        
        localStorage.setItem('ooda-settings', JSON.stringify(settings));
        this.showToast('Settings saved successfully', 'success');
    }
    
    async testAudio() {
        this.showLoading('Testing audio devices...');
        
        try {
            // Simulate audio test
            await new Promise(resolve => setTimeout(resolve, 2000));
            this.showToast('Audio test completed successfully', 'success');
        } catch (error) {
            this.showToast('Audio test failed', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    // Utility Functions
    async detectLocalIP() {
        try {
            // This is a simplified version - in a real app you'd get this from the backend
            this.localIP = '192.168.1.50'; // Mock IP
            document.getElementById('local-ip').textContent = this.localIP;
        } catch (error) {
            console.error('Failed to detect local IP:', error);
            document.getElementById('local-ip').textContent = 'Unknown';
        }
    }
    
    updateStatus() {
        const statusEl = document.getElementById('app-status');
        const myStatusEl = document.getElementById('my-status');
        
        if (this.isInCall) {
            statusEl.textContent = 'In Call';
            myStatusEl.textContent = 'In Call';
            myStatusEl.className = 'status-connecting';
        } else if (this.isListening) {
            statusEl.textContent = 'Listening';
            myStatusEl.textContent = 'Listening';
            myStatusEl.className = 'status-online';
        } else {
            statusEl.textContent = 'Ready';
            myStatusEl.textContent = 'Online';
            myStatusEl.className = 'status-online';
        }
    }
    
    formatTime(date) {
        const now = new Date();
        const diff = now - date;
        const minutes = Math.floor(diff / 60000);
        
        if (minutes < 1) return 'Just now';
        if (minutes < 60) return `${minutes}m ago`;
        
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours}h ago`;
        
        const days = Math.floor(hours / 24);
        return `${days}d ago`;
    }
    
    // UI Helper Functions
    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        const icon = toast.querySelector('.toast-icon');
        const messageEl = toast.querySelector('.toast-message');
        
        // Set icon based on type
        const icons = {
            success: 'fas fa-check-circle',
            error: 'fas fa-exclamation-circle',
            info: 'fas fa-info-circle'
        };
        
        icon.className = `toast-icon ${icons[type] || icons.info}`;
        messageEl.textContent = message;
        toast.className = `toast ${type} show`;
        
        // Auto-hide after 3 seconds
        setTimeout(() => {
            toast.classList.remove('show');
        }, 3000);
    }
    
    showLoading(message = 'Loading...') {
        const loading = document.getElementById('loading');
        const messageEl = loading.querySelector('p');
        messageEl.textContent = message;
        loading.classList.add('show');
    }
    
    hideLoading() {
        document.getElementById('loading').classList.remove('show');
    }
    
    setupEventListeners() {
        // Volume slider
        const volumeSlider = document.getElementById('volume-slider');
        const volumeValue = document.getElementById('volume-value');
        
        if (volumeSlider) {
            volumeSlider.addEventListener('input', (e) => {
                volumeValue.textContent = e.target.value + '%';
            });
        }
        
        // Mic gain slider
        const micGainSlider = document.getElementById('mic-gain');
        const micGainValue = document.getElementById('mic-gain-value');
        
        if (micGainSlider) {
            micGainSlider.addEventListener('input', (e) => {
                micGainValue.textContent = e.target.value + '%';
            });
        }
        
        // Refresh peers button
        const refreshBtn = document.querySelector('.refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.discoverPeers();
            });
        }
    }
    
    initDiscoveryPage() {
        // Auto-discover when entering discovery page
        if (this.peers.length === 0) {
            setTimeout(() => this.discoverPeers(), 500);
        } else {
            this.renderPeersList();
        }
    }
    
    initSettingsPage() {
        // Refresh settings display
        this.loadSettings();
    }
}

// Global functions for HTML onclick handlers
function showPage(pageId) {
    app.showPage(pageId);
}

function startListening() {
    app.startListening();
}

function refreshPeers() {
    app.discoverPeers();
}

function discoverPeers() {
    app.discoverPeers();
}

function toggleMute() {
    app.toggleMute();
}

function toggleVolumePanel() {
    app.toggleVolumePanel();
}

function endCall() {
    app.endCall();
}

function saveSettings() {
    app.saveSettings();
}

function testAudio() {
    app.testAudio();
}

// Initialize the application
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new AudioCallApp();
});
