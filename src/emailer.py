import yagmail
import time
import cv2


class Emailer:
    def __init__(self, sender: str, app_pass: str, receiver: str):
        try:
            self.client = yagmail.SMTP(sender, app_pass)
        except Exception as e:
            self.client = None
            print(f"[WARN] Could not initialize yagmail: {e}")
        self.receiver = receiver

    def send_alert(self, subject: str, html_message: str, frame):
        if not self.client:
            print('[WARN] Email client not available')
            return False
        img_path = f"alert_{int(time.time())}.jpg"
        cv2.imwrite(img_path, frame)
        try:
            self.client.send(self.receiver, subject, html_message, [img_path])
            print('[INFO] Alert email sent')
            return True
        except Exception as e:
            print(f"[WARN] Email send failed: {e}")
            return False