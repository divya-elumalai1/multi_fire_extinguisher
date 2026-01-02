"""
NOTE: NOT USED IN THE BACKEND ANYMORE, KEPT ONLY

TO TEST IT USING IMSHOW


Multi-Camera Stream Launcher
Launches all four ESP32-CAM streams simultaneously and accepts terminal commands
to control the cameras via HTTP requests.

Usage:
    python stream_all.py

Terminal Commands:
    http://firecamback.local/front?cmd=0
    http://firecamfront.local/front?cmd=1
    etc.

Press 'q' in any window to quit that specific stream.
Type 'quit' or 'exit' in terminal to stop all streams.
"""

import cv2
import threading  # Keep for command input (I/O bound)
import multiprocessing
from multiprocessing.queues import Empty as QueueEmpty
import socket
import urllib.request
import urllib.error
import time
import os
import sys
from stream_utils import (
    load_model,
    capture_live_stream,
    predict_frame,
    draw_bbox_on_frame,
    get_model_path
)

# -----------------------------
# Inference Configuration run ML every N frames, reuse last result
# -----------------------------
INFERENCE_EVERY_N = 10  # Run inference every N frames (1 inference per 10 frames = ~2 FPS at 20 FPS stream)

# -----------------------------
# Camera Configuration
# -----------------------------
CAMERAS = {
    "front": {
        "hostname": "firecamfront.local",
        "port": 80,
        "stream_path": "/front/stream",
        "window_name": "FRONT Camera - Fire Detection",
        "control_path": "/front"  # For commands like /front?cmd=0
    },
    "back": {
        "hostname": "firecamback.local",
        "port": 81,
        "stream_path": "/back/stream",
        "window_name": "BACK Camera - Fire Detection",
        "control_path": "/back"
    },
    "left": {
        "hostname": "firecamleft.local",
        "port": 82,
        "stream_path": "/left/stream",
        "window_name": "LEFT Camera - Fire Detection",
        "control_path": "/left"
    },
    "right": {
        "hostname": "firecamright.local",
        "port": 83,
        "stream_path": "/right/stream",
        "window_name": "RIGHT Camera - Fire Detection",
        "control_path": "/right"
    }
}

# Global process/manager references (initialized in main)
stream_flags = None  # Manager().dict()
stream_processes = {}  # Dict of multiprocessing.Process
frame_queues = {}  # Dict of multiprocessing.Queue
quit_flags = None  # Manager().dict()

# Central inference architecture (multiprocessing)
inference_queue = None  # multiprocessing.Queue(maxsize=1)
result_map = None  # Manager().dict() - Store inference results per camera
result_map_lock = None  # multiprocessing.Lock()
inference_worker_process = None  # Single inference worker process
manager = None  # multiprocessing.Manager() for shared state


# -----------------------------
# HTTP Command Functions
# -----------------------------

def resolve_hostname(hostname):
    """Resolve hostname to IP address"""
    try:
        ip = socket.gethostbyname(hostname)
        return ip
    except socket.gaierror as e:
        print(f"[ERROR] Failed to resolve {hostname}: {e}")
        return None


