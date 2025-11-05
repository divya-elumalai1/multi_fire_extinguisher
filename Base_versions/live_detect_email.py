import os
import cv2
import torch
from torchvision.transforms import transforms
import numpy as np
from PIL import Image
import urllib.request
import yagmail
import time
import random

MODEL_PATH = '/Users/divya/Documents/Arduino/Fire_fighting_robot/Fire_detect_ml/Model/trained_model.pth'
CAM_URL = 'http://esp32cam.local/front/cam-mid.jpg'  # Update with your ESP32-CAM IP

EMAIL_SENDER = "multifireextinguisher@gmail.com"
EMAIL_APP_PASS = "kusw ujez lwkm vtud".replace(" ", "")
EMAIL_RECEIVER = "receiver_email@gmail.com"

EMAIL_INTERVAL = 60  # seconds between alerts
PROB_THRESHOLD = 85  # minimum % confidence to trigger email
FRAME_DELAY = 0.2    # seconds between frames (stability delay)


print("[INFO] Loading model...")
model = torch.load(MODEL_PATH, map_location=torch.device('cpu'), weights_only=False)
class_names = ['Fire', 'Neutral', 'Smoke']


try:
    yag = yagmail.SMTP(EMAIL_SENDER, EMAIL_APP_PASS)
    print("[INFO] Email service connected.")
except Exception as e:
    yag = None
    print(f"[WARN] Email setup failed: {e}")


def predict(image):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225])
    ])
    image = transform(image)[:3, :, :].unsqueeze(0)
    image = image.to(torch.device('cpu'))
    with torch.no_grad():
        pred = model(image)
        idx = torch.argmax(pred)
        prob = pred[0][idx].item() * 100
    return class_names[idx], prob


def send_alert_email(prediction, prob, frame):
    if not yag:
        print("[WARN] Email service not available.")
        return

    subject = f"🔥 ALERT: {prediction} Detected!"
    message = f"""
    <div style="font-family: Arial, sans-serif; padding: 15px; border-radius: 10px; background-color:#f8d7da;">
        <h2 style="color:#721c24;">⚠️ Alert: {prediction} Detected</h2>
        <p><b>Probability:</b> {prob:.2f}%</p>
        <p>Time: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    """

    # Save frame locally before sending
    alert_image_path = "alert_image.jpg"
    cv2.imwrite(alert_image_path, frame)

    try:
        yag.send(EMAIL_RECEIVER, subject, message, [alert_image_path])
        print(f"[INFO] Email sent successfully ({prediction}, {prob:.1f}%).")
    except Exception as e:
        print(f"[WARN] Email failed: {e}")


print("[INFO] Starting IP camera stream...")
last_sent_time = 0

while True:
    try:
        # ---- Capture frame ----
        img_resp = urllib.request.urlopen(CAM_URL, timeout=5)
        imgnp = np.asarray(bytearray(img_resp.read()), dtype=np.uint8)
        frame = cv2.imdecode(imgnp, -1)

        if frame is None:
            print("[WARN] Empty frame, skipping...")
            time.sleep(FRAME_DELAY)
            continue

        # ---- Prediction ----
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        prediction, prob = predict(pil_img)

        # ---- Overlay results ----
        color = (0, 255, 0) if prediction == 'Neutral' else (0, 0, 255)
        cv2.putText(frame, f"{prediction} {prob:.2f}%",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        # ---- Fire / Smoke alert logic ----
        if prediction in ['Fire', 'Smoke'] and prob > PROB_THRESHOLD:
            if (time.time() - last_sent_time) > EMAIL_INTERVAL:

                # Detect bright area for bounding box
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest = max(contours, key=cv2.contourArea)
                    x, y, w, h = cv2.boundingRect(largest)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

                send_alert_email(prediction, prob, frame)
                last_sent_time = time.time()

        # ---- Display ----
        cv2.imshow("Fire Detection - IP Camera", frame)
        time.sleep(FRAME_DELAY)

        # ---- Quit ----
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("[INFO] Quitting...")
            break

    except urllib.error.URLError:
        print("[WARN] Connection lost. Retrying...")
        time.sleep(1)
        continue
    except Exception as e:
        print(f"[ERROR] {e}")
        time.sleep(1)
        continue

cv2.destroyAllWindows()