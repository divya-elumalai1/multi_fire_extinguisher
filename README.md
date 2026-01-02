# Multi Fire Extinguisher Robot System 

A comprehensive fire detection and monitoring system using multiple ESP32-CAM cameras with real-time machine learning inference, automated alerts, and remote robot control capabilities.

## Overview

This system consists of:
- **4 ESP32-CAM cameras** (front, back, left, right) streaming video over WiFi
- **FastAPI backend** for video streaming, fire/smoke detection, and robot control
- **Web dashboard** for real-time monitoring and control
- **Machine learning model** for fire and smoke detection
- **Email alert system** for automated notifications
- **Robot motor control** for remote operation

## Prerequisites

### Hardware Requirements
- 4x ESP32-CAM modules
- Robot chassis with motors and actuators
- WiFi router/hotspot (2.4GHz)
- Computer with Python 3.9+ installed

### Software Requirements
- Python 3.9 or higher
- pip package manager
- Modern web browser (Chrome, Firefox, Edge)

## Installation

### 1. Clone or Download the Project

```bash
cd /path/to/multi_fire_extinguisher
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
```

### 3. Activate Virtual Environment

**On macOS/Linux:**
```bash
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

## Setup

### 1. Configure WiFi Hotspot

The robot cameras connect to a WiFi hotspot. Ensure your hotspot is configured with:
- **SSID:** `fireextinguisher`
- **Password:** `fire12345678`
- **Frequency:** 2.4GHz (ESP32-CAM only supports 2.4GHz)

### 2. Power On the Robot

1. Turn on the WiFi hotspot
2. Power on the robot
3. Wait for all four cameras to connect (check connection history on your router/hotspot device)
4. Verify camera hostnames are accessible:
   - `firecamfront.local` (port 80)
   - `firecamback.local` (port 81)
   - `firecamleft.local` (port 82)
   - `firecamright.local` (port 83)

### 3. Connect Your Computer

Connect your computer to the same WiFi network (`fireextinguisher`).

## Running the System

### 1. Activate Virtual Environment

```bash
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows
```

### 2. Start the Dashboard

```bash
python3 backend/dashboard.py
```

### To Kill Dashboard
```bash
pkill -9 -f "dashboard.py"
```

You should see output indicating the system is starting up:
```
[CONFIG] Loaded configuration from backend/config.yaml
[DASHBOARD] System ready (Lazy Start - No streams active)
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### 3. Access the Dashboard

Open your web browser and navigate to:
```
http://localhost:8001
```
or
```
http://0.0.0.0:8001
```

## Using the Dashboard

### System Configuration

1. **Camera Configuration**
   - Navigate to the System Config section
   - Verify camera endpoints (hostname, port, stream path)
   - Update if your camera IPs/hostnames differ
   - Click "Save Config" to apply changes

2. **Email Configuration**
   - In the Email Config section:
     - Check the box to enable email alerts
     - Enter sender email (Gmail recommended)
     - Enter Gmail App Password (not regular password)
     - Enter comma-separated receiver email addresses
     - Set email interval (seconds between alerts)
     - Select alert types (fire, smoke, or both)
   - Click "Save Config"

3. **Alert Types**
   - Select which events trigger email alerts:
     - **Fire:** Detects fire events
     - **Smoke:** Detects smoke events
   - Save configuration after changes

### Dashboard Controls

#### Camera Streaming

**Start Selected Camera:**
1. Select one or more cameras from the camera list
2. Click "Start Selected" to begin streaming
3. Selected cameras will display live video feeds

**Start All Cameras:**
1. Click "Start All" to stream all four cameras simultaneously
2. Each camera feed shows:
   - Live video stream
   - Detection overlays (if fire/smoke detected)
   - FPS counter
   - Online/offline status

**Stop Selected/All:**
- Click "Stop Selected" to stop specific camera streams
- Click "Stop All" to stop all streams

#### Motor Control

Use the motor control buttons to remotely operate the robot:

**Movement Controls:**
- **Forward:** Move robot forward
- **Back:** Move robot backward
- **Right:** Turn robot right
- **Left:** Turn robot left
- **Stop:** Stop all movement

**Actuator Controls:**
- **Mud Servo Toggle:** Open/close servo trolley for mud
- **Moisture Toggle:** Turn moisture system on/off
- **Water Pump Toggle:** Control water pump motor

### Manual Command Codes

For testing purposes, you can send direct commands to the robot:

