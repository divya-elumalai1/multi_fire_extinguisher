"""
File handling utilities for logging fire and smoke detection events.
Maintains a CSV file with a maximum of 1,200 records.

Keeps update of the latest jpeg in the snaps folder
"""

import os
import csv
from datetime import datetime
from typing import Optional, List, Tuple, Dict
import threading
import time
import cv2
import numpy as np

# Import annotation function from stream_utils
try:
    from stream_utils import draw_bbox_on_frame
except ImportError:
    # Fallback if import fails
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

# Thread lock for CSV operations
_csv_lock = threading.Lock()

def load_file_handling_config():
    """Load file handling configuration from config.yaml with fallback defaults"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    
    # Default configuration
    default_config = {
        "max_records": 1200,
        "csv_header": ['datetime', 'camera', 'event', 'confidence_level'],
        "record_update": 5
    }
    
    # Try to load from YAML file
    if os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f) or {}
            
            # Get file_handling section if it exists
            if "file_handling" in yaml_config:
                file_config = yaml_config["file_handling"]
                # Merge with defaults (YAML takes precedence)
                default_config.update(file_config)
            
            return default_config
        except Exception as e:
            print(f"[FILE_HANDLING] Error loading config from {config_path}: {e}")
            print(f"[FILE_HANDLING] Using default configuration")
    
    return default_config

# Load configuration
_file_handling_config = load_file_handling_config()

# Maximum number of records to keep in CSV
MAX_RECORDS = _file_handling_config.get("max_records", 1200)
CSV_HEADER = _file_handling_config.get("csv_header", ['datetime', 'camera', 'event', 'confidence_level'])
Record_update = _file_handling_config.get("record_update", 5)  # update the events at every N seconds

# Camera status tracking - stores current status for each camera
# Format: {camera_name: (event, confidence, timestamp)}
_camera_status: Dict[str, Tuple[str, float, float]] = {}
_status_lock = threading.Lock()
_flush_thread: Optional[threading.Thread] = None
_last_flush_time = 0  # Track last flush time as backup

# Latest frames and detection results for each camera - stores the most recent frame and results for snapshot saving
# Format: {camera_name: (frame_array, label, prob, bbox)}
_camera_frames: Dict[str, Tuple[np.ndarray, str, float, Optional[Tuple[int, int, int, int]]]] = {}
_frame_lock = threading.Lock()

# List of all cameras (default 4 cameras)
CAMERA_NAMES = ['front', 'back', 'left', 'right']

# CSV file path (relative to project root)
def get_data_dir():
    """Get the data directory path (project root/data)"""
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(backend_dir)
    data_dir = os.path.join(project_root, "data")
    return data_dir

def get_csv_path():
    """Get the full path to events.csv"""
    data_dir = get_data_dir()
    return os.path.join(data_dir, "events.csv")

def get_snaps_dir():
    """Get the snaps directory path (project root/data/snaps)"""
    data_dir = get_data_dir()
    snaps_dir = os.path.join(data_dir, "snaps")
    return snaps_dir

def ensure_snaps_folder():
    """Create snaps folder if it doesn't exist"""
    snaps_dir = get_snaps_dir()
    if not os.path.exists(snaps_dir):
        os.makedirs(snaps_dir, exist_ok=True)
    return snaps_dir

def ensure_data_folder():
    """Create data folder if it doesn't exist"""
    data_dir = get_data_dir()
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    return data_dir

def ensure_csv_file():
    """Create events.csv with headers if it doesn't exist or is empty"""
    csv_path = get_csv_path()
    ensure_data_folder()
    
    # Check if file exists and has content
    needs_header = False
    if not os.path.exists(csv_path):
        needs_header = True
    else:
        # Check if file is empty or doesn't have proper header
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                # Check if first line is the header
                expected_header = ','.join(CSV_HEADER)
                if not first_line or first_line != expected_header:
                    needs_header = True
        except Exception:
            needs_header = True
    
    if needs_header:
        # Read existing records if any
        existing_records = []
        if os.path.exists(csv_path):
            try:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    # Skip header if it exists but is wrong
                    first_row = next(reader, None)
                    if first_row and first_row != CSV_HEADER:
                        # First row is data, not header
                        existing_records.append(first_row)
                    # Read remaining records
                    existing_records.extend(list(reader))
            except Exception:
                pass
        
        # Write file with header and existing records
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)
            writer.writerows(existing_records)
    
    return csv_path

def get_record_count():
    """Get the current number of records in the CSV (excluding header)"""
    csv_path = get_csv_path()
    if not os.path.exists(csv_path):
        return 0
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            # Skip header
            next(reader, None)
            # Count records
            count = sum(1 for _ in reader)
        return count
    except Exception as e:
        print(f"[FILE_HANDLING] Error counting records: {e}")
        return 0

