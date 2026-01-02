# Single Frame

import cv2
import requests
import numpy as np
import socket

# Resolve mDNS once
ip = socket.gethostbyname("firecam.local")
print("ESP32 IP:", ip)

url = f"http://{ip}/right/cam-lo.jpg"

while True:
    try:
        response = requests.get(url, timeout=1)
        img_array = np.frombuffer(response.content, np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if frame is not None:
            cv2.imshow("Camera Stream", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    except Exception as e:
        print("Error:", e)

cv2.destroyAllWindows()
