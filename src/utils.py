import numpy as np
import urllib.request
import cv2



def fetch_frame_from_url(url: str, timeout: int = 5):
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        data = resp.read()
        imgnp = np.asarray(bytearray(data), dtype=np.uint8)
        frame = cv2.imdecode(imgnp, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        # print(f"[WARN] fetch_frame error: {e}")
        return None



def draw_bbox_on_frame(frame, bbox, label, prob, color=(0, 0, 255)):
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