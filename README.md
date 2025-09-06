# FERB - The ADB Interaction Tool

![FERB Logo](static/ferb-icon.png)

A comprehensive web-based Android Debug Bridge (ADB) log interaction tool that supports multiple OS types including FOS, VEGA, and Puffin OS. Built with Flask and featuring real-time device monitoring, log streaming, and database extraction capabilities.

## Features

### 🚀 Core Functionality
- **Multi-OS Support**: Works with FOS, VEGA, and Puffin OS devices
- **Real-time Device Detection**: Automatic detection and monitoring of ADB-connected devices
- **Live Log Streaming**: Real-time log capture with filtering capabilities
- **Trial-and-Error Logging**: Smart approach - tries FOS commands first, then VEGA if they fail
- **CHR Database Extraction**: Extract CHR databases from all supported OS types
- **Grep Pattern Matching**: Real-time log filtering with pattern matching

### 🎨 User Interface
- **Modern Web Interface**: Professional dark theme with responsive design
- **Ferb Character Branding**: Custom header featuring Ferb from Phineas and Ferb
- **Real-time Status Updates**: Live connection status and device monitoring
- **Comprehensive Error Handling**: User-friendly error messages and automatic recovery
- **Device Dropdown Selection**: Always shows device selection interface

### 🔧 Technical Features
- **Robust Connection Management**: Automatic reconnection handling and device validation
- **Continuous Monitoring**: Background device scanning every 10 seconds
- **Socket.IO Integration**: Real-time communication between frontend and backend
- **Thread-safe Operations**: Non-blocking log capture with threaded processing
- **Cross-platform Support**: Works on Windows, macOS, and Linux

## Installation

### Prerequisites

1. **ADB (Android Debug Bridge)** must be installed and accessible in your system PATH
   - Download from [Android Developer Tools](https://developer.android.com/studio/releases/platform-tools)
   - Ensure `adb` command works from terminal/command prompt

2. **Python 3.6+** required

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/MONASHWARAN/ReportToolAuto.git
   cd ReportToolAuto
   ```

2. **Install Python dependencies**
   ```bash
   pip install flask flask-socketio eventlet psutil
   ```

3. **Verify ADB installation**
   ```bash
   adb version
   ```
   You should see ADB version information if properly installed.

4. **Run the application**
   ```bash
   python app.py
   ```

5. **Access the web interface**
   Open your browser and navigate to: `http://localhost:5000`

## Usage Guide

### Getting Started

1. **Connect your device** via USB and enable USB debugging
2. **Launch FERB** by running `python app.py`
3. **Open your browser** to `http://localhost:5000`
4. **Device detection** happens automatically - connected devices will appear in the dropdown

### Device Management

- **Automatic Detection**: Devices are detected automatically every 10 seconds
- **Device Selection**: Use the dropdown to select your target device
- **Connection Status**: Visual indicators show device connection state
- **OS Type Detection**: Automatically identifies FOS, VEGA, or Puffin OS

### Log Monitoring

1. **Start Logging**: Click "Start Live Log" button
2. **Real-time Stream**: Logs appear in real-time in the log output area
3. **Grep Filtering**: Use the grep input to filter logs with patterns
4. **Stop Logging**: Click "Stop Logging" to end the session

### CHR Database Extraction

1. **Select Device**: Ensure your device is selected
2. **Choose Filename**: Enter a filename for the extracted database
3. **Extract**: Click "Extract CHR DB" to download the database file
4. **OS-Specific Paths**: Tool automatically uses correct paths for each OS type

### Advanced Features

#### Grep Pattern Matching
- Use regular expressions for complex pattern matching
- Multiple patterns can be monitored simultaneously
- Real-time match counting and highlighting

#### Trial-and-Error Logging
- FOS/Puffin devices: Uses `adb logcat` commands
- VEGA devices: Uses `adb shell journalctl` commands
- Automatic fallback if primary method fails

## Supported Operating Systems

### Device OS Types
- **FOS (Fire OS)**: Amazon Fire tablets and devices
- **VEGA**: Echo devices and Alexa-enabled hardware
- **Puffin OS**: Puffin-based smart displays and devices

### Host OS Compatibility
- **Windows**: Windows 10/11 with ADB installed
- **macOS**: macOS 10.14+ with ADB installed
- **Linux**: Most distributions with ADB package

## Troubleshooting

### Common Issues

#### "No ADB devices found"
- Ensure USB debugging is enabled on your device
- Check USB cable connection
- Verify ADB is installed: `adb devices`
- Try different USB ports

#### Device shows as "unresponsive"
- Disconnect and reconnect USB cable
- Restart ADB server: `adb kill-server && adb start-server`
- Check device authorization dialog

#### Web interface not loading
- Ensure port 5000 is not blocked by firewall
- Try accessing via `http://127.0.0.1:5000`
- Check console for error messages

#### Log streaming not working
- Verify device is properly connected
- Check if logging permissions are granted
- Try restarting the application

### Debug Mode

Run with debug logging:
```bash
python app.py --debug
```

## Configuration

### Environment Variables
- `FLASK_ENV`: Set to 'development' for debug mode
- `ADB_PATH`: Custom path to ADB executable (if not in PATH)
- `LOG_LEVEL`: Set logging level (DEBUG, INFO, WARN, ERROR)

### Custom Port
To run on a different port:
```python
# Modify app.py
socketio.run(app, host='0.0.0.0', port=8080, debug=False)
```

## Development

### Project Structure
```
├── app.py                    # Main Flask application
├── templates/
│   └── index.html           # Web interface template
├── static/
│   └── ferb-icon.png        # Ferb character image
├── README.md                # This documentation
└── replit.md               # Project notes
```

### Adding Features
1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Test with multiple device types
5. Submit a pull request

## API Reference

### Socket.IO Events

#### Client to Server
- `detect_devices`: Request device detection
- `start_logging`: Begin log streaming
- `stop_logging`: End log streaming
- `extract_chr_db`: Request database extraction

#### Server to Client
- `devices`: Device list update
- `log_line`: New log line received
- `grep_match`: Pattern match found
- `logging_status`: Logging state change
- `connection_status`: Device connection update
- `error`: Error message

## License

This project is open source and available under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## Support

For support and questions:
1. Check the troubleshooting section
2. Review existing GitHub issues
3. Create a new issue with detailed information

---

**FERB - Making ADB interaction as easy as building with Phineas and Ferb!** 🔧⚡