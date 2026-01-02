"""
Shared utilities for multi-camera streaming system.
Contains common functions for model loading, preprocessing, and frame processing.
"""

import cv2
import socket
import time
import os
import torch
import warnings
from torchvision import transforms
from PIL import Image
import functools
import numpy as np
import json
import threading

# Suppress PyTorch warnings
warnings.filterwarnings("ignore", category=UserWarning, module="torch.nn.modules.module")
# Reduce OpenCV logging
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

# -----------------------------
# Constants
# -----------------------------
CLASS_NAMES = ['Fire', 'Neutral', 'Smoke']


# -----------------------------
# Model Functions
# -----------------------------

@functools.lru_cache(maxsize=1)
def load_model(model_path: str):
    """Load model (cached)"""
    device = torch.device('cpu')
    model = torch.load(model_path, map_location=device, weights_only=False)
    model.eval()
    return model


def preprocess_image_from_cv(frame: np.ndarray):
    """Convert OpenCV frame to model input tensor"""
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(img)
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    tensor = transform(pil)[:3, :, :].unsqueeze(0)
    return tensor


def predict_frame(frame: np.ndarray, model):
    """
    Predict label, probability, and bounding box for a given frame.
    Returns: (label, prob, bbox)
    """
    tensor = preprocess_image_from_cv(frame)
    device = next(model.parameters()).device
    tensor = tensor.to(device)

    with torch.no_grad():
        pred = model(tensor)
        idx = torch.argmax(pred, dim=1).item()
        prob = float(torch.softmax(pred, dim=1)[0, idx].item() * 100)

    label = CLASS_NAMES[idx]

    # Detect bright areas for visualization (fire blob)
    bbox = None
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest)
            bbox = (int(x), int(y), int(w), int(h))
    except Exception:
        bbox = None

    return label, prob, bbox


# -----------------------------
# Drawing Functions
# -----------------------------

