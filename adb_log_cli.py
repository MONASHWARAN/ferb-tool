#!/usr/bin/env python3
"""
ADB Log Interaction Tool - Command Line Version
A comprehensive CLI application for managing ADB logs and device interactions
with support for FOS, VEGA, and Puffin OS types.
"""

import os
import sys
import subprocess
import threading
import time
import re
import signal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

@dataclass
class DeviceInfo:
    """Device information structure"""
    device_id: str
    os_type: str
    status: str

class ADBLogCLI:
    """Command-line ADB Log Tool"""
    
    def __init__(self):
        self.devices: List[DeviceInfo] = []
        self.current_device: Optional[DeviceInfo] = None
        self.log_process: Optional[subprocess.Popen] = None
        self.log_file_handle: Optional[any] = None
        self.grep_patterns: List[str] = []
        self.grep_matches: List[str] = []
        self.logging_active = False
        self.log_buffer: List[str] = []
        
        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        """Handle Ctrl+C gracefully"""
        print("\nStopping log capture...")
        self.stop_logging()
        sys.exit(0)

    def clear_screen(self):
        """Clear terminal screen"""
        os.system('clear' if os.name == 'posix' else 'cls')

    def print_header(self):
        """Print application header"""
        print("=" * 80)
        print(" " * 25 + "ADB LOG INTERACTION TOOL")
        print(" " * 20 + "FOS, VEGA & Puffin Support")
        print("=" * 80)

    def detect_devices(self) -> bool:
        """Detect connected ADB devices and identify their OS types"""
        try:
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print("❌ ADB not found or error occurred")
                return False
            
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
            return len(devices) > 0
            
        except Exception as e:
            print(f"❌ Error detecting devices: {e}")
            return False

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

    def display_devices(self):
        """Display connected devices"""
        if not self.devices:
            print("❌ No devices connected")
            return
        
        print("\n📱 Connected Devices:")
        print("-" * 60)
        for i, device in enumerate(self.devices, 1):
            status_icon = "✅" if device.status == "device" else "⚠️"
            print(f"{i}. {status_icon} {device.device_id} ({device.os_type}) - {device.status}")
        print("-" * 60)

    def select_device(self) -> bool:
        """Allow user to select a device"""
        if not self.devices:
            print("❌ No devices available")
            return False
        
        if len(self.devices) == 1:
            self.current_device = self.devices[0]
            print(f"✅ Auto-selected device: {self.current_device.device_id} ({self.current_device.os_type})")
            return True
        
        self.display_devices()
        try:
            choice = input("\nSelect device number (1-{}): ".format(len(self.devices)))
            idx = int(choice) - 1
            if 0 <= idx < len(self.devices):
                self.current_device = self.devices[idx]
                print(f"✅ Selected device: {self.current_device.device_id} ({self.current_device.os_type})")
                return True
            else:
                print("❌ Invalid selection")
                return False
        except (ValueError, KeyboardInterrupt):
            print("❌ Invalid input")
            return False

    def setup_grep_patterns(self):
        """Setup grep patterns for log filtering"""
        print("\n🔍 Grep Pattern Setup (press Enter to skip):")
        print("-" * 50)
        
        self.grep_patterns = []
        for i in range(3):
            pattern = input(f"Pattern {i+1}: ").strip()
            if pattern:
                self.grep_patterns.append(pattern)
                print(f"   ✅ Added pattern: {pattern}")
        
        if self.grep_patterns:
            print(f"\n🎯 {len(self.grep_patterns)} grep pattern(s) configured")
        else:
            print("ℹ️ No grep patterns configured - all logs will be shown")

    def start_logging(self, filename: Optional[str] = None):
        """Start ADB logging"""
        if not self.current_device:
            print("❌ No device selected")
            return False
        
        if self.logging_active:
            print("❌ Logging is already active")
            return False
        
        try:
            # Determine the correct ADB command based on OS type
            if self.current_device.os_type.lower() == 'vega':
                cmd = ['adb', '-s', self.current_device.device_id, 'shell', 'journalctl', '-f']
            else:  # FOS & Puffin
                cmd = ['adb', '-s', self.current_device.device_id, 'logcat']
            
            print(f"🚀 Starting log capture for {self.current_device.device_id} ({self.current_device.os_type})")
            if filename:
                print(f"💾 Logs will be saved to: {filename}")
                self.log_file_handle = open(filename, 'w')
            
            # Start the logging process
            self.log_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                text=True, bufsize=1
            )
            
            self.logging_active = True
            
            # Start log processing in a separate thread
            threading.Thread(target=self._process_logs, daemon=True).start()
            
            print("✅ Logging started! Press Ctrl+C to stop\n")
            print("📊 Live Log Output:")
            print("=" * 80)
            
            return True
            
        except Exception as e:
            print(f"❌ Error starting log capture: {e}")
            return False

    def _process_logs(self):
        """Process logs in background thread"""
        grep_matches_count = {pattern: 0 for pattern in self.grep_patterns}
        
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
                        except AttributeError:
                            pass
                    
                    # Display the log line
                    timestamp = time.strftime("%H:%M:%S")
                    print(f"[{timestamp}] {line}")
                    
                    # Check grep patterns
                    for pattern in self.grep_patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            grep_matches_count[pattern] += 1
                            self.grep_matches.append(f"[{timestamp}] MATCH '{pattern}': {line}")
                            print(f"🎯 GREP MATCH [{pattern}]: {line}")
                    
                    # Limit buffer size
                    if len(self.log_buffer) > 10000:
                        self.log_buffer = self.log_buffer[-5000:]
                        
        except Exception as e:
            print(f"❌ Error processing logs: {e}")
        finally:
            # Display grep summary
            if self.grep_patterns:
                print("\n📈 Grep Match Summary:")
                for pattern, count in grep_matches_count.items():
                    print(f"   '{pattern}': {count} matches")

    def stop_logging(self):
        """Stop ADB logging"""
        if not self.logging_active:
            return
        
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
            except AttributeError:
                pass
            self.log_file_handle = None
        
        print(f"\n🛑 Logging stopped. Captured {len(self.log_buffer)} log lines")

    def show_grep_results(self):
        """Display grep match results"""
        if not self.grep_matches:
            print("ℹ️ No grep matches found")
            return
        
        print("\n🎯 Grep Match Results:")
        print("=" * 80)
        for match in self.grep_matches[-50:]:  # Show last 50 matches
            print(match)
        print("=" * 80)
        
        if len(self.grep_matches) > 50:
            print(f"... showing last 50 of {len(self.grep_matches)} total matches")

    def extract_chr_db(self, os_type: str):
        """Extract CHR database file based on OS type"""
        if not self.current_device:
            print("❌ No device selected")
            return False
        
        # Define extraction paths based on OS type
        source_paths = {
            'FOS': "/data/data/com.amazon.alexahybridremoteskill/files/customerHomeRegistry.db",
            'VEGA': "/var/lib/data/alexahybrid/smartHomeSkill/customerHomeRegistry.db",
            'Puffin': "/data/alexahybrid/files/smartHomeSkill/customerHomeRegistry.db"
        }
        
        if os_type not in source_paths:
            print(f"❌ Unknown OS type: {os_type}")
            return False
        
        source_path = source_paths[os_type]
        output_filename = f"CHR_{os_type}_{self.current_device.device_id}_{int(time.time())}.db"
        
        try:
            print(f"📥 Extracting CHR DB for {os_type} from {self.current_device.device_id}")
            
            cmd = ['adb', '-s', self.current_device.device_id, 'pull', source_path, output_filename]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                file_size = os.path.getsize(output_filename) if os.path.exists(output_filename) else 0
                print(f"✅ CHR database extracted successfully!")
                print(f"   📁 File: {output_filename}")
                print(f"   📊 Size: {file_size} bytes")
                return True
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                print(f"❌ Failed to extract CHR database:")
                print(f"   {error_msg}")
                return False
                
        except subprocess.TimeoutExpired:
            print("❌ CHR database extraction timed out")
            return False
        except Exception as e:
            print(f"❌ Error extracting CHR database: {e}")
            return False

    def main_menu(self):
        """Display main menu and handle user input"""
        while True:
            self.clear_screen()
            self.print_header()
            
            if self.current_device:
                print(f"📱 Selected Device: {self.current_device.device_id} ({self.current_device.os_type})")
            else:
                print("📱 No device selected")
            
            print("\n📋 Menu Options:")
            print("1. 🔍 Detect/Refresh Devices")
            print("2. 📱 Select Device")
            print("3. 🎯 Setup Grep Patterns")
            print("4. 🚀 Start Logging")
            print("5. 🛑 Stop Logging")
            print("6. 📊 Show Grep Results")
            print("7. 📥 Extract CHR Database")
            print("8. ❌ Exit")
            
            if self.logging_active:
                print("\n⚠️ Logging is currently active!")
            
            try:
                choice = input("\nSelect option (1-8): ").strip()
                
                if choice == '1':
                    print("\n🔍 Detecting devices...")
                    if self.detect_devices():
                        self.display_devices()
                    input("\nPress Enter to continue...")
                
                elif choice == '2':
                    if not self.detect_devices():
                        print("❌ No devices found")
                    else:
                        self.select_device()
                    input("\nPress Enter to continue...")
                
                elif choice == '3':
                    self.setup_grep_patterns()
                    input("\nPress Enter to continue...")
                
                elif choice == '4':
                    if not self.current_device:
                        print("❌ Please select a device first")
                        input("\nPress Enter to continue...")
                        continue
                    
                    filename = input("Enter log filename (press Enter to skip): ").strip()
                    if not filename:
                        filename = None
                    
                    if not self.setup_grep_patterns():
                        pass  # Continue anyway
                    
                    if self.start_logging(filename):
                        # Keep running until Ctrl+C
                        try:
                            while self.logging_active:
                                time.sleep(1)
                        except KeyboardInterrupt:
                            self.stop_logging()
                    
                    input("\nPress Enter to continue...")
                
                elif choice == '5':
                    self.stop_logging()
                    input("\nPress Enter to continue...")
                
                elif choice == '6':
                    self.show_grep_results()
                    input("\nPress Enter to continue...")
                
                elif choice == '7':
                    if not self.current_device:
                        print("❌ Please select a device first")
                        input("\nPress Enter to continue...")
                        continue
                    
                    print("\nSelect CHR Database to extract:")
                    print("1. FOS")
                    print("2. VEGA") 
                    print("3. Puffin")
                    
                    chr_choice = input("Select (1-3): ").strip()
                    chr_map = {'1': 'FOS', '2': 'VEGA', '3': 'Puffin'}
                    
                    if chr_choice in chr_map:
                        self.extract_chr_db(chr_map[chr_choice])
                    else:
                        print("❌ Invalid selection")
                    
                    input("\nPress Enter to continue...")
                
                elif choice == '8':
                    self.stop_logging()
                    print("👋 Goodbye!")
                    break
                
                else:
                    print("❌ Invalid option")
                    input("\nPress Enter to continue...")
                    
            except KeyboardInterrupt:
                self.stop_logging()
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                input("\nPress Enter to continue...")

def main():
    """Main application entry point"""
    print("🚀 Starting ADB Log Interaction Tool...")
    
    # Check if ADB is available
    try:
        result = subprocess.run(['adb', 'version'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print("❌ ADB is not installed or not accessible")
            print("Please install Android Debug Bridge (ADB) to use this tool")
            return
        print("✅ ADB is available")
    except Exception as e:
        print(f"❌ Error checking ADB: {e}")
        return
    
    # Create and run the application
    app = ADBLogCLI()
    app.main_menu()

if __name__ == "__main__":
    main()