# Fire Detection Web Dashboard

A FastAPI-based web dashboard for real-time multi-camera fire detection monitoring.

What the Dashboard Does
Reads backend/dashboard.py (main application)
Imports functions from backend/stream_utils.py
Serves HTML from backend/templates/dashboard.html
Loads ML model from Model/trained_model.pth
Connects to ESP32 cameras (configured in CAMERAS dict)

```bash
backend/
├── dashboard.py          ← Main dashboard application
├── stream_utils.py       ← Shared utilities (imported)
└── templates/
    └── dashboard.html    ← HTML UI template

Model/
└── trained_model.pth     ← ML model file (loaded at runtime)
```

## Features

- ✅ **Live MJPEG Streaming** - Low-latency video streams for all 4 cameras
- ✅ **2×2 Grid Layout** - Responsive design works on laptop, tablet, and mobile
- ✅ **Inference Overlays** - Real-time Fire/Smoke/Neutral detection with bounding boxes
- ✅ **Health Monitoring** - Online/offline status and FPS for each camera
- ✅ **Zero OpenCV GUI** - No desktop windows, pure web interface
- ✅ **Low CPU Usage** - Efficient MJPEG streaming

## Quick Start

### Installation

Make sure you have the required dependencies:

```bash
pip install -r requirements.txt
```

### Running the Dashboard

Simply run:

```bash
cd backend
python dashboard.py
```

Then open your browser to:
```
http://localhost:8001
```

The dashboard will automatically:
1. Start all 4 camera streams (front, back, left, right)
2. Load the ML model for inference
3. Begin streaming MJPEG video with overlays

## API Endpoints

- `GET /` - Main dashboard HTML page
- `GET /stream/{camera_name}` - MJPEG stream for a camera (front, back, left, right)
- `GET /health` - JSON health status for all cameras
- `GET /health/{camera_name}` - JSON health status for a specific camera

## Architecture

The dashboard uses:
- **Multiprocessing** - Each camera stream runs in a separate process
- **Central Inference Worker** - Single process handles all ML inference
- **Shared State** - Frame queues and results shared via multiprocessing.Manager
- **MJPEG Streaming** - Efficient video delivery over HTTP

## Camera Configuration

Cameras are configured in `dashboard.py`:

```python
CAMERAS = {
    "front": {
        "hostname": "firecamfront.local",
        "port": 80,
        "stream_path": "/front/stream",
    },
    # ... etc
}
```

Update these if your camera hostnames/IPs are different.

## Model Path

The model is expected at:
```
../Model/trained_model.pth
```

The dashboard will continue without inference if the model is not found.

## Stopping the Dashboard

Press `Ctrl+C` to gracefully stop all streams and the server.

## Mobile/Tablet Support

The dashboard is fully responsive and works on:
- Desktop browsers (Chrome, Firefox, Safari, Edge)
- Mobile browsers (iOS Safari, Chrome Mobile)
- Tablets (iPad, Android tablets)

## Troubleshooting

**Cameras show "OFFLINE"**
- Check camera hostnames are resolvable (mDNS or IP)
- Verify camera streams are accessible
- Check network connectivity

**No inference overlays**
- Verify model file exists at `Model/trained_model.pth`
- Check console for model loading errors

**High CPU usage**
- Reduce `INFERENCE_EVERY_N` value (runs inference less frequently)
- Lower MJPEG quality in `cv2.imencode` call