def draw_bbox_on_frame(frame, bbox, label, prob, color=(0, 0, 255)):
    """Draw bounding box and label on frame"""
    if bbox is None:
        return frame
    x, y, w, h = bbox
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    cv2.putText(
        frame,
        f"{label} {prob:.1f}%",
        (x, max(10, y - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
    )
    return frame


# -----------------------------
# Stream Functions
# -----------------------------

def capture_live_stream(hostname, port, stream_path):
    """
    Capture live video stream from ESP32-CAM using MJPEG.
    Includes robust reconnection logic and error suppression.
    Keeps last valid frame during brief disconnections to prevent blank displays.
    """
    # #region agent log
    try:
        # Use absolute path - find project root by going up from backend/
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(backend_dir)
        log_path = os.path.join(project_root, '.cursor', 'debug.log')
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'a') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A,B,E","location":"stream_utils.py:119","message":"capture_live_stream entry","data":{"hostname":hostname,"port":port},"timestamp":int(time.time()*1000)}) + '\n')
            f.flush()
    except (NotImplementedError, OSError, PermissionError):
        # Expected in multiprocessing contexts - file I/O may not work in worker processes
        # Silently ignore - critical info is already printed to stdout
        pass
    except Exception as e:
        # Only log unexpected errors
        if "Broken pipe" not in str(e) and "NotImplemented" not in str(e):
            print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
    # #endregion
    print(f"[{hostname}] Connecting to ESP32-CAM...")
    
    last_valid_frame = None  # Keep last frame during brief disconnects
    
    # Outer loop for reconnection
    while True:
        cap = None
        reconnect_start = None  # Track when reconnection started
        
        try:
            # Resolve IP - yield frames during DNS resolution
            ip = None
            dns_start = time.time()
            while ip is None:
                try:
                    ip = socket.gethostbyname(hostname)
                    break
                except Exception:
                    # Yield last frame continuously during DNS retries
                    if last_valid_frame is not None:
                        yield last_valid_frame
                    if time.time() - dns_start > 2.0:  # Give up after 2 seconds
                        # Continue to outer loop to retry
                        time.sleep(0.5)
                        break
                    time.sleep(0.1)
            
            if ip is None:
                # DNS failed, retry outer loop
                continue
            
            url = f"http://{ip}:{port}{stream_path}"
            
            # #region agent log
            try:
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(backend_dir)
                log_path = os.path.join(project_root, '.cursor', 'debug.log')
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"stream_utils.py:141","message":"Before VideoCapture","data":{"url":url,"timeout_setting":5000},"timestamp":int(time.time()*1000)}) + '\n')
                    f.flush()
            except Exception as e:
                print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
            # #endregion
            
            # Use FFMPEG backend explicitly with timeout settings
            # Yield frames during VideoCapture initialization
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            # Minimize buffering for low latency
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Set timeouts - note: these may not work on all OpenCV builds
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
            
            # Check if opened - yield frames while waiting
            cap_check_start = time.time()
            while not cap.isOpened():
                if last_valid_frame is not None:
                    yield last_valid_frame
                if time.time() - cap_check_start > 2.0:  # Give up after 2 seconds
                    if cap:
                        cap.release()
                    break
                time.sleep(0.05)
            
            if not cap.isOpened():
                # Yield last frame if available during reconnect
                if last_valid_frame is not None:
                    yield last_valid_frame
                time.sleep(0.5)  # Shorter wait before retry
                continue
            
            print(f"[{hostname}] Stream connected")
            
            consecutive_failures = 0
            consecutive_timeouts = 0  # Track timeouts separately
            max_failures = 15  # Increased to allow for network variability
            max_timeouts = 30  # Allow many timeouts before reconnecting (timeouts are less severe)
            timeout_seconds = 3.5  # Increased from 2.0 to allow slow but valid reads
            
            # Helper function to read frame with timeout
            def read_frame_with_timeout(cap, timeout_sec=3.5):
                """Read frame with timeout using threading since OpenCV timeout settings don't work"""
                result = [None, None]  # [ret, frame]
                exception = [None]
                
                def read_worker():
                    try:
                        result[0], result[1] = cap.read()
                    except Exception as e:
                        exception[0] = e
                
                thread = threading.Thread(target=read_worker, daemon=True)
                thread.start()
                thread.join(timeout=timeout_sec)
                
                if thread.is_alive():
                    # Timeout occurred - cap.read() is blocking too long
                    # Note: This is a timeout, not necessarily a failure
                    return False, None, True  # (ret, frame, is_timeout)
                
                if exception[0]:
                    raise exception[0]
                
                return result[0], result[1], False  # (ret, frame, is_timeout)
            
            # Inner loop for frame reading
            while True:
                try:
                    # #region agent log
                    read_start = time.time()
                    # #endregion
                    # Use timeout wrapper since OpenCV timeout settings don't work
                    ret, frame, is_timeout = read_frame_with_timeout(cap, timeout_sec=timeout_seconds)
                    # #region agent log
                    read_duration = (time.time() - read_start) * 1000
                    # Log to file and also print for visibility
                    log_data = {"sessionId":"debug-session","runId":"run1","hypothesisId":"A,B","location":"stream_utils.py:191","message":"cap.read() result","data":{"hostname":hostname,"ret":bool(ret),"read_duration_ms":round(read_duration,2),"consecutive_failures":consecutive_failures},"timestamp":int(time.time()*1000)}
                    try:
                        backend_dir = os.path.dirname(os.path.abspath(__file__))
                        project_root = os.path.dirname(backend_dir)
                        log_path = os.path.join(project_root, '.cursor', 'debug.log')
                        os.makedirs(os.path.dirname(log_path), exist_ok=True)
                        with open(log_path, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(log_data) + '\n')
                            f.flush()
                        # Also print critical data for immediate visibility
                        if read_duration > 1000:  # Only print if > 1 second (suspicious)
                            print(f"[DEBUG-A] {hostname} cap.read() took {read_duration:.1f}ms, ret={ret}, failures={consecutive_failures}")
                    except Exception as e:
                        print(f"[DEBUG] Log write failed: {type(e).__name__}: {str(e)[:100]}")
                        # Fallback: print critical data
                        if read_duration > 1000:
                            print(f"[DEBUG-A-FALLBACK] {hostname} cap.read() took {read_duration:.1f}ms")
                    # #endregion
                    
                    if not ret:
                        # Handle timeouts vs actual read failures differently
                        if is_timeout:
                            # Timeout - less severe, track separately
                            consecutive_timeouts += 1
                            # Only count timeout as failure if we have many consecutive timeouts
                            if consecutive_timeouts >= 5:
                                consecutive_failures += 1
                        else:
                            # Actual read failure (not timeout) - more serious, count immediately
                            consecutive_failures += 1
                            consecutive_timeouts = 0  # Reset timeout counter on actual failure
                        
                        # #region agent log
                        log_data = {"sessionId":"debug-session","runId":"run1","hypothesisId":"B,E","location":"stream_utils.py:203","message":"cap.read() failed","data":{"hostname":hostname,"consecutive_failures":consecutive_failures,"consecutive_timeouts":consecutive_timeouts,"max_failures":max_failures,"read_duration_ms":round(read_duration,2),"is_timeout":is_timeout},"timestamp":int(time.time()*1000)}
                        try:
                            backend_dir = os.path.dirname(os.path.abspath(__file__))
                            project_root = os.path.dirname(backend_dir)
                            log_path = os.path.join(project_root, '.cursor', 'debug.log')
                            os.makedirs(os.path.dirname(log_path), exist_ok=True)
                            with open(log_path, 'a', encoding='utf-8') as f:
                                f.write(json.dumps(log_data) + '\n')
                                f.flush()
                        except Exception as e:
                            print(f"[DEBUG] Log write failed: {type(e).__name__}: {str(e)[:100]}")
                        timeout_msg = " (TIMEOUT)" if is_timeout else ""
                        print(f"[DEBUG-B] {hostname} cap.read() FAILED{timeout_msg}, duration={read_duration:.1f}ms, failures={consecutive_failures}/{max_failures}, timeouts={consecutive_timeouts}")
                        # #endregion
                        if consecutive_failures > max_failures or consecutive_timeouts > max_timeouts:
                            # Too many failures, trigger reconnect
                            # #region agent log
                            try:
                                backend_dir = os.path.dirname(os.path.abspath(__file__))
                                project_root = os.path.dirname(backend_dir)
                                log_path = os.path.join(project_root, '.cursor', 'debug.log')
                                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                                with open(log_path, 'a') as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B,E","location":"stream_utils.py:170","message":"Triggering reconnect","data":{"hostname":hostname,"consecutive_failures":consecutive_failures},"timestamp":int(time.time()*1000)}) + '\n')
                                    f.flush()
                            except Exception as e:
                                print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
                            # #endregion
                            print(f"[{hostname}] Stream unstable, reconnecting...")
                            # #region agent log
                            try:
                                backend_dir = os.path.dirname(os.path.abspath(__file__))
                                project_root = os.path.dirname(backend_dir)
                                log_path = os.path.join(project_root, '.cursor', 'debug.log')
                                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                                with open(log_path, 'a') as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"stream_utils.py:290","message":"Breaking inner loop for reconnect","data":{"hostname":hostname,"has_last_valid_frame":last_valid_frame is not None},"timestamp":int(time.time()*1000)}) + '\n')
                                    f.flush()
                            except Exception as e:
                                print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
                            # #endregion
                            # Yield last frame before breaking to reconnect
                            if last_valid_frame is not None:
                                yield last_valid_frame
                            break
                        # Yield last valid frame during brief failures
                        if last_valid_frame is not None:
                            yield last_valid_frame
                        time.sleep(0.05)
                        continue
                    
                    # Success - update last valid frame
                    consecutive_failures = 0
                    consecutive_timeouts = 0  # Reset timeout counter on success
                    last_valid_frame = frame.copy()  # Keep copy for fallback
                    # #region agent log
                    try:
                        backend_dir = os.path.dirname(os.path.abspath(__file__))
                        project_root = os.path.dirname(backend_dir)
                        log_path = os.path.join(project_root, '.cursor', 'debug.log')
                        os.makedirs(os.path.dirname(log_path), exist_ok=True)
                        with open(log_path, 'a') as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"stream_utils.py:180","message":"cap.read() success","data":{"hostname":hostname,"read_duration_ms":read_duration},"timestamp":int(time.time()*1000)}) + '\n')
                            f.flush()
                    except Exception as e:
                        print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
                    # #endregion
                    yield frame
                    
                except Exception as e:
                    # Yield last frame on exception if available
                    if last_valid_frame is not None:
                        yield last_valid_frame
                    break
                    
        except Exception as e:
            print(f"[{hostname}] Connection error: {e}")
            # Yield last frame during connection errors
            if last_valid_frame is not None:
                yield last_valid_frame
        
        finally:
            if cap:
                cap.release()
        
        # #region agent log
        try:
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(backend_dir)
            log_path = os.path.join(project_root, '.cursor', 'debug.log')
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, 'a') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"stream_utils.py:328","message":"Reconnection gap - before sleep","data":{"hostname":hostname,"has_last_valid_frame":last_valid_frame is not None},"timestamp":int(time.time()*1000)}) + '\n')
                f.flush()
        except Exception as e:
            print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
        # #endregion
        
        # Wait before reconnecting (shorter wait for faster recovery)
        # During this time, yield last_valid_frame continuously to prevent NO SIGNAL
        reconnect_wait_start = time.time()
        while time.time() - reconnect_wait_start < 0.5:
            if last_valid_frame is not None:
                yield last_valid_frame
            time.sleep(0.05)  # Yield frames frequently during reconnect wait


