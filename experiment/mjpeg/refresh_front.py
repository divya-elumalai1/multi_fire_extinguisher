import cv2
import socket
import threading
import requests
import time

# ================= CONFIG =================
HOSTNAME = "firecamfront.local"
STREAM_PATH = "/front/stream"
MOTOR_PATH = "/front/motor"

# ================= RESOLVE mDNS =================
ip = socket.gethostbyname(HOSTNAME)
stream_url = f"http://{ip}{STREAM_PATH}"
motor_url = f"http://{ip}{MOTOR_PATH}"

# ================= MOTOR =================
def send_cmd(cmd):
    try:
        r = requests.get(motor_url, params={"cmd": cmd}, timeout=0.3)
        print("ESP32:", r.text)
    except requests.exceptions.RequestException:
        print("⚠️ ESP32 not reachable")

# ================= INPUT THREAD =================
def motor_input_loop(stop_event):
    while not stop_event.is_set():
        cmd = input("Command (F/B/L/R/S, q=quit): ").strip()
        if not cmd:
            continue

        if cmd.lower() == 'q':
            send_cmd('S')
            stop_event.set()
            break

        send_cmd(cmd[0])

# ================= MAIN =================
if __name__ == "__main__":
    stop_event = threading.Event()

    threading.Thread(
        target=motor_input_loop,
        args=(stop_event,),
        daemon=True
    ).start()

    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print("❌ Failed to open stream")
        exit(1)

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        cv2.imshow("FRONT ESP32 MJPEG Stream", frame)

        if cv2.waitKey(1) & 0xFF == 27:  # ESC
            stop_event.set()
            break

    cap.release()
    cv2.destroyAllWindows()