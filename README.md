# Multi Fire Extinguisher

Streamlit-based live fire/smoke detection UI that pulls frames from ESP32-CAM endpoints, performs inference with a trained model, overlays results, and optionally sends email alerts.


## Features
- Live video frame polling from static IP camera endpoints
- Fire/Smoke detection using a pre-trained PyTorch model
- Bounding box and label overlay on frames
- Email alerts (Gmail app password) with captured frame attachment
- Configurable thresholds, intervals, and camera URL
- Single Save Settings button to persist configuration during session


## Project Structure
```
multi_fire_extinguisher/
├─ app.py                  # Streamlit app (UI + controller)
├─ requirements.txt        # Python dependencies
├─ README.md               # This file
├─ Model/
│  └─ trained_model.pth    # Pre-trained model (do not commit large files)
├─ src/
│  ├─ detector.py          # Model load + predict function
│  ├─ emailer.py           # Email helper (yagmail wrapper)
│  └─ utils.py             # Camera frame fetch + drawing helpers
├─ Arduino_scripts/        # ESP32-CAM/Arduino sketches
└─ .gitignore
```


## Prerequisites
- Python 3.9+ recommended (3.12 supported as per current environment)
- Streamlit
- PyTorch (matching the environment used to train the model)
- OpenCV
- yagmail (optional, only if email alerts are enabled)


## Setup (Virtual Environment)
From the project root directory:

```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows (PowerShell)
# .\venv\Scripts\Activate.ps1

pip3 install --upgrade pip
pip3 install -r requirements.txt
```


## Camera Details (Static IPs)
Add these static IPs to stream the cameras. Use any one at a time as the Camera URL in the app, or switch as needed.

- Front:  http://192.168.0.50/front/cam-mid.jpg
- Back:   http://192.168.0.51/back/cam-mid.jpg
- Right:  http://192.168.0.52/right/cam-mid.jpg
- Left:   http://192.168.0.53/left/cam-mid.jpg


## ESP32-CAM Wi‑Fi Hotspot
Turn on a hotspot with the following SSID and password (used by the cameras):

```c
const char* WIFI_SSID = "fireextinguisher";
const char* WIFI_PASS = "fire12345678";
```

Steps:
1) Power on all cameras
2) Wait for ~1 minute for the cameras to connect and stabilize
3) Connect the laptop to the same Wi‑Fi network (fireextinguisher)


## Run the App
From the project root directory:

```bash
# Activate environment
source venv/bin/activate

# Launch UI
streamlit run app.py
```

It will open a web page in your browser. Configure settings in the sidebar, then click Start Stream.


## Email Alerts (Optional)
- The app supports sending email alerts when detections exceed the configured probability threshold.