def send_camera_command(url):
    """
    Send HTTP command to camera.
    
    Args:
        url (str): Full URL like "http://firecamback.local/front?cmd=0"
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Parse URL to extract hostname and path
        if not url.startswith("http://"):
            print("[ERROR] URL must start with http://")
            return False
        
        # Remove http:// prefix
        url_part = url[7:]
        
        # Split hostname and path/query
        if "/" in url_part:
            parts = url_part.split("/", 1)
            hostname = parts[0]
            path_with_query = "/" + parts[1]
        else:
            # No path, just hostname (with optional query)
            if "?" in url_part:
                parts = url_part.split("?", 1)
                hostname = parts[0]
                path_with_query = "/?" + parts[1]
            else:
                hostname = url_part
                path_with_query = "/"
        
        # Resolve hostname to IP
        ip = resolve_hostname(hostname)
        if ip is None:
            return False
        
        # Construct full URL with IP
        full_url = f"http://{ip}{path_with_query}"
        
        print(f"[CMD] Sending command to {hostname} ({ip}): {path_with_query}")
        
        # Send HTTP GET request
        req = urllib.request.Request(full_url)
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            print(f"[CMD] Response: {resp.status} - {body[:100]}")
            return True
            
    except urllib.error.URLError as e:
        print(f"[ERROR] Failed to send command: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return False


def command_input_loop(stream_flags_dict):
    """Loop to accept terminal commands (runs in thread, I/O bound)"""
    print("\n" + "="*60)
    print("Command Interface Ready")
    print("="*60)
    print("Enter HTTP commands to control cameras:")
    print("  Example: http://firecamback.local/front?cmd=0")
    print("  Type 'quit' or 'exit' to stop all streams")
    print("="*60 + "\n")
    
    while True:
        try:
            command = input("> ").strip()
            
            if not command:
                continue
            
            # Check for quit commands
            if command.lower() in ['quit', 'exit', 'q']:
                print("[INFO] Stopping all streams...")
                for camera_name in stream_flags_dict:
                    stream_flags_dict[camera_name] = False
                break
            
            # Send HTTP command
            if command.startswith("http://"):
                send_camera_command(command)
            else:
                print("[ERROR] Command must be an HTTP URL starting with http://")
                print("  Example: http://firecamback.local/front?cmd=0")
                
        except EOFError:
            # Handle Ctrl+D
            print("\n[INFO] Stopping all streams...")
            for camera_name in stream_flags_dict:
                stream_flags_dict[camera_name] = False
            break
        except KeyboardInterrupt:
            print("\n[INFO] Stopping all streams...")
            for camera_name in stream_flags_dict:
                stream_flags_dict[camera_name] = False
            break


# -----------------------------
# Stream Functions
# -----------------------------

def inference_worker(model_path, inference_queue, result_map_dict, result_map_lock, stream_flags_dict):
    """
    Single inference worker process (Central Brain).
    Processes frames from inference_queue and updates result_map.
    
    Args:
        model_path: Path to model file (load in this process)
        inference_queue: multiprocessing.Queue for frames
        result_map_dict: Manager().dict() for results
        result_map_lock: multiprocessing.Lock for thread-safe access
        stream_flags_dict: Manager().dict() for stream control flags
    """
    print("[INFERENCE] Inference worker process started (Central Brain)")
    
    # Load model in this process
    if model_path is None or not os.path.exists(model_path):
        print("[INFERENCE] No model available, inference worker exiting")
        return
    
    try:
        model = load_model(model_path)
        print("[INFERENCE] Model loaded in worker process")
    except Exception as e:
        print(f"[INFERENCE] Failed to load model: {e}")
        return
    
    try:
        while any(stream_flags_dict.values()):
            try:
                # Get frame from inference queue (blocking with timeout)
                camera_name, frame = inference_queue.get(timeout=1.0)
                
                # Run inference
                try:
                    label, prob, bbox = predict_frame(frame, model)
                    
                    # Update result_map (process-safe)
                    with result_map_lock:
                        result_map_dict[camera_name] = (label, prob, bbox)
                    
                except Exception as e:
                    print(f"[INFERENCE] Error processing {camera_name}: {e}")
                    
            except QueueEmpty:
                # Timeout - check if we should continue
                continue
            except Exception as e:
                print(f"[INFERENCE] Error in inference worker: {e}")
                time.sleep(0.1)
                
    except Exception as e:
        print(f"[INFERENCE] Inference worker error: {e}")
    finally:
        print("[INFERENCE] Inference worker stopped")


def stream_camera(camera_name, camera_config, frame_queue, inference_queue, result_map_dict, result_map_lock, stream_flags_dict):
    """
    Stream from a single camera in a separate process (Capture + decode, no ML).
    Captures frames, queues them for inference, gets results from result_map, and annotates.
    
    Args:
        camera_name (str): Name of the camera (front, back, left, right)
        camera_config (dict): Camera configuration
        frame_queue: multiprocessing.Queue to put processed frames for main process display
        inference_queue: multiprocessing.Queue for inference requests
        result_map_dict: Manager().dict() for inference results
        result_map_lock: multiprocessing.Lock for thread-safe access
        stream_flags_dict: Manager().dict() for stream control flags
    """
    hostname = camera_config["hostname"]
    port = camera_config["port"]
    stream_path = camera_config["stream_path"]
    
    frame_count = 0
    
    try:
        for frame in capture_live_stream(hostname, port, stream_path):
            # Check if stream should stop
            if not stream_flags_dict.get(camera_name, True):
                print(f"[{camera_name.upper()}] Stream stopped by flag")
                break
            
            frame_count += 1
            
            # Queue frame for inference (only every N frames, non-blocking)
            if frame_count % INFERENCE_EVERY_N == 0:
                try:
                    # Only push one frame at a time (size=1 queue drops old frames)
                    inference_queue.put((camera_name, frame.copy()), block=False)
                except Exception:  # Queue full (multiprocessing.queues.Full)
                    # Queue full, skip this inference (will use last result)
                    pass
            
            # Get latest result from result_map (process-safe)
            result = None
            with result_map_lock:
                result = result_map_dict.get(camera_name)
            
            # Annotate frame with result if available
            if result:
                label, prob, bbox = result
                
                # Print prediction results (less frequent)
                if frame_count % 30 == 0:
                    print(f"[{camera_name.upper()}] Frame {frame_count}: {label} ({prob:.1f}%)")
                
                # Draw bounding box and label on frame
                if bbox is not None:
                    # Choose color based on label
                    if label == "Fire":
                        color = (0, 0, 255)  # Red for fire
                    elif label == "Smoke":
                        color = (0, 165, 255)  # Orange for smoke
                    else:
                        color = (0, 255, 0)  # Green for neutral
                    
                    frame = draw_bbox_on_frame(frame, bbox, label, prob, color)
                
                # Add text overlay with prediction at top-left corner
                text = f"{label}: {prob:.1f}%"
                cv2.putText(
                    frame,
                    text,
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0) if label == "Neutral" else (0, 0, 255),
                    2,
                )
            
            # Put frame in queue for main process to display
            try:
                frame_queue.put((camera_name, frame), block=False)
            except Exception:  # Queue full (multiprocessing.queues.Full)
                # Skip this frame if queue is full (backpressure)
                pass
                
    except Exception as e:
        print(f"[{camera_name.upper()}] ERROR in stream: {e}")
    finally:
        print(f"[{camera_name.upper()}] Stream process ended")


# -----------------------------
# Main Function
# -----------------------------

def main():
    """Main function to launch all streams using multiprocessing"""
    global stream_flags, stream_processes, frame_queues, quit_flags
    global inference_queue, result_map, result_map_lock, inference_worker_process, manager
    
    print("="*60)
    print("Multi-Camera Fire Detection System (Multiprocessing)")
    print("="*60)
    
    # Initialize multiprocessing manager for shared state
    manager = multiprocessing.Manager()
    stream_flags = manager.dict()
    quit_flags = manager.dict()
    result_map = manager.dict()
    result_map_lock = manager.Lock()
    
    # Initialize multiprocessing queues
    inference_queue = multiprocessing.Queue(maxsize=1)  # Single queue for inference
    frame_queues = {}  # One queue per camera for display
    
    # Load model path (model will be loaded in inference worker process)
    model_path = get_model_path()
    print(f"\n[INFO] Model path: {model_path}")
    
    if not os.path.exists(model_path):
        print(f"[ERROR] Model file not found: {model_path}")
        print("[INFO] Continuing without model inference...")
        model_path = None
    
    # Initialize stream flags and queues
    for camera_name in CAMERAS:
        stream_flags[camera_name] = True
        frame_queues[camera_name] = multiprocessing.Queue(maxsize=2)  # Small queue to prevent lag
        quit_flags[camera_name] = False
        result_map[camera_name] = None  # Initialize result map
    
    # Start command input thread (I/O bound, can stay as thread)
    command_thread = threading.Thread(
        target=command_input_loop,
        args=(stream_flags,),
        daemon=True
    )
    command_thread.start()
    
    # Start single inference worker process (Central Brain)
    if model_path is not None:
        inference_worker_process = multiprocessing.Process(
            target=inference_worker,
            args=(model_path, inference_queue, result_map, result_map_lock, stream_flags),
            daemon=True
        )
        inference_worker_process.start()
        print("[INFO] Started inference worker process (Central Brain)")
    
    # Start all camera streams in separate processes (Capture + decode, no ML)
    print("\n[INFO] Starting all camera streams (capture processes)...")
    for camera_name, camera_config in CAMERAS.items():
        process = multiprocessing.Process(
            target=stream_camera,
            args=(
                camera_name,
                camera_config,
                frame_queues[camera_name],
                inference_queue,
                result_map,
                result_map_lock,
                stream_flags
            ),
            daemon=True
        )
        process.start()
        stream_processes[camera_name] = process
        print(f"[INFO] Started {camera_name.upper()} camera capture process")
        time.sleep(0.5)  # Small delay between starting processes
    
    print("\n[INFO] All streams started. Windows should appear shortly.")
    print("[INFO] Press 'q' in any window to close that stream.")
    print("[INFO] Type 'quit' or 'exit' in terminal to stop all streams.\n")
    
    # Main display loop - all OpenCV operations happen here (main process)
    try:
        while any(stream_flags.values()):
            # Process frames from all queues
            for camera_name, camera_config in CAMERAS.items():
                if quit_flags.get(camera_name, False):
                    continue
                
                window_name = camera_config["window_name"]
                
                # Try to get frame from queue (non-blocking)
                try:
                    _, frame = frame_queues[camera_name].get_nowait()
                    
                    # Display frame (main process only)
                    cv2.imshow(window_name, frame)
                    
                except QueueEmpty:
                    # No frame available, skip
                    pass
            
            # Check for quit key (main process only) - 'q' closes all windows
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("[INFO] Quit key pressed, closing all streams...")
                for camera_name in stream_flags:
                    stream_flags[camera_name] = False
                    quit_flags[camera_name] = True
                    try:
                        cv2.destroyWindow(CAMERAS[camera_name]["window_name"])
                    except cv2.error:
                        pass  # Window might not exist yet
                break
            
            # Check if any process is still alive
            alive_processes = [name for name, proc in stream_processes.items() 
                             if proc.is_alive() and stream_flags.get(name, False)]
            if not alive_processes:
                break
            
            time.sleep(0.01)  # Small sleep to prevent CPU spinning
                
    except KeyboardInterrupt:
        print("\n[INFO] Keyboard interrupt received, stopping all streams...")
        for camera_name in stream_flags:
            stream_flags[camera_name] = False
    
    # Cleanup - wait a bit for processes to finish
    print("\n[INFO] Waiting for streams to finish...")
    for camera_name, process in stream_processes.items():
        if process.is_alive():
            process.join(timeout=2.0)
            if process.is_alive():
                print(f"[WARN] Force terminating {camera_name} process")
                process.terminate()
                process.join(timeout=1.0)
    
    # Wait for inference worker to finish
    if inference_worker_process is not None and inference_worker_process.is_alive():
        inference_worker_process.join(timeout=2.0)
        if inference_worker_process.is_alive():
            print("[WARN] Force terminating inference worker process")
            inference_worker_process.terminate()
            inference_worker_process.join(timeout=1.0)
    
    print("[INFO] Closing all windows...")
    try:
        cv2.destroyAllWindows()
    except:
        pass
    print("[INFO] All streams stopped. Goodbye!")


if __name__ == "__main__":
    main()

