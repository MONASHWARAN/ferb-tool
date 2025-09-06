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
import socket
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
        """Robust ADB device detection with connection validation"""
        devices = []
        try:
            # First, try to start ADB server if not running
            try:
                subprocess.run(['adb', 'start-server'], capture_output=True, timeout=5)
            except:
                pass  # Continue even if start-server fails
            
            # Get device list
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                print(f"ADB devices command failed: {result.stderr}")
                return []
            
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            
            for line in lines:
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0].strip()
                        status = parts[1].strip()
                        
                        # Only process devices that are actually connected
                        if status in ['device', 'recovery', 'sideload']:
                            # Validate device connection with a quick test
                            if self._validate_device_connection(device_id):
                                os_type = self.detect_os_type(device_id)
                                devices.append(DeviceInfo(device_id, os_type, status))
                            else:
                                # Device listed but not responsive
                                devices.append(DeviceInfo(device_id, 'Unknown', 'unresponsive'))
            
            # Update internal device list
            old_device_count = len(self.devices)
            self.devices = devices
            
            # Log device changes
            if len(devices) != old_device_count:
                print(f"Device count changed: {old_device_count} -> {len(devices)}")
                
            return devices
            
        except subprocess.TimeoutExpired:
            print("ADB device detection timed out")
            return []
        except Exception as e:
            print(f"Error detecting devices: {e}")
            return []
            
    def _validate_device_connection(self, device_id: str) -> bool:
        """Validate that device is actually responsive"""
        try:
            # Quick test to see if device responds
            result = subprocess.run(
                ['adb', '-s', device_id, 'shell', 'echo', 'test'],
                capture_output=True, text=True, timeout=3
            )
            return result.returncode == 0 and 'test' in result.stdout
        except:
            return False

    def detect_os_type(self, device_id: str) -> str:
        """Robust OS type detection with multiple fallback methods"""
        detection_methods = [
            # Method 1: Check product model
            {
                'name': 'product_model',
                'cmd': ['adb', '-s', device_id, 'shell', 'getprop', 'ro.product.model'],
                'timeout': 5
            },
            # Method 2: Check build fingerprint
            {
                'name': 'build_fingerprint', 
                'cmd': ['adb', '-s', device_id, 'shell', 'getprop', 'ro.build.fingerprint'],
                'timeout': 5
            },
            # Method 3: Check manufacturer
            {
                'name': 'manufacturer',
                'cmd': ['adb', '-s', device_id, 'shell', 'getprop', 'ro.product.manufacturer'],
                'timeout': 5
            }
        ]
        
        # Try property-based detection first
        for method in detection_methods:
            try:
                result = subprocess.run(
                    method['cmd'], capture_output=True, text=True, 
                    timeout=method['timeout']
                )
                
                if result.returncode == 0:
                    output = result.stdout.strip().lower()
                    
                    # Check for OS indicators
                    if any(indicator in output for indicator in ['vega', 'echo', 'alexa']):
                        return 'VEGA'
                    elif any(indicator in output for indicator in ['fire', 'kindle', 'amazon']):
                        return 'FOS' 
                    elif 'puffin' in output:
                        return 'Puffin'
                        
            except Exception as e:
                print(f"OS detection method {method['name']} failed: {e}")
                continue
        
        # Fallback: Directory-based detection
        directory_checks = [
            ('/var/lib/data', 'VEGA'),
            ('/system/priv-app', 'FOS'),
            ('/data/alexahybrid', 'Puffin')
        ]
        
        for directory, os_type in directory_checks:
            try:
                result = subprocess.run(
                    ['adb', '-s', device_id, 'shell', 'test', '-d', directory],
                    capture_output=True, timeout=2
                )
                if result.returncode == 0:
                    return os_type
            except Exception:
                continue
                
        # Final fallback: Try to determine by available commands
        try:
            # Check if journalctl exists (VEGA)
            result = subprocess.run(
                ['adb', '-s', device_id, 'shell', 'which', 'journalctl'],
                capture_output=True, timeout=3
            )
            if result.returncode == 0:
                return 'VEGA'
        except Exception:
            pass
            
        # Default to FOS as it's most common
        return 'FOS'

    def start_logging(self, device: dict, filename: Optional[str] = None, grep_patterns: Optional[Dict[int, str]] = None):
        """Start ADB logging with trial-and-error approach"""
        if self.logging_active:
            self.socketio.emit('error', {'message': 'Logging is already active'})
            return False
        
        self.current_device = DeviceInfo(**device)
        self.grep_patterns = grep_patterns or {}
        
        try:
            # Open log file if filename provided
            if filename:
                try:
                    self.log_file_handle = open(filename, 'w')
                except Exception as e:
                    self.socketio.emit('error', {'message': f'Cannot create log file "{filename}": {str(e)}'})
                    return False
            
            # Try different logging commands in order of preference
            success = self._try_logging_methods()
            
            if not success:
                if self.log_file_handle:
                    self.log_file_handle.close()
                    self.log_file_handle = None
                device_id = self.current_device.device_id if self.current_device else 'unknown'
                self.socketio.emit('error', {
                    'message': f'Failed to start logging for {device_id}. Device may not support standard logging commands or is disconnected.'
                })
                return False
            
            self.logging_active = True
            self.log_buffer = []
            
            # Start log processing in a separate thread
            threading.Thread(target=self._process_logs, daemon=True).start()
            
            return True
            
        except Exception as e:
            if self.log_file_handle:
                try:
                    self.log_file_handle.close()
                except:
                    pass
                self.log_file_handle = None
            self.socketio.emit('error', {'message': f'Error starting log capture: {str(e)}'})
            return False
            
    def _try_logging_methods(self) -> bool:
        """Try different logging methods in order: FOS -> VEGA -> Generic"""
        methods = [
            {
                'name': 'FOS/Puffin logcat',
                'cmd': ['adb', '-s', self.current_device.device_id if self.current_device else '', 'logcat'],
                'test_cmd': ['adb', '-s', self.current_device.device_id if self.current_device else '', 'shell', 'logcat', '-d', '-t', '1']
            },
            {
                'name': 'VEGA journalctl',
                'cmd': ['adb', '-s', self.current_device.device_id if self.current_device else '', 'shell', 'journalctl', '-f'],
                'test_cmd': ['adb', '-s', self.current_device.device_id if self.current_device else '', 'shell', 'journalctl', '--version']
            }
        ]
        
        for method in methods:
            try:
                self.socketio.emit('logging_status', {
                    'status': 'trying',
                    'message': f'Trying {method["name"]} for {self.current_device.device_id if self.current_device else "unknown"}...'
                })
                
                # Test if the command is available
                test_result = subprocess.run(
                    method['test_cmd'], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                
                if test_result.returncode == 0 or 'journalctl' in method['name']:
                    # Try to start the actual logging process
                    self.log_process = subprocess.Popen(
                        method['cmd'], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE, 
                        text=True, 
                        bufsize=1
                    )
                    
                    # Wait a moment to see if process starts successfully
                    time.sleep(0.5)
                    
                    if self.log_process.poll() is None:  # Process is still running
                        self.socketio.emit('logging_status', {
                            'status': 'started',
                            'message': f'Logging started using {method["name"]} for {self.current_device.device_id if self.current_device else "unknown"}'
                        })
                        return True
                    else:
                        # Process failed, try next method
                        continue
                        
            except subprocess.TimeoutExpired:
                self.socketio.emit('logging_status', {
                    'status': 'timeout',
                    'message': f'{method["name"]} timed out, trying next method...'
                })
                continue
            except Exception as e:
                self.socketio.emit('logging_status', {
                    'status': 'error',
                    'message': f'{method["name"]} failed: {str(e)}, trying next method...'
                })
                continue
        
        return False

    def _process_logs(self):
        """Process logs in background thread with enhanced error handling"""
        try:
            consecutive_errors = 0
            max_consecutive_errors = 5
            
            while self.logging_active and self.log_process and self.log_process.poll() is None:
                try:
                    if self.log_process.stdout:
                        line = self.log_process.stdout.readline()
                        if line:
                            line = line.strip()
                            
                            # Reset error counter on successful read
                            consecutive_errors = 0
                            
                            # Add to buffer
                            self.log_buffer.append(line)
                            
                            # Save to file if specified
                            if self.log_file_handle:
                                try:
                                    self.log_file_handle.write(line + '\n')
                                    self.log_file_handle.flush()
                                except Exception as e:
                                    self.socketio.emit('error', {
                                        'message': f'Error writing to log file: {str(e)}'
                                    })
                            
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
                        else:
                            # No data, short sleep to prevent busy waiting
                            time.sleep(0.01)
                            
                except Exception as e:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        self.socketio.emit('error', {
                            'message': f'Too many consecutive errors reading logs: {str(e)}. Stopping log capture.'
                        })
                        break
                    else:
                        print(f"Log processing error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                        time.sleep(0.1)
                        
            # Check if process ended unexpectedly
            if self.log_process and self.log_process.poll() is not None and self.logging_active:
                return_code = self.log_process.returncode
                stderr_output = ""
                try:
                    if self.log_process.stderr:
                        stderr_output = self.log_process.stderr.read()
                except:
                    pass
                    
                self.socketio.emit('error', {
                    'message': f'Log process ended unexpectedly (exit code: {return_code}). {stderr_output}'
                })
                self.logging_active = False
                
        except Exception as e:
            self.socketio.emit('error', {'message': f'Critical error in log processing: {str(e)}'})
            self.logging_active = False

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

# Initialize SocketIO with proper configuration
socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True)

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
    """Handle device detection request with enhanced error handling"""
    try:
        print("Starting device detection...")
        devices = adb_manager.detect_devices()
        device_data = [asdict(device) for device in devices]
        print(f"Found {len(devices)} devices: {[d.device_id for d in devices]}")
        emit('devices', {'devices': device_data})
        
        # Also emit connection status
        if devices:
            emit('connection_status', {
                'status': 'connected',
                'message': f'{len(devices)} device(s) connected'
            })
        else:
            emit('connection_status', {
                'status': 'disconnected', 
                'message': 'No ADB devices found'
            })
            
    except Exception as e:
        print(f"Error in device detection: {e}")
        emit('error', {'message': f'Device detection failed: {str(e)}'})
        emit('devices', {'devices': []})

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


def find_available_port(start_port=5000, max_port=5100):
    """Find an available port starting from start_port"""
    for port in range(start_port, max_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available ports found between {start_port} and {max_port}")

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
    
    # Use port 5000 (required for Replit webview)
    port = 5000
    print("🚀 Starting FERB - the adb interaction tool Web Interface...")
    print(f"🌐 Access the tool at: http://localhost:{port}")
    
    # Run the Flask-SocketIO app on port 5000
    socketio.run(app, host='0.0.0.0', port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)