def process_and_display_frame(frame, model, frame_count, window_name, camera_name):
    """
    Run model inference on a frame and display the output with predictions.
    
    Args:
        frame (numpy.ndarray): Video frame to process
        model: Loaded PyTorch model for inference
        frame_count (int): Current frame number
        window_name (str): Name of the OpenCV window
        camera_name (str): Name of the camera (for logging)
    
    Returns:
        bool: True if 'q' key was pressed (to stop), False otherwise
    """
    # Run model inference on frame
    try:
        label, prob, bbox = predict_frame(frame, model)
        
        # Print prediction results (less frequent)
        if frame_count % 30 == 0:
            print(f"[{camera_name}] Frame {frame_count}: {label} ({prob:.1f}%)")
        
        # Draw bounding box and label on frame
        if bbox is not None:
            # Choose color based on label
            if label == "Fire":
                color = (0, 0, 255)  # Red for fire
            elif label == "Smoke":
                color = (0, 165, 255)  # Orange for smoke
            else:
                color = (0, 255, 0)  # Green for neutral
            
            frame = draw_bbox_on_frame(frame, bbox, label, prob, color)
        
        # Add text overlay with prediction at top-left corner
        text = f"{label}: {prob:.1f}%"
        cv2.putText(
            frame,
            text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0) if label == "Neutral" else (0, 0, 255),
            2,
        )
        
    except Exception as e:
        print(f"[{camera_name}] WARN: Inference error on frame {frame_count}: {e}")
    
    cv2.imshow(window_name, frame)
    
    # Check for quit key (only for this specific window)
    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        print(f"[{camera_name}] Quit key pressed")
        return True
    
    return False


def get_model_path():
    """Get the default model path relative to project root"""
    project_root = os.path.join(os.path.dirname(__file__), '..')
    model_path = os.path.join(project_root, "Model", "trained_model.pth")
    return os.path.abspath(model_path)