| Command | Action |
|---------|--------|
| `0` | Close servo trolley for mud |
| `1` | Open servo trolley for mud |
| `2` | Turn on moisture |
| `3` | Turn off moisture |
| `4` | Turn on water pump motor |
| `5` | Turn off water pump motor |
| `6` | Move forward |
| `7` | Move backward |
| `8` | Turn right |
| `9` | Turn left |
| `p` | Stop all movement |

## Configuration File

The system uses `backend/config.yaml` for configuration. Key sections:

### Camera Configuration
```yaml
cameras:
  front:
    hostname: firecamfront.local
    port: 80
    stream_path: /front/stream
  # ... other cameras
```

### Email Configuration
```yaml
email:
  enable: true
  sender: your-email@gmail.com
  app_pass: your-app-password
  receiver:
    - receiver1@gmail.com
    - receiver2@gmail.com
  interval: 60  # seconds between alerts
  alert_types:
    - fire
    - smoke
```

### Stream Settings
```yaml
stream:
  target_fps: 15.0
  frame_interval: 0.2
  inference_every_n: 5
  jpeg_quality: 60
```

## Features

- **Multi-Camera Streaming:** Simultaneous video streams from 4 cameras
- **Real-Time Fire Detection:** ML-powered fire and smoke detection
- **Email Alerts:** Automated email notifications on fire/smoke detection
- **Event Logging:** CSV logging of all detection events
- **Remote Control:** Web-based robot motor and actuator control
- **Health Monitoring:** Real-time camera health and FPS monitoring
- **Configurable Settings:** Easy configuration via web interface and YAML

## Troubleshooting

### Cameras Not Connecting

1. **Check WiFi Connection:**
   - Ensure hotspot is on 2.4GHz frequency
   - Verify SSID is exactly `fireextinguisher`
   - Verify password is exactly `fire12345678`

2. **Check Camera Status:**
   - Verify cameras appear in router connection history
   - Try accessing camera streams directly:
     - `http://firecamfront.local/front/stream`
     - `http://firecamback.local/back/stream`
     - etc.

3. **DNS Resolution:**
   - If `.local` hostnames don't work, use IP addresses
   - Find camera IPs from router admin panel
   - Update `config.yaml` with IP addresses

### Dashboard Not Loading

1. **Check Server Status:**
   - Verify Python process is running
   - Check for error messages in terminal

2. **Check Port:**
   - Ensure port 8001 is not in use
   - Try accessing `http://127.0.0.1:8001`

3. **Check Dependencies:**
   - Ensure virtual environment is activated
   - Reinstall dependencies: `pip install -r requirements.txt`

### Email Alerts Not Working

1. **Gmail App Password:**
   - Use Gmail App Password, not regular password
   - Generate at: https://myaccount.google.com/apppasswords

2. **Check Configuration:**
   - Verify email is enabled in config
   - Check receiver email addresses are correct
   - Verify alert types are selected

3. **Check Logs:**
   - Look for email-related errors in terminal output

### Video Stream Issues

1. **No Signal:**
   - Check camera is powered on
   - Verify camera is connected to WiFi
   - Restart camera stream from dashboard

2. **Low FPS:**
   - Check WiFi signal strength
   - Reduce `target_fps` in config.yaml
   - Increase `frame_interval` in config.yaml

3. **Laggy Streams:**
   - Reduce number of active streams
   - Lower `jpeg_quality` in config.yaml
   - Check network bandwidth

## File Structure

```
multi_fire_extinguisher/
├── backend/
│   ├── config.yaml          # System configuration
│   ├── dashboard.py         # Main FastAPI application
│   ├── stream_utils.py      # Video streaming utilities
│   ├── file_handling.py     # Event logging
│   ├── send_alert.py        # Email alert system
│   └── templates/
│       └── dashboard.html   # Web dashboard UI
├── firmware/
│   ├── front.ino           # Front camera firmware
│   ├── back.ino            # Back camera firmware
│   ├── left.ino            # Left camera firmware
│   └── right.ino           # Right camera firmware
├── Model/
│   └── trained_model.pth   # ML model for fire detection
├── data/
│   ├── events.csv          # Detection event logs
│   └── snaps/              # Captured snapshots
├── docs/                   # Documentation
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Development

### Model Training
The fire detection model (`Model/trained_model.pth`) can be retrained with new data. See documentation in `docs/` for details.

### Firmware Updates
Camera firmware is located in `firmware/`. Upload to ESP32-CAM using Arduino IDE.

## Support

For detailed technical documentation, see:
- `docs/backend_doc.md` - Backend implementation details
- `docs/firmware_doc.md` - Firmware implementation details

## License

This project is for testing and development purposes.

---

**Note:** This system is designed for testing and development. Ensure proper safety measures are in place when deploying in real-world fire detection scenarios.
