import os
import cv2
import torch
from torchvision.transforms import transforms
import numpy as np
from PIL import Image
import urllib.request
import time  # ✅ Add this

# Load the pre-trained model
print("[INFO] loading model...")
model = torch.load(
    '/Users/divya/Documents/Arduino/Fire_fighting_robot/Fire_detect_ml/Model/trained_model.pth',
    map_location=torch.device('cpu'),
    weights_only=False
)
class_names = ['Fire', 'Neutral', 'Smoke']

# Prediction function
def predict(image):
    prediction_transform = transforms.Compose([
        transforms.Resize(size=(224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    image = prediction_transform(image)[:3, :, :].unsqueeze(0)
    image = image.to(torch.device('cpu'))

    pred = model(image)
    idx = torch.argmax(pred)
    prob = pred[0][idx].item() * 100

    return class_names[idx], prob


# Replace the URL with the ESP32-CAM endpoint
url = 'http://192.168.0.11/cam-mid.jpg'

print("[INFO] Starting IP camera stream...")
frame_delay = 0.2  # ✅ Adjust delay here (seconds) — 0.1–0.3 is ideal

while True:
    try:
        # Read a frame from the IP camera
        img_resp = urllib.request.urlopen(url, timeout=5)
        imgnp = np.array(bytearray(img_resp.read()), dtype=np.uint8)
        frame = cv2.imdecode(imgnp, -1)

        if frame is None:
            print("[WARN] Empty frame, skipping...")
            time.sleep(frame_delay)
            continue

        # Convert frame for prediction
        draw = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        draw = Image.fromarray(draw)

        # Predict the class and probability
        prediction, prob = predict(draw)

        # Set color based on prediction
        color = (0, 255, 0) if prediction == 'Neutral' else (0, 0, 255)

        # Display prediction
        cv2.putText(frame, f'{prediction} {prob:.2f}%', (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.imshow('Fire Detection - IP Camera', frame)

        # ✅ Delay here — gives ESP32 time to capture next frame
        time.sleep(frame_delay)

        # Break on 'q' key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except Exception as e:
        print(f"[WARN] {e}")
        time.sleep(0.5)  # wait briefly before retrying
        continue

# Release resources
cv2.destroyAllWindows()