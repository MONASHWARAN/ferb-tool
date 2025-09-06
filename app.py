#!/usr/bin/env python3
"""
ADB Log Interaction Tool - Web Interface
Flask backend with Socket.IO for real-time communication
"""

import os
import sys
import subprocess
import threading
import time
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import signal

@dataclass
class DeviceInfo:
    """Device information structure"""
    device_id: str
    os_type: str
    status: str

class ADBManager:
    """Manages ADB operations and device interactions"""
    
    def __init__(self, socketio):
        self.socketio = socketio
        self.devices: List[DeviceInfo] = []
        self.current_device: Optional[DeviceInfo] = None
        self.log_process: Optional[subprocess.Popen] = None
        self.logging_active = False
        self.log_buffer: List[str] = []
        self.log_file_handle = None
        self.grep_patterns: Dict[int, str] = {}
        
    def detect_devices(self) -> List[DeviceInfo]:
        """Detect connected ADB devices and identify their OS types"""
        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return []
            
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            devices = []
            
            for line in lines:
                if line.strip() and 'device' in line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0].strip()
                        status = parts[1].strip()
                        
                        # Detect OS type
                        os_type = self.detect_os_type(device_id)
                        devices.append(DeviceInfo(device_id, os_type, status))
            
            self.devices = devices
            return devices
            
        except Exception as e:
            print(f"Error detecting devices: {e}")
            return []

    def detect_os_type(self, device_id: str) -> str:
        """Detect the OS type of a connected device"""
        try:
            # Try to detect OS type by checking system properties
            result = subprocess.run(
                ['adb', '-s', device_id, 'shell', 'getprop', 'ro.product.model'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                model = result.stdout.strip().lower()
                
                if 'vega' in model or 'echo' in model:
                    return 'VEGA'
                elif 'fire' in model or 'kindle' in model:
                    return 'FOS'
                elif 'puffin' in model:
                    return 'Puffin'
            
            # Fallback: check for specific directories
            vega_check = subprocess.run(
                ['adb', '-s', device_id, 'shell', 'test', '-d', '/var/lib/data'],
                capture_output=True, timeout=3
            )
            if vega_check.returncode == 0:
                return 'VEGA'
            
            fos_check = subprocess.run(
                ['adb', '-s', device_id, 'shell', 'test', '-d', '/system/priv-app'],
                capture_output=True, timeout=3
            )
            if fos_check.returncode == 0:
                return 'FOS'
                
            return 'Puffin'  # Default fallback
            
        except Exception:
            return 'Unknown'

    def start_logging(self, device: dict, filename: Optional[str] = None, grep_patterns: Dict[int, str] = None):
        """Start ADB logging"""
        if self.logging_active:
            self.socketio.emit('error', {'message': 'Logging is already active'})
            return False
        
        self.current_device = DeviceInfo(**device)
        self.grep_patterns = grep_patterns or {}
        
        try:
            # Determine the correct ADB command based on OS type
            if self.current_device.os_type.lower() == 'vega':
                cmd = ['adb', '-s', self.current_device.device_id, 'shell', 'journalctl', '-f']
            else:  # FOS & Puffin
                cmd = ['adb', '-s', self.current_device.device_id, 'logcat']
            
            # Open log file if filename provided
            if filename:
                self.log_file_handle = open(filename, 'w')
            
            # Start the logging process
            self.log_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                text=True, bufsize=1
            )
            
            self.logging_active = True
            self.log_buffer = []
            
            # Start log processing in a separate thread
            threading.Thread(target=self._process_logs, daemon=True).start()
            
            self.socketio.emit('logging_status', {
                'status': 'started',
                'message': f'Logging started for {self.current_device.device_id} ({self.current_device.os_type})'
            })
            
            return True
            
        except Exception as e:
            self.socketio.emit('error', {'message': f'Error starting log capture: {str(e)}'})
            return False

    def _process_logs(self):
        """Process logs in background thread"""
        try:
            while self.logging_active and self.log_process and self.log_process.poll() is None:
                if self.log_process.stdout:
                    line = self.log_process.stdout.readline()
                    if line:
                        line = line.strip()
                        
                        # Add to buffer
                        self.log_buffer.append(line)
                        
                        # Save to file if specified
                        if self.log_file_handle:
                            try:
                                self.log_file_handle.write(line + '\n')
                                self.log_file_handle.flush()
                            except Exception as e:
                                print(f"Error writing to file: {e}")
                        
                        # Send to frontend
                        timestamp = time.strftime("%H:%M:%S")
                        self.socketio.emit('log_line', {
                            'line': line,
                            'timestamp': timestamp
                        })
                        
                        # Check grep patterns
                        self._check_grep_patterns(line, timestamp)
                        
                        # Limit buffer size
                        if len(self.log_buffer) > 10000:
                            self.log_buffer = self.log_buffer[-5000:]
                            
        except Exception as e:
            self.socketio.emit('error', {'message': f'Error processing logs: {str(e)}'})

    def _check_grep_patterns(self, line: str, timestamp: str):
        """Check if line matches any grep patterns"""
        for pattern_id, pattern in self.grep_patterns.items():
            if pattern and re.search(pattern, line, re.IGNORECASE):
                self.socketio.emit('grep_match', {
                    'pattern_id': pattern_id,
                    'pattern': pattern,
                    'line': line,
                    'timestamp': timestamp
                })

    def stop_logging(self):
        """Stop ADB logging"""
        self.logging_active = False
        
        if self.log_process:
            self.log_process.terminate()
            try:
                self.log_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.log_process.kill()
            self.log_process = None
        
        if self.log_file_handle:
            try:
                self.log_file_handle.close()
            except Exception:
                pass
            self.log_file_handle = None
        
        log_count = len(self.log_buffer)
        self.socketio.emit('logging_status', {
            'status': 'stopped',
            'message': f'Logging stopped. Captured {log_count} log lines'
        })

    def extract_chr_db(self, device: dict, os_type: str):
        """Extract CHR database file based on OS type"""
        device_info = DeviceInfo(**device)
        
        # Define extraction paths based on OS type
        source_paths = {
            'FOS': "/data/data/com.amazon.alexahybridremoteskill/files/customerHomeRegistry.db",
            'VEGA': "/var/lib/data/alexahybrid/smartHomeSkill/customerHomeRegistry.db",
            'Puffin': "/data/alexahybrid/files/smartHomeSkill/customerHomeRegistry.db"
        }
        
        if os_type not in source_paths:
            self.socketio.emit('chr_status', {
                'status': 'error',
                'message': f'Unknown OS type: {os_type}'
            })
            return
        
        source_path = source_paths[os_type]
        output_filename = f"CHR_{os_type}_{device_info.device_id}_{int(time.time())}.db"
        
        try:
            self.socketio.emit('chr_status', {
                'status': 'extracting',
                'message': f'Extracting CHR DB for {os_type} from {device_info.device_id}'
            })
            
            cmd = ['adb', '-s', device_info.device_id, 'pull', source_path, output_filename]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                file_size = os.path.getsize(output_filename) if os.path.exists(output_filename) else 0
                self.socketio.emit('chr_status', {
                    'status': 'success',
                    'message': f'CHR database extracted: {output_filename} ({file_size} bytes)'
                })
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                self.socketio.emit('chr_status', {
                    'status': 'error',
                    'message': f'Failed to extract CHR database: {error_msg}'
                })
                
        except subprocess.TimeoutExpired:
            self.socketio.emit('chr_status', {
                'status': 'error',
                'message': 'CHR database extraction timed out'
            })
        except Exception as e:
            self.socketio.emit('chr_status', {
                'status': 'error',
                'message': f'Error extracting CHR database: {str(e)}'
            })

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'adb_log_tool_secret_key'

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize ADB Manager
adb_manager = ADBManager(socketio)

@app.route('/')
def index():
    """Serve the main page"""
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('connect_response', {'status': 'Connected to ADB Log Tool'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')
    # Stop logging if active
    if adb_manager.logging_active:
        adb_manager.stop_logging()

@socketio.on('detect_devices')
def handle_detect_devices():
    """Handle device detection request"""
    devices = adb_manager.detect_devices()
    emit('devices', {'devices': [asdict(device) for device in devices]})

@socketio.on('start_logging')
def handle_start_logging(data):
    """Handle start logging request"""
    device = data.get('device')
    filename = data.get('filename')
    grep_patterns = data.get('grep_patterns', {})
    
    # Convert string keys to integers
    grep_patterns = {int(k): v for k, v in grep_patterns.items() if v}
    
    if not device:
        emit('error', {'message': 'No device selected'})
        return
    
    adb_manager.start_logging(device, filename, grep_patterns)

@socketio.on('stop_logging')
def handle_stop_logging():
    """Handle stop logging request"""
    adb_manager.stop_logging()

@socketio.on('extract_chr')
def handle_extract_chr(data):
    """Handle CHR extraction request"""
    device = data.get('device')
    os_type = data.get('os_type')
    
    if not device or not os_type:
        emit('error', {'message': 'Device and OS type required'})
        return
    
    adb_manager.extract_chr_db(device, os_type)

@socketio.on('grep_match_found')
def handle_grep_match(data):
    """Handle grep match found from frontend"""
    # This is handled by the frontend, but we can log it
    pattern_id = data.get('pattern_id')
    pattern = data.get('pattern')
    print(f"Grep match found for pattern {pattern_id}: {pattern}")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\nShutting down ADB Log Tool...")
    if adb_manager.logging_active:
        adb_manager.stop_logging()
    sys.exit(0)

if __name__ == '__main__':
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal_handler)
    
    # Check if ADB is available
    try:
        result = subprocess.run(['adb', 'version'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print("❌ ADB is not installed or not accessible")
            print("Please install Android Debug Bridge (ADB) to use this tool")
            sys.exit(1)
        print("✅ ADB is available")
    except Exception as e:
        print(f"❌ Error checking ADB: {e}")
        sys.exit(1)
    
    print("🚀 Starting ADB Log Tool Web Interface...")
    print("🌐 Access the tool at: http://localhost:5000")
    
    # Run the Flask-SocketIO app
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)