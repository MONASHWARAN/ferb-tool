#!/usr/bin/env python3
"""
ADB Log Interaction Tool
A comprehensive GUI application for managing ADB logs and device interactions
with support for FOS, VEGA, and Puffin OS types.
"""

import sys
import subprocess
import threading
import os
import re
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QPushButton, QLineEdit, QTextEdit, QLabel, QTabWidget, QGroupBox,
    QComboBox, QSplitter, QProgressBar, QStatusBar, QMessageBox,
    QScrollArea, QFrame
)
from PyQt6.QtCore import (
    QThread, pyqtSignal, QTimer, Qt, QMutex, QWaitCondition
)
from PyQt6.QtGui import QFont, QPalette, QColor, QPixmap, QIcon

@dataclass
class DeviceInfo:
    """Device information structure"""
    device_id: str
    os_type: str
    status: str

class LogThread(QThread):
    """Thread for handling ADB log capture"""
    log_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, device_id: str, os_type: str, filename: Optional[str] = None):
        super().__init__()
        self.device_id = device_id
        self.os_type = os_type
        self.filename = filename
        self.running = False
        self.process = None
        
    def run(self):
        """Execute the logging process"""
        self.running = True
        
        try:
            # Determine the correct ADB command based on OS type
            if self.os_type.lower() == 'vega':
                if self.filename:
                    cmd = f"adb -s {self.device_id} shell journalctl -f > {self.filename}"
                else:
                    cmd = f"adb -s {self.device_id} shell journalctl -f"
            else:  # FOS & Puffin
                if self.filename:
                    cmd = f"adb -s {self.device_id} logcat > {self.filename}"
                else:
                    cmd = f"adb -s {self.device_id} logcat"
            
            self.process = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, text=True, bufsize=1
            )
            
            while self.running and self.process.poll() is None:
                if self.process.stdout:
                    line = self.process.stdout.readline()
                if line:
                    self.log_received.emit(line.strip())
                    
        except Exception as e:
            self.error_occurred.emit(f"Error during log capture: {str(e)}")
            
    def stop(self):
        """Stop the logging process"""
        self.running = False
        if self.process:
            self.process.terminate()
            self.process.wait()

class GrepThread(QThread):
    """Thread for handling grep operations"""
    grep_match_found = pyqtSignal(str, str)  # pattern, matched_line
    grep_status_updated = pyqtSignal(str, str)  # pattern, status
    
    def __init__(self):
        super().__init__()
        self.patterns = []
        self.running = False
        self.mutex = QMutex()
        
    def add_pattern(self, pattern: str):
        """Add a grep pattern to search for"""
        self.mutex.lock()
        try:
            if pattern and pattern not in self.patterns:
                self.patterns.append(pattern)
        finally:
            self.mutex.unlock()
                
    def remove_pattern(self, pattern: str):
        """Remove a grep pattern"""
        self.mutex.lock()
        try:
            if pattern in self.patterns:
                self.patterns.remove(pattern)
        finally:
            self.mutex.unlock()
                
    def process_log_line(self, line: str):
        """Process a log line against all patterns"""
        if not self.running:
            return
            
        self.mutex.lock()
        try:
            for pattern in self.patterns:
                if pattern and re.search(pattern, line, re.IGNORECASE):
                    self.grep_match_found.emit(pattern, line)
                    self.grep_status_updated.emit(pattern, f"Found match: {len(line)} chars")
        finally:
            self.mutex.unlock()
                    
    def start_grep(self):
        """Start grep processing"""
        self.running = True
        
    def stop_grep(self):
        """Stop grep processing"""
        self.running = False

