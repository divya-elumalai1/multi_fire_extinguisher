
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
import cv2
import time
import threading
import multiprocessing
import uvicorn
import requests
import socket
from typing import Dict, Optional, TYPE_CHECKING, List
import numpy as np
import os
import logging
import hashlib
import yaml
import json

# Set multiprocessing start method
try:
    if hasattr(multiprocessing, 'set_start_method'):
        try:
            multiprocessing.set_start_method('fork', force=True)
        except RuntimeError:
            pass
except AttributeError:
    pass

try:
    from queue import Empty as QueueEmpty
except ImportError:
    from multiprocessing.queues import Empty as QueueEmpty

if TYPE_CHECKING:
    from multiprocessing.managers import DictProxy

from stream_utils import (
    load_model,
    capture_live_stream,
    predict_frame,
    draw_bbox_on_frame,
    get_model_path
)
from file_handling import log_detection_result
from send_alert import check_and_send_alert
from autonomous_mode import (
    is_autonomous_mode_enabled,
    send_motor_command as autonomous_send_motor_command,
    autonomous_mode_worker as autonomous_worker
)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

def load_config():
    """Load configuration from YAML file with fallback defaults"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    
    # Default configuration
    default_config = {
        "cameras": {
            "front": {"hostname": "firecamfront.local", "port": 80, "stream_path": "/front/stream"},
            "back": {"hostname": "firecamback.local", "port": 81, "stream_path": "/back/stream"},
            "left": {"hostname": "firecamleft.local", "port": 82, "stream_path": "/left/stream"},
            "right": {"hostname": "firecamright.local", "port": 83, "stream_path": "/right/stream"},
        },
        "motor": {
            "hostname": "firecamfront.local",
            "port": 80,
            "path": "/front/motor",
            "autonomous_mode": False
        },
        "stream": {
            "target_fps": 2.0,
            "frame_interval": 0.5,
            "inference_every_n": 5,
            "jpeg_quality": 60
        }
    }
    
    # Try to load from YAML file
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f) or {}
            
            # Merge YAML config with defaults (YAML takes precedence)
            config = default_config.copy()
            if "cameras" in yaml_config:
                config["cameras"].update(yaml_config["cameras"])
            if "motor" in yaml_config:
                config["motor"].update(yaml_config["motor"])
            if "stream" in yaml_config:
                config["stream"].update(yaml_config["stream"])
            if "email" in yaml_config:
                if "email" not in config:
                    config["email"] = {}
                config["email"].update(yaml_config["email"])
            
            print(f"[CONFIG] Loaded configuration from {config_path}")
            return config
        except Exception as e:
            print(f"[CONFIG] Error loading config from {config_path}: {e}")
            print(f"[CONFIG] Using default configuration")
    else:
        print(f"[CONFIG] Config file not found at {config_path}, using defaults")
    
    return default_config

# Load configuration
config = load_config()

# Extract configuration values
DEFAULT_CAMERAS = config["cameras"]
DEFAULT_MOTOR = config["motor"]
TARGET_FPS = config["stream"]["target_fps"]
FRAME_INTERVAL = config["stream"]["frame_interval"]
INFERENCE_EVERY_N = config["stream"]["inference_every_n"]
JPEG_QUALITY = config["stream"]["jpeg_quality"]

# Runtime Config
current_cameras = DEFAULT_CAMERAS.copy()
current_motor = DEFAULT_MOTOR.copy()

app = FastAPI(title="Fire Detection Dashboard")

class CameraConfig(BaseModel):
    hostname: str
    port: int
    stream_path: str

class MotorConfig(BaseModel):
    hostname: str
    port: int
    path: str

class StreamControl(BaseModel):
    cameras: List[str]

class MotorCommand(BaseModel):
    cmd: str

class ConfigUpdate(BaseModel):
    cameras: Dict[str, CameraConfig]

class EmailConfig(BaseModel):
    enable: bool
    sender: str
    app_pass: str
    receiver: List[str]
    interval: int
    alert_types: List[str]

class AutonomousConfig(BaseModel):
    enabled: bool

# Global State
frame_queues: Dict[str, multiprocessing.Queue] = {}
result_map: Optional["DictProxy"] = None
stream_flags: Optional["DictProxy"] = None
health_status: Optional["DictProxy"] = None
stream_processes: Dict[str, multiprocessing.Process] = {}
inference_process: Optional[multiprocessing.Process] = None
# Manager process instance
manager = None

health_lock = threading.RLock()
autonomous_mode_enabled = False
autonomous_mode_lock = threading.RLock()
last_fire_detection_time: Dict[str, float] = {}  # Track last fire detection per camera to prevent spam


# -----------------------------------------------------------------------------
# Process Management
# -----------------------------------------------------------------------------

def stop_camera_process(name: str):
    """Stop a specific camera process"""
    global stream_processes, stream_flags
    if name in stream_processes:
        print(f"[SYSTEM] Stopping {name}...")
        if stream_flags:
            stream_flags[name] = False
        
        proc = stream_processes[name]
        try:
            proc.join(timeout=1.0)
            if proc.is_alive():
                proc.terminate()
        except:
            pass
        
        del stream_processes[name]
        
        if health_status and name in health_status:
            try:
                health_status[name] = {"online": False, "last_frame_time": 0, "fps": 0}
            except:
                pass

def start_camera_process(name: str):
    """Start a specific camera process using current config"""
    global stream_processes, stream_flags, frame_queues, result_map, health_status, inference_queue
    
    if name not in current_cameras:
        return

    stop_camera_process(name)
    
    if stream_flags:
        stream_flags[name] = True
        
    config = current_cameras[name]
    
    if name not in frame_queues:
        frame_queues[name] = multiprocessing.Queue(maxsize=1)
    
    # Initialize health status to "connecting" state when starting
    if health_status:
        try:
            health_status[name] = {"online": False, "last_frame_time": time.time(), "fps": 0, "status": "connecting"}
        except:
            pass
        
    try:
        proc = multiprocessing.Process(
            target=stream_camera_worker,
            args=(name, config, frame_queues[name], inference_queue, result_map, stream_flags, health_status),
            daemon=True
        )
        proc.start()
        stream_processes[name] = proc
        print(f"[SYSTEM] Started process for {name}")
    except Exception as e:
        print(f"[SYSTEM] Error starting process for {name}: {e}")

def check_health_periodically():
    while True:
        if health_status:
            with health_lock:
                for name in list(current_cameras.keys()):
                    try:
                        status = health_status.get(name, {})
                        last_frame_time = status.get("last_frame_time", 0)
                        # Only mark offline if last_frame_time is more than 8 seconds old
                        # This gives more time for slow frame reads (1-2 seconds per frame)
                        # and prevents false offline status during normal operation
                        if last_frame_time > 0 and time.time() - last_frame_time > 8.0:
                            # Only mark offline if there's actually a process running
                            # If no process, keep the status as is
                            if name in stream_processes:
                                health_status[name] = {"online": False, "last_frame_time": last_frame_time, "fps": 0}
                    except Exception:
                        pass
        time.sleep(1.0)


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/config")
async def get_config():
    return current_cameras

@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    global current_cameras
    for name, cam_config in config.cameras.items():
        if name in current_cameras:
            current_cameras[name] = cam_config.dict()
            if name in stream_processes:
                start_camera_process(name)
    return {"status": "updated", "config": current_cameras}

@app.get("/api/motor/config")
async def get_motor_config():
    return current_motor

@app.post("/api/motor/config")
async def update_motor_config(config: MotorConfig):
    global current_motor
    current_motor = config.dict()
    return {"status": "updated", "config": current_motor}

@app.get("/api/email/config")
async def get_email_config():
    """Get email configuration from config.yaml"""
    full_config = load_config()
    return full_config.get("email", {})

@app.post("/api/email/config")
async def update_email_config(email_config: EmailConfig):
    """Update email configuration in config.yaml"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    
    # Load existing full config
    full_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                full_config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[CONFIG] Error reading config for update: {e}")
    
    # Update email section
    full_config["email"] = email_config.dict()
    
    # Save back to file
    try:
        with open(config_path, 'w') as f:
            yaml.dump(full_config, f, default_flow_style=False)
        return {"status": "updated", "config": full_config["email"]}
    except Exception as e:
        print(f"[CONFIG] Error saving email config: {e}")
        raise HTTPException(500, f"Failed to save config: {e}")

