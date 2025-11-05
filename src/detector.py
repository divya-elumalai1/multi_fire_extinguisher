import torch
from torchvision import transforms
from PIL import Image
import functools
import numpy as np
import cv2

# -----------------------------
# Constants
# -----------------------------
CLASS_NAMES = ['Fire', 'Neutral', 'Smoke']


# -----------------------------
# Load model (cached)
# -----------------------------
@functools.lru_cache(maxsize=1)
def load_model(model_path: str):
    device = torch.device('cpu')
    # Load your model (ensure it's a torch model)
    model = torch.load(model_path, map_location=device, weights_only=False)
    model.eval()
    return model


# -----------------------------
# Preprocess image
# -----------------------------
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


# -----------------------------
# Predict function
# -----------------------------
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