class ADBLogTool(QMainWindow):
    """Main application window for ADB Log Tool"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADB Log Interaction Tool")
        self.setGeometry(100, 100, 1400, 900)
        
        # Initialize variables
        self.devices: List[DeviceInfo] = []
        self.current_device: Optional[DeviceInfo] = None
        self.log_thread: Optional[LogThread] = None
        self.grep_thread = GrepThread()
        self.log_buffer = []
        
        # Setup UI
        self.setup_ui()
        self.setup_dark_theme()
        
        # Start device detection
        self.detect_devices()
        
        # Setup timers
        self.device_timer = QTimer()
        self.device_timer.timeout.connect(self.detect_devices)
        self.device_timer.start(5000)  # Check every 5 seconds

    def setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # Device selection section
        device_group = self.create_device_section()
        main_layout.addWidget(device_group)
        
        # Log control section
        log_control_group = self.create_log_control_section()
        main_layout.addWidget(log_control_group)
        
        # Grep section
        grep_group = self.create_grep_section()
        main_layout.addWidget(grep_group)
        
        # Main content area with tabs
        content_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Output tabs
        self.tab_widget = QTabWidget()
        self.setup_output_tabs()
        content_splitter.addWidget(self.tab_widget)
        
        # CHR DB extraction section
        chr_group = self.create_chr_section()
        content_splitter.addWidget(chr_group)
        
        content_splitter.setSizes([600, 200])
        main_layout.addWidget(content_splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def create_device_section(self) -> QGroupBox:
        """Create device selection section"""
        group = QGroupBox("Connected Devices")
        layout = QHBoxLayout(group)
        
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(300)
        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        
        refresh_btn = QPushButton("Refresh Devices")
        refresh_btn.clicked.connect(self.detect_devices)
        
        self.device_status_label = QLabel("No devices detected")
        
        layout.addWidget(QLabel("Device:"))
        layout.addWidget(self.device_combo)
        layout.addWidget(refresh_btn)
        layout.addStretch()
        layout.addWidget(self.device_status_label)
        
        return group

    def create_log_control_section(self) -> QGroupBox:
        """Create log control section"""
        group = QGroupBox("Log Control")
        layout = QHBoxLayout(group)
        
        # Log filename input
        self.log_filename_input = QLineEdit()
        self.log_filename_input.setPlaceholderText("Enter log filename (optional)")
        self.log_filename_input.setMinimumWidth(200)
        
        # Control buttons
        self.start_log_btn = QPushButton("Start Logs")
        self.start_log_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.start_log_btn.clicked.connect(self.start_logging)
        
        self.stop_log_btn = QPushButton("Stop Logs")
        self.stop_log_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        self.stop_log_btn.clicked.connect(self.stop_logging)
        self.stop_log_btn.setEnabled(False)
        
        self.clear_log_btn = QPushButton("Clear Logs")
        self.clear_log_btn.clicked.connect(self.clear_logs)
        
        layout.addWidget(QLabel("Log Filename:"))
        layout.addWidget(self.log_filename_input)
        layout.addWidget(self.start_log_btn)
        layout.addWidget(self.stop_log_btn)
        layout.addWidget(self.clear_log_btn)
        layout.addStretch()
        
        return group

    def create_grep_section(self) -> QGroupBox:
        """Create grep search section"""
        group = QGroupBox("Log Search (Grep)")
        layout = QVBoxLayout(group)
        
        # Three grep input fields
        self.grep_inputs = []
        self.grep_status_labels = []
        
        for i in range(3):
            row_layout = QHBoxLayout()
            
            grep_input = QLineEdit()
            grep_input.setPlaceholderText(f"Enter search pattern {i+1}")
            grep_input.textChanged.connect(lambda text, idx=i: self.on_grep_pattern_changed(idx, text))
            
            status_label = QLabel("Ready")
            status_label.setStyleSheet("color: #888; font-style: italic;")
            status_label.setMinimumWidth(150)
            
            row_layout.addWidget(QLabel(f"Pattern {i+1}:"))
            row_layout.addWidget(grep_input)
            row_layout.addWidget(status_label)
            
            self.grep_inputs.append(grep_input)
            self.grep_status_labels.append(status_label)
            layout.addLayout(row_layout)
        
        return group

    def setup_output_tabs(self):
        """Setup output tabs for live logs and grep results"""
        # Live logs tab
        self.live_logs_widget = QTextEdit()
        self.live_logs_widget.setReadOnly(True)
        self.live_logs_widget.setFont(QFont("Consolas", 9))
        self.tab_widget.addTab(self.live_logs_widget, "Live Logs")
        
        # Grep results tab
        self.grep_results_widget = QTextEdit()
        self.grep_results_widget.setReadOnly(True)
        self.grep_results_widget.setFont(QFont("Consolas", 9))
        self.tab_widget.addTab(self.grep_results_widget, "Grep Results")

    def create_chr_section(self) -> QGroupBox:
        """Create CHR DB extraction section"""
        group = QGroupBox("CHR Database Extraction")
        layout = QHBoxLayout(group)
        
        # FOS CHR button
        fos_btn = QPushButton("Extract FOS CHR")
        fos_btn.setStyleSheet("background-color: #2196F3; color: white; padding: 8px;")
        fos_btn.clicked.connect(lambda: self.extract_chr_db('FOS'))
        
        # VEGA CHR button
        vega_btn = QPushButton("Extract VEGA CHR")
        vega_btn.setStyleSheet("background-color: #FF9800; color: white; padding: 8px;")
        vega_btn.clicked.connect(lambda: self.extract_chr_db('VEGA'))
        
        # Puffin CHR button
        puffin_btn = QPushButton("Extract Puffin CHR")
        puffin_btn.setStyleSheet("background-color: #9C27B0; color: white; padding: 8px;")
        puffin_btn.clicked.connect(lambda: self.extract_chr_db('Puffin'))
        
        self.chr_status_label = QLabel("Ready to extract CHR database")
        
        layout.addWidget(fos_btn)
        layout.addWidget(vega_btn)
        layout.addWidget(puffin_btn)
        layout.addStretch()
        layout.addWidget(self.chr_status_label)
        
        return group

    def setup_dark_theme(self):
        """Apply dark theme to the application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
                background-color: #3c3c3c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #ffffff;
            }
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666;
                padding: 8px 16px;
                border-radius: 4px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
            QLineEdit {
                background-color: #4a4a4a;
                border: 1px solid #666;
                padding: 6px;
                border-radius: 3px;
                color: #ffffff;
            }
            QComboBox {
                background-color: #4a4a4a;
                border: 1px solid #666;
                padding: 6px;
                border-radius: 3px;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #666;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #666;
                background-color: #3c3c3c;
            }
            QTabBar::tab {
                background-color: #4a4a4a;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #666;
            }
            QLabel {
                color: #ffffff;
            }
            QStatusBar {
                background-color: #3c3c3c;
                color: #ffffff;
                border-top: 1px solid #666;
            }
        """)

    def detect_devices(self):
        """Detect connected ADB devices and identify their OS types"""
        try:
            # Run adb devices command
            result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
            if result.returncode != 0:
                self.device_status_label.setText("ADB not found or error occurred")
                return
            
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
            
            # Update device list
            self.devices = devices
            self.update_device_combo()
            
            if devices:
                self.device_status_label.setText(f"{len(devices)} device(s) connected")
            else:
                self.device_status_label.setText("No devices connected")
                
        except Exception as e:
            self.device_status_label.setText(f"Error: {str(e)}")

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
                
                # Check for specific OS indicators
                if 'vega' in model or 'echo' in model:
                    return 'VEGA'
                elif 'fire' in model or 'kindle' in model:
                    return 'FOS'
                elif 'puffin' in model:
                    return 'Puffin'
            
            # Fallback: check for specific directories or files
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

    def update_device_combo(self):
        """Update the device combo box"""
        self.device_combo.clear()
        
        for device in self.devices:
            display_text = f"{device.device_id} ({device.os_type}) - {device.status}"
            self.device_combo.addItem(display_text, device)

    def on_device_changed(self, text: str):
        """Handle device selection change"""
        if self.device_combo.currentData():
            self.current_device = self.device_combo.currentData()
            self.status_bar.showMessage(f"Selected device: {self.current_device.device_id} ({self.current_device.os_type})")

    def start_logging(self):
        """Start ADB logging"""
        if not self.current_device:
            QMessageBox.warning(self, "Warning", "Please select a device first")
            return
        
        if self.log_thread and self.log_thread.isRunning():
            QMessageBox.warning(self, "Warning", "Logging is already in progress")
            return
        
        filename = self.log_filename_input.text().strip() if self.log_filename_input.text().strip() else None
        
        self.log_thread = LogThread(self.current_device.device_id, self.current_device.os_type, filename)
        self.log_thread.log_received.connect(self.on_log_received)
        self.log_thread.error_occurred.connect(self.on_log_error)
        self.log_thread.start()
        
        # Start grep thread
        self.grep_thread.start_grep()
        
        # Update UI
        self.start_log_btn.setEnabled(False)
        self.stop_log_btn.setEnabled(True)
        self.status_bar.showMessage("Logging started...")

    def stop_logging(self):
        """Stop ADB logging"""
        if self.log_thread:
            self.log_thread.stop()
            self.log_thread.wait()
            
        self.grep_thread.stop_grep()
        
        # Save log file if filename was provided
        filename = self.log_filename_input.text().strip()
        if filename and self.log_buffer:
            try:
                with open(filename, 'w') as f:
                    f.write('\n'.join(self.log_buffer))
                self.status_bar.showMessage(f"Logs saved to {filename}")
                QMessageBox.information(self, "Success", f"Logs saved to {filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save logs: {str(e)}")
        
        # Update UI
        self.start_log_btn.setEnabled(True)
        self.stop_log_btn.setEnabled(False)
        self.status_bar.showMessage("Logging stopped")

    def clear_logs(self):
        """Clear all log displays"""
        self.live_logs_widget.clear()
        self.grep_results_widget.clear()
        self.log_buffer.clear()
        
        # Reset grep status labels
        for label in self.grep_status_labels:
            label.setText("Ready")
        
        self.status_bar.showMessage("Logs cleared")

    def on_log_received(self, line: str):
        """Handle received log line"""
        # Add to buffer
        self.log_buffer.append(line)
        
        # Display in live logs
        self.live_logs_widget.append(line)
        
        # Limit buffer size to prevent memory issues
        if len(self.log_buffer) > 10000:
            self.log_buffer = self.log_buffer[-5000:]
        
        # Process for grep
        self.grep_thread.process_log_line(line)

    def on_log_error(self, error: str):
        """Handle log error"""
        self.status_bar.showMessage(f"Logging error: {error}")
        QMessageBox.critical(self, "Logging Error", error)

    def on_grep_pattern_changed(self, index: int, pattern: str):
        """Handle grep pattern change"""
        old_patterns = [input.text() for input in self.grep_inputs]
        
        # Update grep thread patterns
        if index < len(old_patterns):
            old_pattern = old_patterns[index] if index < len(self.grep_inputs) else ""
            if old_pattern:
                self.grep_thread.remove_pattern(old_pattern)
        
        if pattern:
            self.grep_thread.add_pattern(pattern)
            self.grep_status_labels[index].setText("Searching...")
        else:
            self.grep_status_labels[index].setText("Ready")
        
        # Connect grep signals if not already connected
        if not hasattr(self, '_grep_signals_connected'):
            self.grep_thread.grep_match_found.connect(self.on_grep_match_found)
            self.grep_thread.grep_status_updated.connect(self.on_grep_status_updated)
            self._grep_signals_connected = True

    def on_grep_match_found(self, pattern: str, line: str):
        """Handle grep match found"""
        timestamp = time.strftime("%H:%M:%S")
        match_text = f"[{timestamp}] Pattern '{pattern}' found:\n{line}\n"
        self.grep_results_widget.append(match_text)

    def on_grep_status_updated(self, pattern: str, status: str):
        """Handle grep status update"""
        for i, input_field in enumerate(self.grep_inputs):
            if input_field.text() == pattern:
                self.grep_status_labels[i].setText(status)
                break

    def extract_chr_db(self, os_type: str):
        """Extract CHR database file based on OS type"""
        if not self.current_device:
            QMessageBox.warning(self, "Warning", "Please select a device first")
            return
        
        # Define extraction paths based on OS type
        if os_type == 'FOS':
            source_path = "/data/data/com.amazon.alexahybridremoteskill/files/customerHomeRegistry.db"
        elif os_type == 'VEGA':
            source_path = "/var/lib/data/alexahybrid/smartHomeSkill/customerHomeRegistry.db"
        elif os_type == 'Puffin':
            source_path = "/data/alexahybrid/files/smartHomeSkill/customerHomeRegistry.db"
        else:
            QMessageBox.warning(self, "Warning", f"Unknown OS type: {os_type}")
            return
        
        # Create output filename
        output_filename = f"CHR_{os_type}_{self.current_device.device_id}.db"
        
        try:
            self.chr_status_label.setText(f"Extracting CHR DB for {os_type}...")
            
            # Execute adb pull command
            cmd = ['adb', '-s', self.current_device.device_id, 'pull', source_path, output_filename]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.chr_status_label.setText(f"CHR DB extracted: {output_filename}")
                QMessageBox.information(self, "Success", f"CHR database extracted successfully!\nFile: {output_filename}")
            else:
                error_msg = result.stderr or result.stdout or "Unknown error occurred"
                self.chr_status_label.setText("CHR extraction failed")
                QMessageBox.critical(self, "Error", f"Failed to extract CHR database:\n{error_msg}")
                
        except subprocess.TimeoutExpired:
            self.chr_status_label.setText("CHR extraction timed out")
            QMessageBox.critical(self, "Error", "CHR database extraction timed out")
        except Exception as e:
            self.chr_status_label.setText("CHR extraction error")
            QMessageBox.critical(self, "Error", f"Error extracting CHR database:\n{str(e)}")

def main():
    """Main application entry point"""
    # Set Qt platform plugin to offscreen for headless operation
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("ADB Log Tool")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("DevTools")
    
    # Create and show main window
    window = ADBLogTool()
    window.show()
    
    # Start event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()