@app.get("/api/autonomous/config")
async def get_autonomous_config():
    """Get autonomous mode configuration from config.yaml"""
    full_config = load_config()
    motor_config = full_config.get("motor", {})
    return {"enabled": motor_config.get("autonomous_mode", False)}

@app.post("/api/autonomous/config")
async def update_autonomous_config(autonomous_config: AutonomousConfig):
    """Update autonomous mode configuration in config.yaml"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    
    # Load existing full config
    full_config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                full_config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[CONFIG] Error reading config for update: {e}")
            raise HTTPException(500, f"Failed to read config: {e}")
    
    # Ensure motor section exists
    if "motor" not in full_config:
        full_config["motor"] = {}
    
    # Update autonomous_mode in motor section
    old_value = full_config["motor"].get("autonomous_mode", False)
    full_config["motor"]["autonomous_mode"] = autonomous_config.enabled
    
    print(f"[CONFIG] Updating autonomous_mode: {old_value} -> {autonomous_config.enabled}")
    
    # Save back to file
    try:
        with open(config_path, 'w') as f:
            yaml.dump(full_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
        
        # Verify the write by reading it back
        with open(config_path, 'r') as f:
            verify_config = yaml.safe_load(f)
            saved_value = verify_config.get("motor", {}).get("autonomous_mode", None)
            if saved_value != autonomous_config.enabled:
                print(f"[CONFIG] WARNING: Saved value ({saved_value}) doesn't match requested value ({autonomous_config.enabled})")
            else:
                print(f"[CONFIG] Successfully saved and verified autonomous_mode={autonomous_config.enabled} to {config_path}")
        
        # Update runtime config
        global current_motor, autonomous_mode_enabled
        current_motor["autonomous_mode"] = autonomous_config.enabled
        autonomous_mode_enabled = autonomous_config.enabled
        
        return {"status": "updated", "enabled": autonomous_config.enabled}
    except Exception as e:
        print(f"[CONFIG] Error saving autonomous config: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Failed to save config: {e}")

@app.post("/api/motor/send")
async def send_motor_command(command: MotorCommand):
    """Resolve IP and send motor command"""
    try:
        hostname = current_motor["hostname"]
        port = current_motor["port"]
        path = current_motor["path"]
        
        # Resolve IP to avoid DNS issues on ESP32 sometimes
        try:
            ip = socket.gethostbyname(hostname)
        except Exception as e:
            # Fallback to hostname if resolution fails
            ip = hostname
            print(f"[MOTOR] DNS resolution failed, using hostname: {e}")
            
        url = f"http://{ip}:{port}{path}"
        print(f"[MOTOR] Sending cmd='{command.cmd}' to {url}")
        
        # Send request
        try:
            resp = requests.get(url, params={"cmd": command.cmd}, timeout=3.0)
            return {"status": "sent", "code": resp.status_code, "url": url}
        except Exception as e:
             # Just log error but return success to UI so it doesn't alert user unnecessarily if robot is offline during testing
             print(f"[MOTOR] Request failed: {e}")
             return {"status": "failed", "error": str(e), "url": url}
             
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/restart/{camera_name}")
async def restart_camera(camera_name: str):
    if camera_name not in current_cameras:
        raise HTTPException(404, "Camera not found")
    start_camera_process(camera_name)
    return {"status": "restarted", "camera": camera_name}

@app.post("/api/control/start")
async def start_streams(control: StreamControl):
    for name in control.cameras:
        if name in current_cameras:
            if name not in stream_processes:
                start_camera_process(name)
    return {"status": "started", "cameras": control.cameras}

@app.post("/api/control/stop")
async def stop_streams(control: StreamControl):
    for name in control.cameras:
        stop_camera_process(name)
    return {"status": "stopped", "cameras": control.cameras}


# -----------------------------------------------------------------------------
# Streaming
# -----------------------------------------------------------------------------

def mjpeg_generator(camera_name: str):
    """Generate MJPEG stream from frame queue - optimized for performance"""
    # Create a placeholder "no signal" frame (black JPEG with text)
    placeholder_frame = None
    try:
        placeholder_img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(placeholder_img, "NO SIGNAL", (50, 120), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        _, placeholder_jpeg = cv2.imencode(".jpg", placeholder_img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        placeholder_frame = placeholder_jpeg.tobytes()
    except:
        # Fallback: minimal valid JPEG (1x1 black pixel)
        placeholder_frame = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xaa\xff\xd9'
    
    if camera_name not in frame_queues:
        # Send placeholder frame to establish connection
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder_frame + b"\r\n")
        return
    
    q = frame_queues[camera_name]
    consecutive_empty = 0
    max_empty_frames = 5  # Track empty frames but always send something
    
    while True:
        # Check if stream process exists
        if camera_name not in stream_processes and camera_name not in current_cameras: 
            # Send placeholder when no process
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder_frame + b"\r\n")
            time.sleep(2.0)  # Longer sleep when no process
            continue
        
        try:
            # Try to get frame with timeout that matches camera read timeout
            # Increased from 1.0s to 2.0s to handle slow camera reads better
            queue_get_start = time.time()
            jpeg_bytes = q.get(timeout=2.0)
            queue_get_duration = (time.time() - queue_get_start) * 1000
            if jpeg_bytes and len(jpeg_bytes) > 0:
                consecutive_empty = 0
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg_bytes + b"\r\n")
            else:
                consecutive_empty += 1
                # #region agent log
                try:
                    backend_dir = os.path.dirname(os.path.abspath(__file__))
                    project_root = os.path.dirname(backend_dir)
                    log_path = os.path.join(project_root, '.cursor', 'debug.log')
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)
                    with open(log_path, 'a') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"dashboard.py:339","message":"Queue returned empty bytes","data":{"camera_name":camera_name,"queue_get_duration_ms":round(queue_get_duration,2)},"timestamp":int(time.time()*1000)}) + '\n')
                        f.flush()
                except Exception as e:
                    print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
                # #endregion
                # Always send placeholder to keep connection alive (never stop yielding)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder_frame + b"\r\n")
                time.sleep(0.2)  # Slightly longer sleep to reduce CPU
        except QueueEmpty:
            consecutive_empty += 1
            # #region agent log
            try:
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(backend_dir)
                log_path = os.path.join(project_root, '.cursor', 'debug.log')
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"dashboard.py:347","message":"Queue empty - sending NO SIGNAL","data":{"camera_name":camera_name,"consecutive_empty":consecutive_empty,"queue_size":q.qsize(),"has_process":camera_name in stream_processes},"timestamp":int(time.time()*1000)}) + '\n')
                    f.flush()
            except (NotImplementedError, OSError, PermissionError):
                # Expected in multiprocessing contexts - file I/O may not work in worker processes
                # Silently ignore - critical info is already printed to stdout
                pass
            except Exception as e:
                # Only log unexpected errors
                if "Broken pipe" not in str(e) and "NotImplemented" not in str(e):
                    print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
            # #endregion
            # Always send placeholder to keep connection alive (never stop yielding)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder_frame + b"\r\n")
            time.sleep(0.2)  # Slightly longer sleep to reduce CPU
        except Exception as e:
            # Log error but continue (suppress broken pipe errors)
            if "Broken pipe" not in str(e):
                print(f"[MJPEG] Error in generator for {camera_name}: {e}")
            # Always send placeholder even on error to keep connection alive
            try:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder_frame + b"\r\n")
            except:
                pass
            time.sleep(0.2)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            content = f.read()
            # Add version hash for cache debugging
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            # Inject version log at the start of the main script block
            script_start = content.find('<script>')
            if script_start != -1:
                insert_pos = script_start + len('<script>')
                content = content[:insert_pos] + f'\n        console.log("Dashboard loaded - version: {content_hash}, health check interval: 60s");' + content[insert_pos:]
            response = HTMLResponse(content=content)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers["ETag"] = content_hash
            return response
    return "Template not found"

@app.get("/stream/{camera_name}")
async def stream(camera_name: str):
    return StreamingResponse(mjpeg_generator(camera_name), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/health")
async def health():
    if health_status:
        with health_lock:
            status_dict = {}
            for k in current_cameras:
                try:
                    val = health_status.get(k, {})
                    if isinstance(val, dict):
                        status_dict[k] = dict(val)
                    else:
                        status_dict[k] = val
                except Exception:
                    status_dict[k] = {"online": False, "last_frame_time": 0, "fps": 0}
        return JSONResponse(content=status_dict)
    return JSONResponse(content={})


# -----------------------------------------------------------------------------
# Initialization
# -----------------------------------------------------------------------------

def stream_camera_worker(camera_name: str, config: dict, frame_queue: multiprocessing.Queue, 
                         inference_queue: multiprocessing.Queue, result_map_dict: "DictProxy",
                         stream_flags_dict: "DictProxy", health_status_dict: "DictProxy"):
    # Worker Logic
    print(f"[{camera_name.upper()}] Stream started")
    frame_count = 0
    last_frame_time = 0
    frame_times = []
    
    try:
        from stream_utils import capture_live_stream  # Local import to ensure clean process space
        
        for frame in capture_live_stream(config["hostname"], config["port"], config["stream_path"]):
            # #region agent log
            try:
                backend_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(backend_dir)
                log_path = os.path.join(project_root, '.cursor', 'debug.log')
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, 'a') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A,C,D","location":"dashboard.py:422","message":"Frame received from generator","data":{"camera_name":camera_name,"frame_shape":frame.shape if frame is not None else None},"timestamp":int(time.time()*1000)}) + '\n')
                    f.flush()
            except (NotImplementedError, OSError, PermissionError):
                # Expected in multiprocessing contexts - file I/O may not work in worker processes
                # Silently ignore - critical info is already printed to stdout
                pass
            except Exception as e:
                # Only log unexpected errors
                if "Broken pipe" not in str(e) and "NotImplemented" not in str(e):
                    print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
            # #endregion
            if not stream_flags_dict.get(camera_name, True):
                break
            
            now = time.time()
            time_since_last = now - last_frame_time
            
            # Check if queue is empty - if so, always add frame to prevent NO SIGNAL
            queue_is_empty = False
            try:
                queue_is_empty = frame_queue.empty()
            except:
                pass  # Queue method may not be available in all contexts
            
            # Smart throttling: Skip frame only if:
            # 1. Queue already has a frame (not starving)
            # 2. AND frame arrived too soon (within FRAME_INTERVAL)
            # 3. AND it hasn't been too long since last frame (prevent starvation)
            STARVATION_TIMEOUT = 1.5  # If no frame queued for 1.5s, always add one
            should_skip = (not queue_is_empty and 
                          time_since_last < FRAME_INTERVAL and 
                          time_since_last < STARVATION_TIMEOUT)
            
            if should_skip:
                # #region agent log
                try:
                    backend_dir = os.path.dirname(os.path.abspath(__file__))
                    project_root = os.path.dirname(backend_dir)
                    log_path = os.path.join(project_root, '.cursor', 'debug.log')
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)
                    with open(log_path, 'a') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"dashboard.py:440","message":"Frame skipped due to throttling","data":{"camera_name":camera_name,"time_since_last":time_since_last,"FRAME_INTERVAL":FRAME_INTERVAL,"queue_empty":queue_is_empty},"timestamp":int(time.time()*1000)}) + '\n')
                        f.flush()
                except Exception as e:
                    print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
                # #endregion
                continue
            
            last_frame_time = now
            
            frame_count += 1
            
            # Update health
            current_time = time.time()
            frame_times.append(current_time)
            if len(frame_times) > 30:
                frame_times.pop(0)
            fps = 0
            if len(frame_times) > 1:
                time_span = frame_times[-1] - frame_times[0]
                if time_span > 0:
                    fps = round((len(frame_times) - 1) / time_span, 1)
            
            try:
                health_status_dict[camera_name] = {"online": True, "last_frame_time": current_time, "fps": fps}
                # Debug: print first few updates to verify health status is being set
                if frame_count <= 3:
                    print(f"[{camera_name.upper()}] Health status updated: online=True, fps={fps}")
            except Exception as e:
                print(f"[{camera_name.upper()}] Failed to update health status: {e}")
                pass
            
            # Inference
            if frame_count % INFERENCE_EVERY_N == 0:
                try:
                    inference_queue.put_nowait((camera_name, frame))
                except:
                    pass
            
            # Annotate
            annotated = frame.copy()
            try:
                res = result_map_dict.get(camera_name)
                if res:
                    label, prob, bbox = res
                    if bbox:
                         annotated = draw_bbox_on_frame(annotated, bbox, label, prob)
                    # Text
                    cv2.putText(annotated, f"{label}: {prob:.1f}%", (10, 30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255) if label!="Neutral" else (0,255,0), 2)
            except: pass
             
            # Health Overlay
            status_text = f"ONLINE | {fps} FPS" if fps > 0 else "ONLINE"
            ts = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.putText(annotated, status_text, (annotated.shape[1] - ts[0] - 10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # Encode
            try:
                s, j = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if s:
                    # Non-blocking put - handle queue full gracefully
                    try:
                        # Try to put frame (non-blocking)
                        frame_queue.put_nowait(j.tobytes())
                    except:
                        # Queue is full - remove oldest frame and add new one
                        try:
                            frame_queue.get_nowait()  # Remove oldest
                            frame_queue.put_nowait(j.tobytes())  # Add new
                        except:
                            pass  # If still fails, skip this frame
                    # #region agent log
                    try:
                        backend_dir = os.path.dirname(os.path.abspath(__file__))
                        project_root = os.path.dirname(backend_dir)
                        log_path = os.path.join(project_root, '.cursor', 'debug.log')
                        os.makedirs(os.path.dirname(log_path), exist_ok=True)
                        with open(log_path, 'a') as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"dashboard.py:437","message":"After queue put","data":{"camera_name":camera_name,"success":True},"timestamp":int(time.time()*1000)}) + '\n')
                            f.flush()
                    except Exception as e:
                        print(f"[DEBUG] Log write failed: {type(e).__name__}: {e}")
                    # #endregion
            except Exception as e:
                # #region agent log
                try:
                    backend_dir = os.path.dirname(os.path.abspath(__file__))
                    project_root = os.path.dirname(backend_dir)
                    log_path = os.path.join(project_root, '.cursor', 'debug.log')
                    os.makedirs(os.path.dirname(log_path), exist_ok=True)
                    with open(log_path, 'a') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"dashboard.py:442","message":"Queue put error","data":{"camera_name":camera_name,"error":str(e)},"timestamp":int(time.time()*1000)}) + '\n')
                        f.flush()
                except Exception as e2:
                    print(f"[DEBUG] Log write failed: {type(e2).__name__}: {e2}")
                # #endregion
                pass
            
    except Exception as e:
         print(f"[{camera_name}] Error: {e}")
         try:
            health_status_dict[camera_name] = {"online": False, "last_frame_time": 0, "fps": 0}
         except: pass

def inference_worker(model_path: str, in_queue: multiprocessing.Queue, 
                     res_map: "DictProxy", flags: "DictProxy"):
    print("[INFERENCE] Ready")
    model = None
    try:
        model = load_model(model_path)
    except: pass
    
    while True: # Keep running even if streams stop, to be ready
        try:
            c, f = in_queue.get(timeout=1.0)
            if model:
                l, p, b = predict_frame(f, model)
                res_map[c] = (l, p, b)
                # Log fire or smoke events to CSV (with frame and bbox for annotated snapshot)
                try:
                    log_detection_result(c, l, p, f, b)
                    # Check and send email alert if smoke/fire detected
                    # Only check when smoke or fire is detected (not neutral)
                    if l and l.lower() in ["smoke", "fire"]:
                        try:
                            check_and_send_alert()
                        except Exception as e:
                            # Don't let email errors break inference
                            print(f"[ALERT] Error checking/sending alert: {e}")
                except Exception as e:
                    # Don't let logging errors break inference
                    print(f"[INFERENCE] Error logging event: {e}")
        except QueueEmpty:
            pass
        except Exception:
            time.sleep(0.1)

def send_motor_command_sync(cmd: str):
    """Synchronous helper to send motor command (for use in threads)"""
    return autonomous_send_motor_command(cmd, current_motor)

def autonomous_mode_worker(result_map_dict: "DictProxy"):
    """Worker thread that monitors fire detection and sends autonomous motor commands"""
    global autonomous_mode_enabled, last_fire_detection_time
    
    # Use the autonomous mode worker from autonomous_mode.py
    autonomous_worker(
        result_map_dict=result_map_dict,
        cameras=current_cameras,
        motor_config=current_motor,
        enabled_flag=autonomous_mode_enabled,
        enabled_lock=autonomous_mode_lock,
        last_fire_times=last_fire_detection_time
    )

def init_dashboard_state(queues=None, results=None, flags=None, health=None):
    global frame_queues, result_map, stream_flags, health_status, manager, inference_queue, inference_process, autonomous_mode_enabled
    
    if queues:
        # Externally managed
        frame_queues = queues
        result_map = results
        stream_flags = flags
        health_status = health
        
        # Load autonomous mode from config
        autonomous_mode_enabled = current_motor.get("autonomous_mode", False)
        
        # Start autonomous mode worker even when externally managed
        threading.Thread(target=autonomous_mode_worker, args=(result_map,), daemon=True).start()
        
        print("[DASHBOARD] Attached to external state")
        return

    # Locally managed - LAZY START
    manager = multiprocessing.Manager()
    stream_flags = manager.dict()
    result_map = manager.dict()
    health_status = manager.dict()
    
    inference_queue = multiprocessing.Queue(maxsize=1)
    frame_queues = {name: multiprocessing.Queue(maxsize=1) for name in current_cameras}
    
    model_path = get_model_path()
    
    # Init Flags
    for name in current_cameras:
        stream_flags[name] = True
        result_map[name] = None
        health_status[name] = {"online": False, "last_frame_time": 0, "fps": 0}

    # Start Inference Worker ONLY 
    if model_path:
        inference_process = multiprocessing.Process(
            target=inference_worker,
            args=(model_path, inference_queue, result_map, stream_flags),
            daemon=True
        )
        inference_process.start()
        
    print("[DASHBOARD] System ready (Lazy Start - No streams active)")
    
    # Load autonomous mode from config
    autonomous_mode_enabled = current_motor.get("autonomous_mode", False)
    
    # Start background threads
    threading.Thread(target=check_health_periodically, daemon=True).start()
    threading.Thread(target=autonomous_mode_worker, args=(result_map,), daemon=True).start()

if __name__ == "__main__":
    init_dashboard_state()
    
    # Configure logging with timestamps
    log_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "access": {
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO"},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }
    
    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=log_config)
