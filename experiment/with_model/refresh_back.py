# Live video (MJPEG)
# uses mpeg motion jpeg
'''
FUNCTION FLOW:
--------------------------------
Main Entry Point:
    stream_live_with_model()
        ↓
    1. Loads the trained PyTorch model using load_model()
        ↓
    2. Starts capturing frames from ESP32-CAM using capture_live_stream()
           (Generator function that yields frames continuously)
        ↓
    3. For each captured frame:
           ↓
           display_with_predictions()
               ↓
           a. Runs inference using predict_frame()
                  ↓
               - preprocess_image_from_cv(): Converts OpenCV frame to model input tensor
                  ↓
               - Model inference: Gets label (Fire/Neutral/Smoke), probability, and bounding box
                  ↓
           b. Draws results on frame using draw_bbox_on_frame()
           c. Displays annotated frame with predictions
           d. Checks for 'q' key press to quit
        ↓
    4. Continues loop until 'q' is pressed or stream ends

Function Dependencies:
    - load_model(): Loads and caches the PyTorch model
    - capture_live_stream(): Generator that yields video frames from ESP32-CAM
    - display_with_predictions(): Processes frame, runs inference, and displays results
    - predict_frame(): Core inference function that calls preprocess_image_from_cv()
    - preprocess_image_from_cv(): Converts OpenCV BGR frame to normalized tensor
    - draw_bbox_on_frame(): Draws bounding boxes and labels on the frame
'''

import cv2
import socket
import time
import os
import torch
from torchvision import transforms
from PIL import Image
import functools
import numpy as np

# -----------------------------
# Constants
# -----------------------------
CLASS_NAMES = ['Fire', 'Neutral', 'Smoke']


# -----------------------------

# -----------------------------

@functools.lru_cache(maxsize=1)
def load_model(model_path: str):
    """Load model (cached)"""
    device = torch.device('cpu')
    # Load your model (ensure it's a torch model)
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
# Utility Functions (from src/utils.py)
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


def capture_live_stream(hostname="firecamback.local", port=81, stream_path="/back/stream"):
    """
    Capture live video stream from ESP32-CAM using MJPEG.
    This is a generator function that yields frames.
    
    Args:
        hostname (str): Hostname or IP address of the ESP32-CAM
        port (int): Port number for the stream
        stream_path (str): Path to the stream endpoint
    
    Yields:
        numpy.ndarray: Video frames from the stream
    
    Returns:
        cv2.VideoCapture: The video capture object (for cleanup)
    """
    print("[INFO] Starting ESP32-CAM MJPEG client")
    
    # Resolve mDNS ONCE (important for performance)
    print(f"[INFO] Resolving hostname: {hostname}")
    
    try:
        ip = socket.gethostbyname(hostname)
        print(f"[INFO] Resolved IP address: {ip}")
    except socket.gaierror as e:
        print(f"[ERROR] Failed to resolve hostname: {e}")
        return None
    
    url = f"http://{ip}:{port}{stream_path}"
    print(f"[INFO] Stream URL: {url}")
    
    print("[INFO] Opening video stream...")
    cap = cv2.VideoCapture(url)
    
    if not cap.isOpened():
        print("[ERROR] Failed to open stream")
        return None
    
    print("[INFO] Stream opened successfully")
    
    try:
        while True:
            ret, frame = cap.read()
            
            if not ret:
                print("[WARN] Failed to read frame, retrying...")
                time.sleep(0.01)
                continue
            
            yield frame
    finally:
        cap.release()
        print("[INFO] Stream closed cleanly")


def display_with_predictions(frame, model, frame_count, window_name="BACK ESP32 MJPEG Stream - Fire Detection"):
    """
    Run model inference on a frame and display the output with predictions.
    
    Args:
        frame (numpy.ndarray): Video frame to process
        model: Loaded PyTorch model for inference
        frame_count (int): Current frame number (for logging)
        window_name (str): Name of the OpenCV window
    
    Returns:
        bool: True if 'q' key was pressed (to stop), False otherwise
    """
    # Run model inference on frame
    try:
        label, prob, bbox = predict_frame(frame, model)
        
        # Print prediction results
        if frame_count % 30 == 0:  # Print every 30 frames to reduce console spam
            print(f"[INFO] Frame {frame_count}: {label} ({prob:.1f}%)")
        
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
        print(f"[WARN] Inference error on frame {frame_count}: {e}")
    
    cv2.imshow(window_name, frame)
    
    # Check for quit key
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("[INFO] Quit key pressed, exiting...")
        return True
    
    return False


def stream_live_with_model(
    model_path=None,
    hostname="firecamback.local",
    port=81,
    stream_path="/back/stream",
    window_name="BACK ESP32 MJPEG Stream - Fire Detection"
):
    """
    Stream live video from ESP32-CAM using MJPEG and run fire detection model inference.
    This function combines capture_live_stream() and display_with_predictions().
    
    Args:
        model_path (str): Path to the trained model file (default: Model/trained_model.pth relative to project root)
        hostname (str): Hostname or IP address of the ESP32-CAM
        port (int): Port number for the stream
        stream_path (str): Path to the stream endpoint
        window_name (str): Name of the OpenCV window
    
    Returns:
        None
    """
    print("[INFO] Starting ESP32-CAM MJPEG client with Fire Detection Model")
    
    # Set default model path relative to project root
    if model_path is None:
        # Get project root (two levels up from this file)
        project_root = os.path.join(os.path.dirname(__file__), '../..')
        model_path = os.path.join(project_root, "Model", "trained_model.pth")
        model_path = os.path.abspath(model_path)
    
    # Load model
    print(f"[INFO] Loading model from: {model_path}")
    try:
        model = load_model(model_path)
        print("[INFO] Model loaded successfully")
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}")
        return
    
    frame_count = 0
    
    try:
        # Capture frames from live stream
        for frame in capture_live_stream(hostname, port, stream_path):
            frame_count += 1
            
            # Display frame with predictions
            should_quit = display_with_predictions(frame, model, frame_count, window_name)
            
            if should_quit:
                break
    finally:
        cv2.destroyAllWindows()
        print("[INFO] Display closed cleanly")


if __name__ == "__main__":
    # Uncomment the function you want to use:
    # stream_live()  # Basic streaming without model
    stream_live_with_model()  # Streaming with fire detection model
