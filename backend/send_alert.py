import yagmail
import time
import csv
import os
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Paths
CONFIG_PATH = Path(__file__).parent / "config.yaml"
EVENTS_CSV = Path(__file__).parent.parent / "data" / "events.csv"
SNAPS_DIR = Path(__file__).parent.parent / "data" / "snaps"

# Track last email time to enforce interval
last_email_time = 0

# Config caching to avoid reloading on every call
_cached_config = None
_config_load_time = 0
_CONFIG_CACHE_TTL = 30  # Reload config every 30 seconds instead of every call


def load_email_config(force_reload=False):
    """Load email configuration from config.yaml with fallback defaults
    Uses caching to avoid reloading on every call (reloads every 30 seconds)
    """
    global _cached_config, _config_load_time
    
    current_time = time.time()
    
    # Return cached config if still valid and not forcing reload
    if not force_reload and _cached_config is not None:
        if current_time - _config_load_time < _CONFIG_CACHE_TTL:
            return _cached_config
    
    default_config = {
        "enable": True,
        "sender": "multifireextinguisher@gmail.com",
        "app_pass": "kusw ujez lwkm vtud",
        "receiver": ["divya.eindu@gmail.com", "gaganashreedg@gmail.com", "saagarikasaag@gmail.com", "shreya.satish.2004@gmail.com"],
        "interval": 60,
        "alert_types": ["smoke", "fire"]
    }
    
    if not CONFIG_PATH.exists():
        print(f"[CONFIG] Config file not found at {CONFIG_PATH}, using defaults")
        _cached_config = default_config
        _config_load_time = current_time
        return default_config
    
    try:
        with open(CONFIG_PATH, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        email_config = config.get("email", {})
        
        # Merge with defaults
        result = default_config.copy()
        result.update(email_config)
        
        # Only print when actually reloading (not from cache)
        if force_reload or _cached_config is None:
            print(f"[CONFIG] Loaded email configuration from {CONFIG_PATH}")
        
        # Update cache
        _cached_config = result
        _config_load_time = current_time
        return result
    except Exception as e:
        print(f"[CONFIG] Error loading email config from {CONFIG_PATH}: {e}")
        print(f"[CONFIG] Using default configuration")
        _cached_config = default_config
        _config_load_time = current_time
        return default_config


# Load configuration initially
_email_config = load_email_config()

# Configuration variables (loaded from config.yaml)
send_alert = _email_config.get("alert_types", ["smoke", "fire"])
receiver_email = _email_config.get("receiver", ["dinesh.graph@gmail.com", "dineshdinu.elu@gmail.com"])
sender_email = _email_config.get("sender", "multifireextinguisher@gmail.com")
app_pass = _email_config.get("app_pass", "kusw ujez lwkm vtud")
email_enable = _email_config.get("enable", True)
email_interval = _email_config.get("interval", 60)



class Emailer:
    def __init__(self, sender: str, app_pass: str, receivers: List[str]):
        self.receivers = receivers
        try:
            self.client = yagmail.SMTP(sender, app_pass)
            print('[INFO] Email client initialized successfully')
        except Exception as e:
            self.client = None
            print(f"[WARN] Could not initialize yagmail: {e}")

    def send_alert_email(self, subject: str, html_message: str, image_paths: List[str]):
        """Send email alert with multiple image attachments"""
        if not self.client:
            print('[WARN] Email client not available')
            return False
        
        if not image_paths:
            print('[WARN] No images to attach')
            return False
        
        try:
            # Send to all receivers
            for receiver in self.receivers:
                self.client.send(
                    to=receiver,
                    subject=subject,
                    contents=html_message,
                    attachments=image_paths
                )
            print(f'[INFO] Alert email sent to {len(self.receivers)} recipient(s)')
            return True
        except Exception as e:
            print(f"[WARN] Email send failed: {e}")
            return False


def read_latest_events(n: int = 4) -> List[Dict[str, str]]:
    """Read the latest n records from events.csv"""
    if not EVENTS_CSV.exists():
        print(f"[WARN] Events file not found: {EVENTS_CSV}")
        return []
    
    events = []
    try:
        with open(EVENTS_CSV, 'r') as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)
            # Get last n records
            events = all_rows[-n:] if len(all_rows) >= n else all_rows
    except Exception as e:
        print(f"[ERROR] Failed to read events.csv: {e}")
    
    return events