def trim_old_records():
    """Remove oldest records if CSV exceeds MAX_RECORDS"""
    csv_path = get_csv_path()
    if not os.path.exists(csv_path):
        return
    
    try:
        # Read all records
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Read header
            records = list(reader)
        
        # If we have more than MAX_RECORDS, keep only the most recent ones
        if len(records) > MAX_RECORDS:
            # Keep the most recent MAX_RECORDS records
            records = records[-MAX_RECORDS:]
            
            # Write back to file
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(records)
    except Exception as e:
        print(f"[FILE_HANDLING] Error trimming records: {e}")

def _flush_events_to_csv():
    """Write all 4 cameras' current status to CSV file (called every 5 seconds)
    Only writes if there are actual status updates from the model (streams are active)"""
    global _camera_status, _last_flush_time
    
    current_time = time.time()
    current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    events_to_write = []
    recent_update_threshold = 10.0  # Only write if camera was updated within last 10 seconds
    
    with _status_lock:
        # Only write cameras that have been updated recently (streams are active)
        cameras_with_recent_updates = []
        for camera in CAMERA_NAMES:
            if camera in _camera_status:
                event, confidence, timestamp = _camera_status[camera]
                time_since_update = current_time - timestamp
                # Only include if updated recently (within threshold)
                if time_since_update <= recent_update_threshold:
                    events_to_write.append((current_datetime, camera, event, confidence))
                    cameras_with_recent_updates.append(camera)
    
    # Only write if we have at least one camera with recent updates (streams are active)
    # This ensures we don't write when no streams are running
    if not cameras_with_recent_updates:
        return  # No active streams, don't write anything
    
    # Fill in remaining cameras with neutral status (for cameras not updated recently)
    cameras_written = [cam for _, cam, _, _ in events_to_write]
    for camera in CAMERA_NAMES:
        if camera not in cameras_written:
            # Add neutral for cameras that haven't been updated recently
            events_to_write.append((current_datetime, camera, 'neutral', 0.0))
    
    try:
        with _csv_lock:
            # Ensure CSV file exists
            csv_path = ensure_csv_file()
            
            # Append all 4 camera statuses (active ones with real status, inactive as neutral)
            with open(csv_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for datetime_str, camera, event, confidence in events_to_write:
                    writer.writerow([datetime_str, camera, event, f"{confidence:.1f}"])
                f.flush()  # Force write to disk
                os.fsync(f.fileno())  # Ensure data is written to disk
            
            # Trim old records if necessary
            trim_old_records()
            
            # Update last flush time
            _last_flush_time = time.time()
            
            # Save frames as JPEG snapshots
            _save_frame_snapshots()
            
            print(f"[FILE_HANDLING] Updated events.csv ({len(cameras_with_recent_updates)} active cameras)")
            
    except Exception as e:
        import traceback
        print(f"[FILE_HANDLING] Error flushing events to CSV: {e}")
        print(f"[FILE_HANDLING] Traceback: {traceback.format_exc()}")

def _periodic_flush_worker():
    """Background thread that periodically flushes events to CSV"""
    while True:
        try:
            time.sleep(Record_update)
            _flush_events_to_csv()
        except Exception as e:
            print(f"[FILE_HANDLING] Error in flush worker thread: {e}")
            time.sleep(1)  # Wait before retrying

def _start_flush_thread():
    """Start the background thread for periodic CSV updates"""
    global _flush_thread
    
    try:
        if _flush_thread is None or not _flush_thread.is_alive():
            _flush_thread = threading.Thread(target=_periodic_flush_worker, daemon=True)
            _flush_thread.start()
            # Give it a moment to start
            time.sleep(0.1)
    except Exception as e:
        print(f"[FILE_HANDLING] Error starting flush thread: {e}")

def update_camera_status(camera: str, event: str, confidence_level: float, frame: Optional[np.ndarray] = None):
    """
    Update the current status of a camera (called whenever detection happens)
    
    Args:
        camera: Camera name (e.g., 'front', 'back', 'left', 'right')
        event: Event type ('fire', 'smoke', or 'neutral')
        confidence_level: Confidence level as a percentage (0-100)
        frame: Optional frame array to save as snapshot
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Ensure flush thread is running
    global _flush_thread
    if _flush_thread is None or not _flush_thread.is_alive():
        _start_flush_thread()
    
    # Validate event type (now includes neutral)
    event_lower = event.lower()
    if event_lower not in ['fire', 'smoke', 'neutral']:
        print(f"[FILE_HANDLING] Invalid event type: {event}. Must be 'fire', 'smoke', or 'neutral'")
        return False
    
    # Validate confidence level
    try:
        confidence = float(confidence_level)
        if confidence < 0 or confidence > 100:
            print(f"[FILE_HANDLING] Invalid confidence level: {confidence}. Must be between 0 and 100")
            return False
    except (ValueError, TypeError):
        print(f"[FILE_HANDLING] Invalid confidence level: {confidence_level}")
        return False
    
    # Update camera status
    current_time = time.time()
    with _status_lock:
        _camera_status[camera] = (event_lower, confidence, current_time)
    
    # Note: Frame storage is handled in log_detection_result to include bbox
    # This function just updates status
    
    return True

def _save_frame_snapshots():
    """Save latest annotated frames from all cameras as JPEG files in snaps folder"""
    global _camera_frames
    
    ensure_snaps_folder()
    snaps_dir = get_snaps_dir()
    
    with _frame_lock:
        frames_to_save = {cam: (frame.copy(), label, prob, bbox) 
                         for cam, (frame, label, prob, bbox) in _camera_frames.items()}
    
    # Save frames for all cameras (even if some don't have frames, create empty placeholder)
    for camera in CAMERA_NAMES:
        try:
            jpeg_path = os.path.join(snaps_dir, f"{camera}.jpeg")
            
            if camera in frames_to_save:
                frame, label, prob, bbox = frames_to_save[camera]
                
                # Annotate frame with model output
                annotated = frame.copy()
                
                # Choose color based on label
                if label == "fire":
                    color = (0, 0, 255)  # Red for fire
                elif label == "smoke":
                    color = (0, 165, 255)  # Orange for smoke
                else:
                    color = (0, 255, 0)  # Green for neutral
                
                # Draw bounding box if available
                if bbox is not None:
                    annotated = draw_bbox_on_frame(annotated, bbox, label.capitalize(), prob, color)
                
                # Add text overlay with prediction at top-left corner
                text = f"{label.capitalize()}: {prob:.1f}%"
                text_color = (0, 255, 0) if label == "neutral" else (0, 0, 255)
                cv2.putText(annotated, text, (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)
                
                # Save annotated frame as JPEG
                success, encoded_image = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if success:
                    with open(jpeg_path, 'wb') as f:
                        f.write(encoded_image.tobytes())
            else:
                # Create empty/placeholder image if no frame available
                placeholder = np.zeros((240, 320, 3), dtype=np.uint8)
                cv2.putText(placeholder, "NO FRAME", (80, 120), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (128, 128, 128), 2)
                success, encoded_image = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if success:
                    with open(jpeg_path, 'wb') as f:
                        f.write(encoded_image.tobytes())
        except Exception as e:
            # Silently fail - don't break CSV writing if snapshot fails
            pass

def flush_events():
    """
    Manually flush all camera statuses to CSV immediately.
    Useful for ensuring data is written before shutdown.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        _flush_events_to_csv()
        return True
    except Exception as e:
        print(f"[FILE_HANDLING] Error in manual flush: {e}")
        return False

def get_camera_status(camera: str = None):
    """
    Get the current status of a camera or all cameras.
    
    Args:
        camera: Camera name (optional). If None, returns all cameras.
    
    Returns:
        dict: Camera status(es) or None if camera not found
    """
    with _status_lock:
        if camera:
            if camera in _camera_status:
                event, confidence, timestamp = _camera_status[camera]
                return {camera: {'event': event, 'confidence': confidence, 'timestamp': timestamp}}
            return None
        else:
            # Return all camera statuses
            return {cam: {'event': event, 'confidence': conf, 'timestamp': ts} 
                   for cam, (event, conf, ts) in _camera_status.items()}

def log_detection_result(camera: str, label: str, confidence: float, frame: Optional[np.ndarray] = None, bbox: Optional[Tuple[int, int, int, int]] = None):
    """
    Update camera status with detection results from the model.
    Now logs all statuses including 'Neutral'.
    Status will be written to CSV every 5 seconds for all 4 cameras.
    Frames will be saved as JPEG snapshots when CSV is updated (with annotations).
    
    Args:
        camera: Camera name
        label: Detection label ('Fire', 'Smoke', or 'Neutral')
        confidence: Confidence level as a percentage (0-100)
        frame: Optional frame array to save as snapshot
        bbox: Optional bounding box tuple (x, y, w, h) for annotation
    
    Returns:
        bool: True if updated, False if failed
    """
    # Ensure flush thread is running (important in multiprocessing contexts)
    global _flush_thread
    if _flush_thread is None or not _flush_thread.is_alive():
        _start_flush_thread()
    
    # Store frame with detection results for annotation
    if frame is not None:
        with _frame_lock:
            _camera_frames[camera] = (frame.copy(), label.lower(), confidence, bbox)
    
    # Update status for all labels (fire, smoke, and neutral)
    return update_camera_status(camera, label, confidence, frame)

def get_recent_events(limit: int = 10):
    """
    Get the most recent events from the CSV
    
    Args:
        limit: Number of recent events to return (default: 10)
    
    Returns:
        list: List of dictionaries with event data
    """
    csv_path = get_csv_path()
    if not os.path.exists(csv_path):
        return []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            records = list(reader)
        
        # Return most recent records
        return records[-limit:] if len(records) > limit else records
    except Exception as e:
        print(f"[FILE_HANDLING] Error reading events: {e}")
        return []

# Initialize on module import
ensure_data_folder()
ensure_csv_file()
ensure_snaps_folder()
# Start flush thread - will be started in each process that imports this module
_start_flush_thread()

