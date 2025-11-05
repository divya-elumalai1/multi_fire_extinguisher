import streamlit as st
import time
import cv2
from datetime import datetime
from src.detector import load_model, predict_frame
from src.utils import fetch_frame_from_url, draw_bbox_on_frame
from src.emailer import Emailer

# ----------------------------
# Streamlit Page Configuration
# ----------------------------
st.set_page_config(page_title="Multi Fire Extinguisher", layout="wide")

# ----------------------------
# Default Settings
# ----------------------------
defaults = {
    "CAM_FRONT": "http://192.168.0.50/front/cam-mid.jpg",
    "CAM_BACK": "http://192.168.0.51/back/cam-mid.jpg",
    "CAM_RIGHT": "http://192.168.0.52/right/cam-mid.jpg",
    "CAM_LEFT": "http://192.168.0.53/left/cam-mid.jpg",
    "model_path": "Model/trained_model.pth",
    "prob_threshold": 85,
    "email_enable": False,
    "email_sender": "multifireextinguisher@gmail.com",
    "email_app_pass": "kusw ujez lwkm vtud",
    "email_receiver": "",
    "email_interval": 60,
    "frame_delay": 0.2,
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ----------------------------
# Sidebar Settings
# ----------------------------
st.sidebar.title("⚙️ Settings")

st.sidebar.subheader("Camera URLs")
CAM_FRONT = st.sidebar.text_input("Front Camera URL", value=st.session_state.CAM_FRONT)
CAM_BACK = st.sidebar.text_input("Back Camera URL", value=st.session_state.CAM_BACK)
CAM_RIGHT = st.sidebar.text_input("Right Camera URL", value=st.session_state.CAM_RIGHT)
CAM_LEFT = st.sidebar.text_input("Left Camera URL", value=st.session_state.CAM_LEFT)

st.sidebar.divider()

model_path = st.sidebar.text_input("Model path", value=st.session_state.model_path)
prob_threshold = st.sidebar.slider("Alert Probability Threshold (%)", 50, 100, st.session_state.prob_threshold)
email_enable = st.sidebar.checkbox("Enable Email Alerts", value=st.session_state.email_enable)

with st.sidebar.expander("Email Configuration", expanded=False):
    email_sender = st.text_input("Email Sender (Gmail)", value=st.session_state.email_sender)
    email_app_pass = st.text_input("Email App Password", type="password", value=st.session_state.email_app_pass)
    email_receiver = st.text_input("Email Receiver", value=st.session_state.email_receiver)
    email_interval = st.number_input("Email Interval (s)", min_value=10, value=st.session_state.email_interval)

frame_delay = st.sidebar.number_input("Frame Delay (s)", min_value=0.05, value=st.session_state.frame_delay, step=0.05)

# ----------------------------
# Save Settings Button ✅
# ----------------------------
if st.sidebar.button("💾 Save Settings"):
    st.session_state.CAM_FRONT = CAM_FRONT
    st.session_state.CAM_BACK = CAM_BACK
    st.session_state.CAM_RIGHT = CAM_RIGHT
    st.session_state.CAM_LEFT = CAM_LEFT
    st.session_state.model_path = model_path
    st.session_state.prob_threshold = prob_threshold
    st.session_state.email_enable = email_enable
    st.session_state.email_sender = email_sender
    st.session_state.email_app_pass = email_app_pass
    st.session_state.email_receiver = email_receiver
    st.session_state.email_interval = email_interval
    st.session_state.frame_delay = frame_delay
    st.toast("✅ Settings saved successfully!")

# ----------------------------
# Load Model Once (Cached)
# ----------------------------
@st.cache_resource
def get_model(path):
    return load_model(path)

try:
    model = get_model(st.session_state.model_path)
except Exception as e:
    st.error(f"❌ Failed to load model: {e}")
    st.stop()

emailer = Emailer(
    st.session_state.email_sender,
    st.session_state.email_app_pass,
    st.session_state.email_receiver
) if st.session_state.email_enable else None

# ----------------------------
# Stream Controls
# ----------------------------
st.title("🔥 Multi Fire Extinguisher — Live Multi-Camera Detection")

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("📹 Live Streams")
with col2:
    start = st.button("▶️ Start Stream")
    stop = st.button("⏹️ Stop Stream")
    status_placeholder = st.empty()

if start:
    st.session_state.running = True
if stop:
    st.session_state.running = False

if "running" not in st.session_state:
    st.session_state.running = False

# ----------------------------
# Multi-Camera Stream
# ----------------------------
CAMERAS = {
    "Front": st.session_state.CAM_FRONT,
    "Back": st.session_state.CAM_BACK,
    "Right": st.session_state.CAM_RIGHT,
    "Left": st.session_state.CAM_LEFT,
}

if st.session_state.running:
    last_sent_time = 0
    status_placeholder.info("🟢 Streaming all cameras... Press Stop to end.")

    # Create 4 placeholders (2x2 layout)
    row1_col1, row1_col2 = st.columns(2)
    row2_col1, row2_col2 = st.columns(2)
    cam_placeholders = {
        "Front": row1_col1.empty(),
        "Back": row1_col2.empty(),
        "Right": row2_col1.empty(),
        "Left": row2_col2.empty(),
    }

    while st.session_state.running:
        for cam_name, cam_url in CAMERAS.items():
            frame = fetch_frame_from_url(cam_url)
            if frame is None:
                cam_placeholders[cam_name].warning(f"⚠️ {cam_name} camera offline...")
                continue

            # Predict
            label, prob, bbox = predict_frame(frame, model)
            color = (0, 255, 0) if label == "Neutral" else (0, 0, 255)
            frame = draw_bbox_on_frame(frame, bbox, label, prob, color=color)

            # Email alert (one for all)
            if emailer and label in ("Fire", "Smoke") and prob >= st.session_state.prob_threshold:
                if time.time() - last_sent_time > st.session_state.email_interval:
                    subject = f"🔥 ALERT: {label} detected in {cam_name} camera"
                    html = f"""
                    <div style='font-family: Arial, sans-serif;'>
                        <h3>⚠️ {label} Detected in {cam_name} Camera</h3>
                        <p><b>Probability:</b> {prob:.2f}%</p>
                        <p><b>Time:</b> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                    """
                    emailer.send_alert(subject, html, frame)
                    last_sent_time = time.time()

            # Convert to RGB and show
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            cam_placeholders[cam_name].image(frame_rgb, channels="RGB", width=480, caption=f"{cam_name} Camera")

        time.sleep(st.session_state.frame_delay)

    status_placeholder.info("⏸️ Stream stopped.")