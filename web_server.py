"""
OODA Audio Call System - Web Server
Serves the web interface and provides REST API for audio call functionality

This web server integrates the web interface with the Python M2 backend:
- Serves static web files (HTML, CSS, JS)
- Provides REST API endpoints for call management
- WebSocket support for real-time updates
- Integrates all M2 components
"""

import asyncio
import json
import logging
import os
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional

# Web server imports
try:
    from aiohttp import web, WSMsgType
    from aiohttp.web import Application, Request, Response, WebSocketResponse
    from aiohttp_cors import setup as cors_setup, ResourceOptions
except ImportError:
    print("Installing required web server dependencies...")
    import subprocess
    subprocess.run(["pip", "install", "aiohttp", "aiohttp-cors"], check=True)
    from aiohttp import web, WSMsgType
    from aiohttp.web import Application, Request, Response, WebSocketResponse
    from aiohttp_cors import setup as cors_setup, ResourceOptions

# Import our M2 components
from audio_call_app_demo import AudioCallApp, CallState

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OODAWebServer:
    """OODA Web Server with integrated audio call functionality"""
    
    def __init__(self, host='localhost', port=8080, audio_port=5000):
        self.host = host
        self.port = port
        self.audio_port = audio_port
        self.app = None
        self.audio_app = None
        self.websockets = set()
        self.web_interface_path = Path(__file__).parent / "web_interface"
        
        # Initialize audio call app
        self.audio_app = AudioCallApp(local_port=audio_port, listen_port=audio_port + 1)
        
        logger.info(f"🌐 OODA Web Server initialized: {host}:{port}")
        logger.info(f"🎵 Audio system: ports {audio_port}-{audio_port + 1}")
    
    def create_app(self) -> Application:
        """Create and configure the web application"""
        app = web.Application()
        
        # Setup CORS
        cors = cors_setup(app, defaults={
            "*": ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # Static file routes
        app.router.add_get('/', self.serve_index)
        app.router.add_static('/', self.web_interface_path, name='static')
        
        # API routes
        app.router.add_get('/api/status', self.get_status)
        app.router.add_post('/api/call/start', self.start_call)
        app.router.add_post('/api/call/end', self.end_call)
        app.router.add_get('/api/devices', self.get_devices)
        app.router.add_post('/api/test-connectivity', self.test_connectivity)
        app.router.add_get('/api/discovery', self.discover_peers)
        
        # WebSocket route
        app.router.add_get('/ws', self.websocket_handler)
        
        # Add CORS to all routes
        for route in list(app.router.routes()):
            cors.add(route)
        
        self.app = app
        return app
    
    async def serve_index(self, request: Request) -> Response:
        """Serve the main index.html file"""
        try:
            index_path = self.web_interface_path / "index.html"
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Response(text=content, content_type='text/html')
        except Exception as e:
            logger.error(f"Error serving index: {e}")
            return Response(text="Error loading page", status=500)
    
    async def get_status(self, request: Request) -> Response:
        """Get current system and call status"""
        try:
            status = self.audio_app.get_call_status()
            
            # Add web server info
            status['web_server'] = {
                'host': self.host,
                'port': self.port,
                'audio_port': self.audio_port,
                'connected_clients': len(self.websockets)
            }
            
            return web.json_response(status)
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def start_call(self, request: Request) -> Response:
        """Start an audio call"""
        try:
            data = await request.json()
            remote_ip = data.get('ip', '127.0.0.1')
            remote_port = int(data.get('port', self.audio_port + 1))
            
            logger.info(f"🚀 Web API: Starting call to {remote_ip}:{remote_port}")
            
            success = self.audio_app.start_call(remote_ip, remote_port)
            
            if success:
                # Notify all connected WebSocket clients
                await self.broadcast_status_update()
                return web.json_response({
                    'success': True,
                    'message': f'Call started to {remote_ip}:{remote_port}',
                    'call_state': self.audio_app.call_state.value
                })
            else:
                return web.json_response({
                    'success': False,
                    'message': 'Failed to start call',
                    'call_state': self.audio_app.call_state.value
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error starting call: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def end_call(self, request: Request) -> Response:
        """End the current call"""
        try:
            logger.info("🛑 Web API: Ending call")
            
            self.audio_app.end_call()
            
            # Notify all connected WebSocket clients
            await self.broadcast_status_update()
            
            return web.json_response({
                'success': True,
                'message': 'Call ended',
                'call_state': self.audio_app.call_state.value
            })
            
        except Exception as e:
            logger.error(f"Error ending call: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_devices(self, request: Request) -> Response:
        """Get available audio devices"""
        try:
            devices = self.audio_app.get_audio_devices()
            return web.json_response(devices)
        except Exception as e:
            logger.error(f"Error getting devices: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def test_connectivity(self, request: Request) -> Response:
        """Test connectivity to a remote peer"""
        try:
            data = await request.json()
            remote_ip = data.get('ip', '127.0.0.1')
            remote_port = int(data.get('port', self.audio_port + 1))
            
            logger.info(f"🔗 Web API: Testing connectivity to {remote_ip}:{remote_port}")
            
            success = self.audio_app.test_connectivity(remote_ip, remote_port)
            
            return web.json_response({
                'success': success,
                'message': f'Connectivity test {"passed" if success else "failed"}',
                'target': f'{remote_ip}:{remote_port}'
            })
            
        except Exception as e:
            logger.error(f"Error testing connectivity: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def discover_peers(self, request: Request) -> Response:
        """Discover peers on the local network"""
        try:
            # Simulate peer discovery for demo
            peers = [
                {
                    'ip': '192.168.1.100',
                    'port': self.audio_port + 1,
                    'name': 'Desktop-PC',
                    'status': 'available',
                    'last_seen': time.time()
                },
                {
                    'ip': '192.168.1.101',
                    'port': self.audio_port + 1,
                    'name': 'Laptop-User',
                    'status': 'busy',
                    'last_seen': time.time() - 30
                },
                {
                    'ip': '127.0.0.1',
                    'port': self.audio_port + 1,
                    'name': 'Local-Test',
                    'status': 'available',
                    'last_seen': time.time()
                }
            ]
            
            return web.json_response({
                'peers': peers,
                'discovery_time': time.time()
            })
            
        except Exception as e:
            logger.error(f"Error discovering peers: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def websocket_handler(self, request: Request) -> WebSocketResponse:
        """Handle WebSocket connections for real-time updates"""
        ws = WebSocketResponse()
        await ws.prepare(request)
        
        self.websockets.add(ws)
        logger.info(f"🔌 WebSocket client connected. Total: {len(self.websockets)}")
        
        try:
            # Send initial status
            status = self.audio_app.get_call_status()
            await ws.send_str(json.dumps({
                'type': 'status_update',
                'data': status
            }))
            
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        # Handle WebSocket messages if needed
                        logger.debug(f"WebSocket message: {data}")
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid WebSocket message: {msg.data}")
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
                    break
                    
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self.websockets.discard(ws)
            logger.info(f"🔌 WebSocket client disconnected. Total: {len(self.websockets)}")
        
        return ws
    
    async def broadcast_status_update(self):
        """Broadcast status update to all connected WebSocket clients"""
        if not self.websockets:
            return
        
        try:
            status = self.audio_app.get_call_status()
            message = json.dumps({
                'type': 'status_update',
                'data': status,
                'timestamp': time.time()
            })
            
            # Send to all connected clients
            disconnected = set()
            for ws in self.websockets:
                try:
                    await ws.send_str(message)
                except Exception as e:
                    logger.warning(f"Failed to send to WebSocket client: {e}")
                    disconnected.add(ws)
            
            # Remove disconnected clients
            self.websockets -= disconnected
            
        except Exception as e:
            logger.error(f"Error broadcasting status: {e}")
    
    async def start_status_broadcaster(self):
        """Start periodic status broadcasting"""
        while True:
            try:
                await asyncio.sleep(2.0)  # Broadcast every 2 seconds
                if self.websockets and self.audio_app.call_state == CallState.CONNECTED:
                    await self.broadcast_status_update()
            except Exception as e:
                logger.error(f"Status broadcaster error: {e}")
    
    async def start_server(self):
        """Start the web server"""
        try:
            app = self.create_app()
            
            # Start status broadcaster
            asyncio.create_task(self.start_status_broadcaster())
            
            logger.info(f"🌐 Starting OODA Web Server on http://{self.host}:{self.port}")
            logger.info(f"🎵 Audio call system ready on ports {self.audio_port}-{self.audio_port + 1}")
            
            runner = web.AppRunner(app)
            await runner.setup()
            
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            
            logger.info("✅ OODA Web Server started successfully!")
            logger.info(f"📱 Open your browser to: http://{self.host}:{self.port}")
            
            return runner
            
        except Exception as e:
            logger.error(f"Failed to start web server: {e}")
            raise
    
    def cleanup(self):
        """Clean up resources"""
        if self.audio_app:
            self.audio_app.cleanup()

async def main():
    """Main function to run the OODA web server"""
    print("🎉 OODA AUDIO CALL SYSTEM - WEB SERVER")
    print("=" * 60)
    print("Starting web interface with integrated M2 backend:")
    print("✅ M2: Capture microphone input (using pyaudio)")
    print("✅ M2: Transmit audio stream via UDP")
    print("✅ M2: Receive remote audio stream and play it")
    print("✅ M2: Ensure real-time synchronization")
    print("=" * 60)
    print()
    
    server = OODAWebServer(host='localhost', port=8080, audio_port=5000)
    
    try:
        runner = await server.start_server()
        
        # Keep the server running
        print("🚀 Server is running! Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down OODA Web Server...")
    except Exception as e:
        print(f"❌ Server error: {e}")
    finally:
        server.cleanup()
        if 'runner' in locals():
            await runner.cleanup()
        print("✅ Server shutdown completed.")

if __name__ == "__main__":
    asyncio.run(main())
