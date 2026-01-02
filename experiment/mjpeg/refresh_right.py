# Live video (MJPEG)
# uses mpeg motion jpeg

import cv2
import socket
import time

print("[INFO] Starting ESP32-CAM MJPEG client")

# Resolve mDNS ONCE (important for performance)
hostname = "firecamright.local"
PORT = 83
print(f"[INFO] Resolving hostname: {hostname}")

try:
    ip = socket.gethostbyname(hostname)
    print(f"[INFO] Resolved IP address: {ip}")
except socket.gaierror as e:
    print(f"[ERROR] Failed to resolve hostname: {e}")
    exit()

url = f"http://{ip}:{PORT}/right/stream"
print(f"[INFO] Stream URL: {url}")

print("[INFO] Opening video stream...")
cap = cv2.VideoCapture(url)

if not cap.isOpened():
    print("[ERROR] Failed to open stream")
    exit()

print("[INFO] Stream opened successfully")

frame_count = 0

while True:
    ret, frame = cap.read()

    if not ret:
        print("[WARN] Failed to read frame, retrying...")
        time.sleep(0.01)
        continue

    frame_count += 1

    # Print OpenCV frame position (as requested)
    print(f"[DEBUG] CAP_PROP_POS_FRAMES = {cap.get(cv2.CAP_PROP_POS_FRAMES)}")

    cv2.imshow("RIGHT ESP32 MJPEG Stream", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("[INFO] Quit key pressed, exiting...")
        break

cap.release()
cv2.destroyAllWindows()

print("[INFO] Stream closed cleanly")
