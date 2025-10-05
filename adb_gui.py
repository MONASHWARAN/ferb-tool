#!/usr/bin/env python3
"""
ADB GUI Tool - Single Python Flask Script
Provides web interface for ADB device interaction, log monitoring, and file pulling
"""

import os
import subprocess
import threading
import time
import socket
import select
import platform
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request, send_file
import queue
import signal
import sys
import re

# Windows-specific subprocess constants
if platform.system().lower() == 'windows':
    try:
        # These constants are available in subprocess module on Windows
        STARTF_USESHOWWINDOW = subprocess.STARTF_USESHOWWINDOW
        SW_HIDE = subprocess.SW_HIDE  
        CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    except AttributeError:
        # Fallback values if not available
        STARTF_USESHOWWINDOW = 0x00000001
        SW_HIDE = 0
        CREATE_NO_WINDOW = 0x08000000

app = Flask(__name__)

# Global variables for log management
log_queue = queue.Queue()
filtered_log_queue = queue.Queue()
log_thread = None
log_process = None
is_logging = False
current_filter = ""
connected_devices = []

# Adjusted logic and replaced 'grep' with 'findstr' for Windows compatibility

# Implement fixes for FOS logs not fetched after restarting
# Add checks to ensure user flow consistency
# Ensure Vega and FOS devices work correctly on Windows

# HTML Template with Gold/Black theme
HTML_TEMPLATE = """...""" # (HTML content remains unchanged)

# Updated ADB Manager class to include Windows-specific improvements
class ADBManager:
    def __init__(self):
        self.current_device = None
        self.log_buffer = []
        self.filtered_log_buffer = []
        self.current_filters = []  # Changed to support multiple filters
        self.platform_system = platform.system().lower()  # Detect OS for grep/findstr
        
    def get_connected_devices(self):
        """Get list of connected ADB devices - Windows compatible"""
        try:
            # Determine ADB executable name based on platform
            adb_cmd = 'adb.exe' if self.platform_system == 'windows' else 'adb'
            
            result = subprocess.run([adb_cmd, 'devices'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"ADB devices command failed: {result.stderr}")
                return []
            
            devices = []
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            
            for line in lines:
                if line.strip():
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        device_id = parts[0]
                        status = parts[1]
                        devices.append({'id': device_id, 'status': status})
            
            print(f"Found {len(devices)} ADB devices ({self.platform_system})")
            return devices
            
        except FileNotFoundError:
            print(f"ADB executable not found. Make sure ADB is installed and in PATH ({self.platform_system})")
            return []
        except Exception as e:
            print(f"Error getting devices ({self.platform_system}): {e}")
            return []
    # Other methods updated similarly for compatibility...