def check_for_alerts(events: List[Dict[str, str]]) -> Dict[str, str]:
    """Check events for smoke/fire and return detected cameras with their events"""
    alerts = {}
    
    for event in events:
        camera = event.get('camera', '').strip().lower()
        event_type = event.get('event', '').strip().lower()
        
        if event_type in send_alert:
            alerts[camera] = event_type
    
    return alerts


def get_image_paths(alerts: Dict[str, str]) -> List[str]:
    """Get image paths for cameras with alerts"""
    image_paths = []
    
    for camera in alerts.keys():
        img_path = SNAPS_DIR / f"{camera}.jpeg"
        if img_path.exists():
            image_paths.append(str(img_path))
        else:
            print(f"[WARN] Image not found: {img_path}")
    
    return image_paths


def create_email_message(alerts: Dict[str, str]) -> Tuple[str, str]:
    """Create email subject and HTML message"""
    cameras = list(alerts.keys())
    events = [alerts[cam] for cam in cameras]
    
    # Create subject
    event_types = set(events)
    if len(event_types) == 1:
        subject = f"Fire Alert: {events[0].upper()} detected"
    else:
        subject = f"Fire Alert: {', '.join(event_types).upper()} detected"
    
    # Create HTML message with detailed camera information
    locations = ", ".join([cam.upper() for cam in cameras])
    alert_details = "<ul>"
    for camera, event_type in alerts.items():
        alert_details += f"<li><strong>{camera.upper()}</strong>: {event_type.upper()}</li>"
    alert_details += "</ul>"
    
    html_message = f"""
    <html>
    <body>
        <h2>🚨 Fire Detection Alert</h2>
        <p><strong>Alert Type:</strong> {', '.join([e.upper() for e in event_types])}</p>
        <p><strong>Location(s):</strong> {locations}</p>
        <p><strong>Detections:</strong></p>
        {alert_details}
        <p><strong>Timestamp:</strong> {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        <hr>
        <p>Please review the attached images from the cameras where the alert was detected.</p>
    </body>
    </html>
    """
    
    return subject, html_message


def check_and_send_alert():
    """Main function to check events and send alert if needed"""
    global last_email_time
    
    # Load configuration (cached, reloads every 30 seconds)
    config = load_email_config()
    email_enable = config.get("enable", True)
    email_interval = config.get("interval", 60)
    alert_types = config.get("alert_types", ["smoke", "fire"])
    receiver_email = config.get("receiver", [])
    sender_email = config.get("sender", "")
    app_pass = config.get("app_pass", "")
    
    if not email_enable:
        # Silently return if email is disabled (no need to log every time)
        return False
    
    # Check interval
    current_time = time.time()
    if current_time - last_email_time < email_interval:
        time_remaining = email_interval - (current_time - last_email_time)
        print(f"[INFO] Email interval not reached. Wait {time_remaining:.1f} more seconds")
        return False
    
    # Read latest 4 events
    events = read_latest_events(4)
    if not events:
        print("[INFO] No events found")
        return False
    
    # Check for alerts using reloaded alert_types
    alerts = {}
    for event in events:
        camera = event.get('camera', '').strip().lower()
        event_type = event.get('event', '').strip().lower()
        if event_type in alert_types:
            alerts[camera] = event_type
            
    if not alerts:
        print("[INFO] No smoke/fire detected in latest events")
        return False
    
    # Get image paths
    image_paths = get_image_paths(alerts)
    if not image_paths:
        print("[WARN] No images found for alert cameras")
        return False
    
    # Create email
    subject, html_message = create_email_message(alerts)
    
    # Initialize emailer and send using reloaded credentials
    emailer = Emailer(sender_email, app_pass, receiver_email)
    success = emailer.send_alert_email(subject, html_message, image_paths)
    
    if success:
        last_email_time = current_time
        print(f"[INFO] Alert email sent successfully for: {', '.join(alerts.keys())}")
    
    return success


if __name__ == "__main__":
    # Test the function
    check_and_send_alert()
