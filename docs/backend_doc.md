# Backend Technical Implementation Documentation

## Table of Contents
1. [Overview](#overview)
2. [Configuration System](#configuration-system)
3. [Architecture](#architecture)
4. [Core Components](#core-components)
5. [API Endpoints](#api-endpoints)
6. [Data Flow](#data-flow)
7. [File Handling System](#file-handling-system)
8. [Alert System](#alert-system)
9. [Multiprocessing Architecture](#multiprocessing-architecture)
10. [Streaming System](#streaming-system)

---

## Overview

The backend system is a FastAPI-based multi-camera fire detection monitoring system that:
- Streams video from 4 ESP32-CAM devices simultaneously
- Performs real-time ML inference for fire/smoke detection
- Logs detection events to CSV
- Sends email alerts when fire/smoke is detected
- Provides a web dashboard for monitoring

**Main Entry Point:** `backend/dashboard.py`

---

## Configuration System

The configuration system is the central component that manages all system parameters. It uses a YAML-based configuration file (`config.yaml`) with intelligent fallback defaults.

### Configuration File Structure

The `config.yaml` file is located at `backend/config.yaml` and contains the following sections:

```yaml
cameras:
  back:
    hostname: firecamback.local
    port: 81
    stream_path: /back/stream
  front:
    hostname: firecamfront.local
    port: 80
    stream_path: /front/stream
  left:
    hostname: firecamleft.local
    port: 82
    stream_path: /left/stream
  right:
    hostname: firecamright.local
    port: 83
    stream_path: /right/stream

email:
  alert_types:
  - fire
  app_pass: <app pass key>
  enable: true
  interval: 60
  receiver:
  - <receiver@gmail.com>
  - <receiver2@gmail.com>
  sender: multifireextinguisher@gmail.com

file_handling:
  csv_header:
  - datetime
  - camera
  - event
  - confidence_level
  max_records: 1200
  record_update: 5

motor:
  hostname: firecamfront.local
  path: /front/motor
  port: 80

stream:
  frame_interval: 0.2
  inference_every_n: 5
  jpeg_quality: 60
  target_fps: 15.0
```

### Configuration Loading Mechanism

The configuration is loaded through the `load_config()` function in `dashboard.py` (lines 52-104):

#### 1. **Default Configuration**
The system defines comprehensive defaults that ensure the system works even without a config file:

```python
default_config = {
    "cameras": {
        "front": {"hostname": "firecamfront.local", "port": 80, "stream_path": "/front/stream"},
        "back": {"hostname": "firecamback.local", "port": 81, "stream_path": "/back/stream"},
        "left": {"hostname": "firecamleft.local", "port": 82, "stream_path": "/left/stream"},
        "right": {"hostname": "firecamright.local", "port": 83, "stream_path": "/right/stream"},
    },
    "motor": {
        "hostname": "firecamfront.local",
        "port": 80,
        "path": "/front/motor"
    },
    "stream": {
        "target_fps": 2.0,
        "frame_interval": 0.5,
        "inference_every_n": 5,
        "jpeg_quality": 60
    }
}
```

#### 2. **YAML File Loading**
The system attempts to load `config.yaml` from the backend directory:
- If the file exists, it uses `yaml.safe_load()` to parse it
- The YAML configuration is merged with defaults (YAML values take precedence)
- If loading fails, the system falls back to defaults and logs an error

#### 3. **Configuration Merging Strategy**
The merge process (lines 84-94) is section-aware:
- **Cameras**: Updates individual camera configs while preserving defaults for missing cameras
- **Motor**: Updates motor config with YAML values
- **Stream**: Updates stream parameters
- **Email**: Creates email section if missing, then updates it

#### 4. **Runtime Configuration Variables**
After loading, configuration values are extracted into module-level variables (lines 110-115):

```python
DEFAULT_CAMERAS = config["cameras"]
DEFAULT_MOTOR = config["motor"]
TARGET_FPS = config["stream"]["target_fps"]
FRAME_INTERVAL = config["stream"]["frame_interval"]
INFERENCE_EVERY_N = config["stream"]["inference_every_n"]
JPEG_QUALITY = config["stream"]["jpeg_quality"]
```

### Configuration Usage Throughout the System

#### **1. Camera Configuration**

**Location:** `dashboard.py` lines 110, 118, 195-203

**Usage:**
- `current_cameras` dictionary stores active camera configurations (initialized from `DEFAULT_CAMERAS`)
- When starting a camera process, the config is passed to `stream_camera_worker()`:
  ```python
  config = current_cameras[name]
  # Used to construct stream URL: http://{hostname}:{port}{stream_path}
  ```

**Dynamic Updates:**
- Camera configs can be updated via `POST /api/config` endpoint (lines 256-264)
- When updated, the affected camera process is restarted with new config
- Runtime changes are stored in `current_cameras` (separate from file)

#### **2. Stream Configuration**

**Location:** `dashboard.py` lines 112-115, 540-554

**Parameters:**
- `TARGET_FPS`: Target frames per second (default: 15.0)
- `FRAME_INTERVAL`: Minimum time between frames (default: 0.2 seconds)
- `INFERENCE_EVERY_N`: Run inference every Nth frame (default: 5)
- `JPEG_QUALITY`: JPEG compression quality 0-100 (default: 60)

**Usage:**
- `FRAME_INTERVAL` controls frame throttling in `stream_camera_worker()` (line 553)
- `INFERENCE_EVERY_N` determines when to queue frames for inference (line 596)
- `JPEG_QUALITY` used in `cv2.imencode()` for MJPEG streaming (line 623)

#### **3. Motor Configuration**

**Location:** `dashboard.py` lines 111, 119, 308-337

**Usage:**
- Stored in `current_motor` dictionary
- Used in `POST /api/motor/send` endpoint to construct motor command URLs
- Format: `http://{hostname}:{port}{path}?cmd={command}`
- DNS resolution is performed to avoid ESP32 DNS issues

#### **4. Email Configuration**

**Location:** `send_alert.py` lines 23-74, 210-221

**Loading Mechanism:**
- Uses caching to avoid reloading on every call (30-second TTL)
- Loaded via `load_email_config()` function
- Falls back to defaults if file missing or invalid

**Parameters:**
- `enable`: Boolean to enable/disable email alerts
- `sender`: Gmail address for sending alerts
- `app_pass`: Gmail app password (not regular password)
- `receiver`: List of recipient email addresses
- `interval`: Minimum seconds between emails (default: 60)
- `alert_types`: List of event types that trigger alerts (e.g., ["fire", "smoke"])

**Usage:**
- Checked in `check_and_send_alert()` before sending emails
- Interval enforcement prevents email spam
- Only sends for events matching `alert_types`

**Dynamic Updates:**
- Can be updated via `POST /api/email/config` endpoint (lines 282-306 in dashboard.py)
- Changes are written directly to `config.yaml` file
- Cache is invalidated on next call (or after 30 seconds)

#### **5. File Handling Configuration**

**Location:** `file_handling.py` lines 42-71, 74-79

**Loading Mechanism:**
- Loaded via `load_file_handling_config()` function
- Merges with defaults if YAML section missing

**Parameters:**
- `max_records`: Maximum number of records in CSV (default: 1200)
- `csv_header`: Column names for CSV file (default: ['datetime', 'camera', 'event', 'confidence_level'])
- `record_update`: Seconds between CSV updates (default: 5)

**Usage:**
- `MAX_RECORDS` used in `trim_old_records()` to limit CSV size
- `CSV_HEADER` used when creating/validating CSV file structure
- `Record_update` controls periodic flush interval in background thread

### Configuration Access Patterns

#### **1. Module-Level Loading**
Configuration is loaded once at module import time:
```python
config = load_config()  # Line 107 in dashboard.py
```

#### **2. Runtime Access**
- Camera configs: Accessed via `current_cameras` dictionary
- Stream params: Accessed via module-level constants
- Email config: Loaded on-demand with caching (send_alert.py)
- File handling: Loaded once at module import (file_handling.py)

#### **3. Dynamic Updates**
- Camera configs: Updated via API, stored in memory (`current_cameras`)
- Email config: Updated via API, written to file (`config.yaml`)
- Motor config: Updated via API, stored in memory (`current_motor`)

### Configuration Validation

The system performs minimal validation:
- Camera configs must have `hostname`, `port`, and `stream_path`
- Email configs validate `enable` (boolean), `interval` (positive integer)
- File handling validates `max_records` (positive integer)

### Error Handling

- **Missing config file**: Falls back to defaults, logs warning
- **Invalid YAML**: Falls back to defaults, logs error
- **Missing sections**: Uses defaults for missing sections
- **Invalid values**: Uses defaults, logs warning

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Server                        │
│                  (dashboard.py)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   API Routes │  │  MJPEG Gen   │  │  HTML Serve  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
│ Camera Proc  │ │ Camera Proc  │ │ Camera... │
│   (front)    │ │   (back)     │ │           │
└───────┬──────┘ └──────┬──────┘ └─────┬──────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
                ┌───────▼────────┐
                │ Inference Queue │
                └───────┬────────┘
                        │
                ┌───────▼────────┐
                │ Inference Proc │
                │  (ML Model)    │
                └───────┬────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐
│ File Handler │ │ Alert System│ │ Health    │
│  (CSV Log)   │ │  (Email)    │ │ Monitor   │
└──────────────┘ └─────────────┘ └───────────┘
```

### Process Architecture

1. **Main Process**: FastAPI server, handles HTTP requests
2. **Camera Processes**: One per camera, captures frames from ESP32-CAM
3. **Inference Process**: Single process runs ML model on queued frames
4. **Background Threads**: Health monitoring, CSV flushing

### Shared State

Managed via `multiprocessing.Manager()`:
- `frame_queues`: Dict of queues, one per camera
- `result_map`: Dict storing latest inference results per camera
- `stream_flags`: Dict of boolean flags to control camera processes
- `health_status`: Dict storing health metrics per camera

---

## Core Components

### 1. Dashboard Application (`dashboard.py`)

**Responsibilities:**
- FastAPI server setup and routing
- Process management (start/stop camera processes)
- Configuration loading and management
- MJPEG stream generation
- Health monitoring

**Key Functions:**
- `load_config()`: Loads and merges configuration
- `start_camera_process()`: Starts a camera capture process
- `stop_camera_process()`: Stops a camera process
- `stream_camera_worker()`: Worker function for camera capture
- `inference_worker()`: Worker function for ML inference
- `mjpeg_generator()`: Generates MJPEG stream for web display

### 2. Stream Utilities (`stream_utils.py`)

**Responsibilities:**
- ESP32-CAM stream capture
- ML model loading and inference
- Frame preprocessing
- Bounding box detection and drawing

**Key Functions:**
- `capture_live_stream()`: Captures MJPEG stream from ESP32-CAM with reconnection logic
- `load_model()`: Loads PyTorch model (cached)
- `predict_frame()`: Runs inference on a frame
- `preprocess_image_from_cv()`: Converts OpenCV frame to model input
- `draw_bbox_on_frame()`: Draws bounding box and label on frame

**Stream Capture Details:**
- Uses OpenCV `VideoCapture` with FFMPEG backend
- Implements robust reconnection with timeout handling
- Maintains last valid frame during disconnections
- DNS resolution with retry logic
- Thread-based timeout wrapper for `cap.read()`

### 3. File Handling (`file_handling.py`)

**Responsibilities:**
- CSV event logging
- Frame snapshot saving
- Periodic data flushing

**Key Functions:**
- `log_detection_result()`: Updates camera status with detection results
- `update_camera_status()`: Updates internal status tracking
- `_flush_events_to_csv()`: Writes all camera statuses to CSV
- `_save_frame_snapshots()`: Saves annotated JPEG snapshots
- `_periodic_flush_worker()`: Background thread for periodic updates

**Data Flow:**
1. Detection results call `log_detection_result()`
2. Status stored in `_camera_status` dict
3. Background thread flushes to CSV every `record_update` seconds
4. Snapshots saved with annotations during flush

### 4. Alert System (`send_alert.py`)

**Responsibilities:**
- Email alert generation and sending
- Event monitoring
- Alert throttling

**Key Functions:**
- `check_and_send_alert()`: Main function to check events and send alerts
- `load_email_config()`: Loads email configuration with caching
- `read_latest_events()`: Reads recent events from CSV
- `check_for_alerts()`: Identifies cameras with fire/smoke
- `create_email_message()`: Generates HTML email content
- `Emailer`: Class for sending emails via yagmail

**Alert Logic:**
1. Checks if email enabled and interval elapsed
2. Reads latest 4 events (one per camera)
3. Filters for alert types (fire/smoke)
4. Collects snapshot images for alerting cameras
5. Sends HTML email with attachments

---

## API Endpoints

### Configuration Endpoints

#### `GET /api/config`
Returns current camera configurations.

**Response:**
```json
{
  "front": {
    "hostname": "firecamfront.local",
    "port": 80,
    "stream_path": "/front/stream"
  },
  ...
}
```

#### `POST /api/config`
Updates camera configurations.

**Request Body:**
```json
{
  "cameras": {
    "front": {
      "hostname": "192.168.1.100",
      "port": 80,
      "stream_path": "/front/stream"
    }
  }
}
```

**Behavior:**
- Updates `current_cameras` dictionary
- Restarts affected camera processes with new config

#### `GET /api/motor/config`
Returns current motor configuration.

#### `POST /api/motor/config`
Updates motor configuration.

#### `GET /api/email/config`
Returns email configuration from `config.yaml`.

#### `POST /api/email/config`
Updates email configuration in `config.yaml` file.

**Request Body:**
```json
{
  "enable": true,
  "sender": "sender@gmail.com",
  "app_pass": "app_password",
  "receiver": ["recipient@gmail.com"],
  "interval": 60,
  "alert_types": ["fire", "smoke"]
}
```

### Control Endpoints

#### `POST /api/control/start`
Starts camera streams.

**Request Body:**
```json
{
  "cameras": ["front", "back", "left", "right"]
}
```

#### `POST /api/control/stop`
Stops camera streams.

#### `POST /api/restart/{camera_name}`
Restarts a specific camera process.

### Motor Control

#### `POST /api/motor/send`
Sends motor command to ESP32.

**Request Body:**
```json
{
  "cmd": "0"
}
```

**Behavior:**
- Resolves hostname to IP
- Sends HTTP GET request to motor endpoint
- Returns status

### Streaming Endpoints

#### `GET /`
Serves the main dashboard HTML page.

#### `GET /stream/{camera_name}`
Returns MJPEG stream for specified camera.

**Media Type:** `multipart/x-mixed-replace; boundary=frame`

**Behavior:**
- Reads frames from camera's frame queue
- Encodes as JPEG
- Streams with MJPEG protocol
- Sends placeholder frame if queue empty or camera offline

#### `GET /health`
Returns health status for all cameras.

**Response:**
```json
{
  "front": {
    "online": true,
    "last_frame_time": 1234567890.123,
    "fps": 15.2
  },
  ...
}
```

---

## Data Flow

### Frame Capture Flow

```
ESP32-CAM → capture_live_stream() → stream_camera_worker()
    ↓
Frame Queue (multiprocessing.Queue)
    ↓
mjpeg_generator() → HTTP Response (MJPEG)
```

### Inference Flow

```
stream_camera_worker() → Inference Queue
    ↓
inference_worker() → ML Model → Result Map
    ↓
stream_camera_worker() → Annotate Frame → Frame Queue
```

### Event Logging Flow

```
inference_worker() → log_detection_result()
    ↓
_camera_status (dict) → Background Thread
    ↓
_flush_events_to_csv() → events.csv
    ↓
_save_frame_snapshots() → data/snaps/{camera}.jpeg
```

### Alert Flow

```
inference_worker() → check_and_send_alert()
    ↓
read_latest_events() → events.csv
    ↓
check_for_alerts() → Filter fire/smoke
    ↓
get_image_paths() → data/snaps/
    ↓
Emailer.send_alert_email() → Gmail SMTP
```

---

## File Handling System

### CSV Event Logging

**File Location:** `data/events.csv`

**Structure:**
```csv
datetime,camera,event,confidence_level
2025-12-31 13:44:37,front,smoke,57.0
2025-12-31 13:44:37,back,neutral,52.5
```

**Update Frequency:** Every `record_update` seconds (default: 5)

**Record Management:**
- Maximum records: `max_records` (default: 1200)
- Old records trimmed automatically
- All 4 cameras written per update (active cameras with real status, inactive as neutral)

### Snapshot System

**Directory:** `data/snaps/`

**Files:** `{camera}.jpeg` (front.jpeg, back.jpeg, left.jpeg, right.jpeg)

**Content:**
- Latest annotated frame from each camera
- Includes bounding boxes and labels
- Updated during CSV flush (every 5 seconds)

**Annotation:**
- Bounding box drawn if detected
- Label and confidence text overlay
- Color coding: Red (fire), Orange (smoke), Green (neutral)

---

## Alert System

### Email Configuration

**Provider:** Gmail (via yagmail library)

**Authentication:** App Password (not regular password)

**Configuration Source:** `config.yaml` → `email` section

### Alert Triggering

**Conditions:**
1. Email enabled (`enable: true`)
2. Interval elapsed (default: 60 seconds)
3. Latest events contain fire/smoke
4. Snapshot images available

**Alert Types:** Configurable via `alert_types` (default: ["fire", "smoke"])

### Email Content

**Format:** HTML email with:
- Alert type (FIRE/SMOKE detected)
- Camera locations
- Detection details (list)
- Timestamp
- Attached images (one per alerting camera)

### Throttling

- Minimum interval between emails: `interval` seconds
- Prevents email spam during continuous detections
- Tracks `last_email_time` globally

---

## Multiprocessing Architecture

### Process Structure

1. **Main Process** (dashboard.py)
   - FastAPI server
   - Process manager
   - HTTP request handling

2. **Camera Processes** (one per camera)
   - Function: `stream_camera_worker()`
   - Captures frames from ESP32-CAM
   - Queues frames for inference
   - Annotates frames with results
   - Puts frames in display queue

3. **Inference Process** (single)
   - Function: `inference_worker()`
   - Loads ML model
   - Processes frames from inference queue
   - Updates result map
   - Triggers logging and alerts

### Inter-Process Communication

**Queues:**
- `frame_queues[camera]`: Camera → Display (maxsize=1)
- `inference_queue`: Camera → Inference (maxsize=1)

**Shared Dicts (Manager):**
- `result_map`: Inference → Camera (latest results)
- `stream_flags`: Main → Camera (control flags)
- `health_status`: Camera → Main (health metrics)

### Process Lifecycle

**Start:**
1. Main process creates Manager and queues
2. Starts inference process
3. Starts camera processes on demand (lazy start)

**Stop:**
1. Main process sets `stream_flags[name] = False`
2. Camera process checks flag and exits loop
3. Process joins with timeout
4. Force terminate if still alive

---

## Streaming System

### MJPEG Protocol

**Format:** `multipart/x-mixed-replace` with boundary `frame`

**Frame Format:**
```
--frame\r\n
Content-Type: image/jpeg\r\n\r\n
[JPEG bytes]
\r\n
```

### Stream Generation

**Function:** `mjpeg_generator()` in dashboard.py

**Behavior:**
- Reads from camera's frame queue
- Timeout: 2.0 seconds
- Sends placeholder if queue empty or camera offline
- Continuous streaming (never stops yielding)

### Frame Throttling

**Logic:** (lines 540-554 in dashboard.py)
- Skip frame if:
  - Queue not empty (has frame waiting)
  - AND time since last frame < `FRAME_INTERVAL`
  - AND time since last frame < starvation timeout (1.5s)
- Always add frame if queue empty (prevent starvation)

### Health Monitoring

**Metrics:**
- `online`: Boolean (true if frames received recently)
- `last_frame_time`: Timestamp of last frame
- `fps`: Calculated from recent frame times

**Update:**
- Updated in `stream_camera_worker()` on each frame
- Health check thread marks offline if no frame for 8 seconds

---

## Error Handling

### Stream Errors

- **Connection failures**: Reconnection loop with exponential backoff
- **DNS failures**: Retry with fallback to hostname
- **Frame read timeouts**: Thread-based timeout wrapper
- **Queue full**: Drop oldest frame, add new one

### Inference Errors

- **Model loading failure**: System continues without inference
- **Inference errors**: Logged, don't break stream
- **Queue full**: Skip inference for that frame

### File System Errors

- **CSV write errors**: Logged, don't break system
- **Snapshot save errors**: Silently fail, don't break CSV writing
- **Missing directories**: Auto-created

---

## Performance Considerations

### Optimization Strategies

1. **Frame Throttling**: Prevents queue overflow
2. **Inference Skipping**: Only every Nth frame
3. **Queue Sizing**: Small queues (maxsize=1) prevent buffering
4. **JPEG Quality**: Configurable compression (default: 60)
5. **Caching**: Model loaded once, config cached

### Resource Usage

- **CPU**: Moderate (inference is CPU-bound)
- **Memory**: Low (small queues, frames not buffered)
- **Network**: Depends on stream quality and FPS
- **Disk**: CSV grows to max_records, then trims

---

## Dependencies

**Core:**
- `fastapi`: Web framework
- `uvicorn`: ASGI server
- `opencv-python`: Video capture and processing
- `torch`: ML model inference
- `yaml`: Configuration parsing

**Utilities:**
- `yagmail`: Email sending
- `numpy`: Array operations
- `PIL`: Image processing

---

## Deployment

### Running the Server

```bash
cd backend
python dashboard.py
```

**Default Port:** 8001

**Access:** `http://localhost:8001`

### Environment Requirements

- Python 3.9+
- Virtual environment recommended
- Network access to ESP32-CAM devices
- Model file at `Model/trained_model.pth`

### Configuration Management

- Edit `backend/config.yaml` for persistent changes
- Use API endpoints for runtime changes (camera configs)
- Email config changes require file write (API updates file)

---

## Troubleshooting

### Common Issues

1. **Cameras show OFFLINE**
   - Check hostname resolution (mDNS or IP)
   - Verify network connectivity
   - Check camera firmware is running

2. **No inference overlays**
   - Verify model file exists
   - Check console for model loading errors
   - Verify `INFERENCE_EVERY_N` is appropriate

3. **High CPU usage**
   - Reduce `INFERENCE_EVERY_N`
   - Lower `TARGET_FPS`
   - Reduce `JPEG_QUALITY`

4. **Email alerts not sending**
   - Check `enable: true` in config
   - Verify Gmail app password
   - Check interval hasn't elapsed
   - Verify alert_types include detected events

5. **CSV not updating**
   - Check `record_update` interval
   - Verify background thread is running
   - Check file permissions

---

## Future Enhancements

Potential improvements:
- WebSocket support for real-time updates
- Database backend instead of CSV
- Multiple model support
- Video recording on alerts
- Mobile app integration
- Advanced alert routing (SMS, push notifications)