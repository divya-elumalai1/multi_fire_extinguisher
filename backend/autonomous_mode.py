'''
Autonomous Mode - Fire Detection Response System

This module defines the autonomous response patterns when fire is detected in specific cameras.
The autonomous mode worker thread in dashboard.py monitors fire detection results and
executes these predefined response sequences automatically.

Motor Command Reference:
------------------------
0 - servo close (mud close)
1 - servo open (mud open)
2 - moist on
3 - moist off
4 - pump on
5 - pump off
6 - motor forward (up button)
7 - motor backward (down button)
8 - motor right (right button)
9 - motor left (left button)
p - motor stop

Autonomous Response Patterns:
-----------------------------

All motor commands are sent via HTTP GET requests to the ESP32 motor endpoint.

Front Camera Fire Detection:
    When fire is detected in the front camera, execute the following sequence:
    1. GET request with cmd="7" - move backward
    2. Wait 2 seconds
    3. GET request with cmd="p" - stop motor
    4. GET request with cmd="1" - servo open
    5. Wait 2 seconds
    6. GET request with cmd="0" - servo close
    7. Wait 2 seconds
    8. GET request with cmd="2" - moist on
    9. Wait 2 seconds
    10. GET request with cmd="3" - moist off
    11. Wait 2 seconds
    12. GET request with cmd="4" - turn on motor pump
    13. Wait 2 seconds
    14. GET request with cmd="5" - turn off motor pump

Back Camera Fire Detection:
    When fire is detected in the back camera, execute the following sequence:
    1. GET request with cmd="6" - move forward
    2. Wait 2 seconds
    3. GET request with cmd="p" - stop motor
    4. GET request with cmd="1" - servo open
    5. Wait 2 seconds
    6. GET request with cmd="0" - servo close
    7. Wait 2 seconds
    8. GET request with cmd="2" - moist on
    9. Wait 2 seconds
    10. GET request with cmd="3" - moist off
    11. Wait 2 seconds
    12. GET request with cmd="4" - turn on motor pump
    13. Wait 2 seconds
    14. GET request with cmd="5" - turn off motor pump

Left Camera Fire Detection:
    When fire is detected in the left camera, execute the following sequence:
    1. GET request with cmd="9" - move left
    2. Wait 1 second
    3. GET request with cmd="p" - stop motor
    4. GET request with cmd="7" - move backward
    5. Wait 1 second
    6. GET request with cmd="p" - stop motor
    7. GET request with cmd="1" - servo open
    8. Wait 2 seconds
    9. GET request with cmd="0" - servo close
    10. Wait 2 seconds
    11. GET request with cmd="2" - moist on
    12. Wait 2 seconds
    13. GET request with cmd="3" - moist off
    14. Wait 2 seconds
    15. GET request with cmd="4" - turn on motor pump
    16. Wait 2 seconds
    17. GET request with cmd="5" - turn off motor pump

Right Camera Fire Detection:
    When fire is detected in the right camera, execute the following sequence:
    1. GET request with cmd="8" - move right
    2. Wait 1 second
    3. GET request with cmd="p" - stop motor
    4. GET request with cmd="7" - move backward
    5. Wait 1 second
    6. GET request with cmd="p" - stop motor
    7. GET request with cmd="1" - servo open
    8. Wait 2 seconds
    9. GET request with cmd="0" - servo close
    10. Wait 2 seconds
    11. GET request with cmd="2" - moist on
    12. Wait 2 seconds
    13. GET request with cmd="3" - moist off
    14. Wait 2 seconds
    15. GET request with cmd="4" - turn on motor pump
    16. Wait 2 seconds
    17. GET request with cmd="5" - turn off motor pump

Note: The autonomous mode worker has a cooldown period (30 seconds) between responses
to prevent command spam if fire is continuously detected.
'''

import requests
import socket
import time
import os
import yaml
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from multiprocessing.managers import DictProxy


def load_config():
    """Load configuration from YAML file"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            return config
        except Exception as e:
            print(f"[AUTONOMOUS] Error loading config: {e}")
            return {}
    return {}


def is_autonomous_mode_enabled() -> bool:
    """Check if autonomous mode is enabled in config.yaml"""
    config = load_config()
    motor_config = config.get("motor", {})
    return motor_config.get("autonomous_mode", False)


def send_motor_command(cmd: str, motor_config: Optional[Dict] = None) -> Dict:
    """
    Send a motor command to ESP32 via HTTP GET request.
    
    Args:
        cmd: Motor command code (e.g., "7", "p", "4", "5")
        motor_config: Optional motor configuration dict. If None, loads from config.yaml
        
    Returns:
        Dict with status and response details
    """
    try:
        # Load motor config if not provided
        if motor_config is None:
            config = load_config()
            motor_config = config.get("motor", {})
        
        hostname = motor_config.get("hostname", "firecamfront.local")
        port = motor_config.get("port", 80)
        path = motor_config.get("path", "/front/motor")
        
        # Resolve IP to avoid DNS issues on ESP32 sometimes
        try:
            ip = socket.gethostbyname(hostname)
        except Exception as e:
            ip = hostname
            print(f"[AUTONOMOUS] DNS resolution failed, using hostname: {e}")
        
        url = f"http://{ip}:{port}{path}"
        print(f"[AUTONOMOUS] Sending cmd='{cmd}' to {url}")
        
        resp = requests.get(url, params={"cmd": cmd}, timeout=3.0)
        return {"status": "sent", "code": resp.status_code, "url": url}
    except Exception as e:
        print(f"[AUTONOMOUS] Failed to send command '{cmd}': {e}")
        return {"status": "failed", "error": str(e)}


def execute_front_camera_response(motor_config: Optional[Dict] = None):
    """
    Execute autonomous response sequence for front camera fire detection.
    
    Sequence:
    1. Move backward (cmd: "7")
    2. Wait 2 seconds
    3. Stop motor (cmd: "p")
    4. Servo open (cmd: "1")
    5. Wait 2 seconds
    6. Servo close (cmd: "0")
    7. Wait 2 seconds
    8. Moist on (cmd: "2")
    9. Wait 2 seconds
    10. Moist off (cmd: "3")
    11. Wait 2 seconds
    12. Motor pump on (cmd: "4")
    13. Wait 2 seconds
    14. Motor pump off (cmd: "5")

    
    Args:
        motor_config: Optional motor configuration dict
    """
    print("[AUTONOMOUS] Executing front camera fire response sequence")
    
    # 1. Move backward
    result = send_motor_command('7', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '7' (move backward): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 2. Stop motor
    result = send_motor_command('p', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command 'p' (stop): {result.get('error', 'Unknown error')}")
    
    # 3. Servo open
    result = send_motor_command('1', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '1' (servo open): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 4. Servo close
    result = send_motor_command('0', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '0' (servo close): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 5. Moist on
    result = send_motor_command('2', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '2' (moist on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 6. Moist off
    result = send_motor_command('3', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '3' (moist off): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 7. Motor pump on
    result = send_motor_command('4', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '4' (pump on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 8. Motor pump off
    result = send_motor_command('5', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '5' (pump off): {result.get('error', 'Unknown error')}")
    
    print("[AUTONOMOUS] Front camera fire response sequence completed")


def execute_back_camera_response(motor_config: Optional[Dict] = None):
    """
    Execute autonomous response sequence for back camera fire detection.
    
    Sequence:
    1. Move forward (cmd: "6")
    2. Wait 2 seconds
    3. Stop motor (cmd: "p")
    4. Servo open (cmd: "1")
    5. Wait 2 seconds
    6. Servo close (cmd: "0")
    7. Wait 2 seconds
    8. Moist on (cmd: "2")
    9. Wait 2 seconds
    10. Moist off (cmd: "3")
    11. Wait 2 seconds
    12. Motor pump on (cmd: "4")
    13. Wait 2 seconds
    14. Motor pump off (cmd: "5")
    
    Args:
        motor_config: Optional motor configuration dict
    """
    print("[AUTONOMOUS] Executing back camera fire response sequence")
    
    # 1. Move forward
    result = send_motor_command('6', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '6' (move forward): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 2. Stop motor
    result = send_motor_command('p', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command 'p' (stop): {result.get('error', 'Unknown error')}")
    
    # 3. Servo open
    result = send_motor_command('1', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '1' (servo open): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 4. Servo close
    result = send_motor_command('0', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '0' (servo close): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 5. Moist on
    result = send_motor_command('2', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '2' (moist on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 6. Moist off
    result = send_motor_command('3', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '3' (moist off): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 7. Motor pump on
    result = send_motor_command('4', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '4' (pump on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 8. Motor pump off
    result = send_motor_command('5', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '5' (pump off): {result.get('error', 'Unknown error')}")
    
    print("[AUTONOMOUS] Back camera fire response sequence completed")


def execute_left_camera_response(motor_config: Optional[Dict] = None):
    """
    Execute autonomous response sequence for left camera fire detection.
    
    Sequence:
    1. Move left (cmd: "9")
    2. Wait 1 second
    3. Stop motor (cmd: "p")
    4. Move backward (cmd: "7")
    5. Wait 1 second
    6. Stop motor (cmd: "p")
    7. Servo open (cmd: "1")
    8. Wait 2 seconds
    9. Servo close (cmd: "0")
    10. Wait 2 seconds
    11. Moist on (cmd: "2")
    12. Wait 2 seconds
    13. Moist off (cmd: "3")
    14. Wait 2 seconds
    15. Motor pump on (cmd: "4")
    16. Wait 2 seconds
    17. Motor pump off (cmd: "5")
    
    Args:
        motor_config: Optional motor configuration dict
    """
    print("[AUTONOMOUS] Executing left camera fire response sequence")
    
    # 1. Move left
    result = send_motor_command('9', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '9' (move left): {result.get('error', 'Unknown error')}")
    time.sleep(1.0)
    
    # 2. Stop motor
    result = send_motor_command('p', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command 'p' (stop): {result.get('error', 'Unknown error')}")
    
    # 3. Move backward
    result = send_motor_command('7', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '7' (move backward): {result.get('error', 'Unknown error')}")
    time.sleep(1.0)
    
    # 4. Stop motor
    result = send_motor_command('p', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command 'p' (stop): {result.get('error', 'Unknown error')}")
    
    # 5. Servo open
    result = send_motor_command('1', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '1' (servo open): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 6. Servo close
    result = send_motor_command('0', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '0' (servo close): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 7. Moist on
    result = send_motor_command('2', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '2' (moist on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 8. Moist off
    result = send_motor_command('3', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '3' (moist off): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 9. Motor pump on
    result = send_motor_command('4', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '4' (pump on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 10. Motor pump off
    result = send_motor_command('5', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '5' (pump off): {result.get('error', 'Unknown error')}")
    
    print("[AUTONOMOUS] Left camera fire response sequence completed")


def execute_right_camera_response(motor_config: Optional[Dict] = None):
    """
    Execute autonomous response sequence for right camera fire detection.
    
    Sequence:
    1. Move right (cmd: "8")
    2. Wait 1 second
    3. Stop motor (cmd: "p")
    4. Move backward (cmd: "7")
    5. Wait 1 second
    6. Stop motor (cmd: "p")
    7. Servo open (cmd: "1")
    8. Wait 2 seconds
    9. Servo close (cmd: "0")
    10. Wait 2 seconds
    11. Moist on (cmd: "2")
    12. Wait 2 seconds
    13. Moist off (cmd: "3")
    14. Wait 2 seconds
    15. Motor pump on (cmd: "4")
    16. Wait 2 seconds
    17. Motor pump off (cmd: "5")
    
    Args:
        motor_config: Optional motor configuration dict
    """
    print("[AUTONOMOUS] Executing right camera fire response sequence")
    
    # 1. Move right
    result = send_motor_command('8', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '8' (move right): {result.get('error', 'Unknown error')}")
    time.sleep(1.0)
    
    # 2. Stop motor
    result = send_motor_command('p', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command 'p' (stop): {result.get('error', 'Unknown error')}")
    
    # 3. Move backward
    result = send_motor_command('7', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '7' (move backward): {result.get('error', 'Unknown error')}")
    time.sleep(1.0)
    
    # 4. Stop motor
    result = send_motor_command('p', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command 'p' (stop): {result.get('error', 'Unknown error')}")
    
    # 5. Servo open
    result = send_motor_command('1', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '1' (servo open): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 6. Servo close
    result = send_motor_command('0', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '0' (servo close): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 7. Moist on
    result = send_motor_command('2', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '2' (moist on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 8. Moist off
    result = send_motor_command('3', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '3' (moist off): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 9. Motor pump on
    result = send_motor_command('4', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '4' (pump on): {result.get('error', 'Unknown error')}")
    time.sleep(2.0)
    
    # 10. Motor pump off
    result = send_motor_command('5', motor_config)
    if result.get("status") != "sent":
        print(f"[AUTONOMOUS] Warning: Failed to send command '5' (pump off): {result.get('error', 'Unknown error')}")
    
    print("[AUTONOMOUS] Right camera fire response sequence completed")


def execute_camera_response(camera_name: str, motor_config: Optional[Dict] = None):
    """
    Execute the appropriate autonomous response sequence based on camera name.
    
    Args:
        camera_name: Name of the camera where fire was detected (e.g., "front", "back", "left", "right")
        motor_config: Optional motor configuration dict
    """
    if camera_name == "front":
        execute_front_camera_response(motor_config)
    elif camera_name == "back":
        execute_back_camera_response(motor_config)
    elif camera_name == "left":
        execute_left_camera_response(motor_config)
    elif camera_name == "right":
        execute_right_camera_response(motor_config)
    else:
        print(f"[AUTONOMOUS] Unknown camera name: {camera_name}")


def autonomous_mode_worker(result_map_dict: "DictProxy", cameras: Dict, motor_config: Dict, 
                          enabled_flag: bool, enabled_lock, last_fire_times: Dict[str, float]):
    """
    Worker thread that monitors fire detection and sends autonomous motor commands.
    
    This function should be called from dashboard.py in a separate thread.
    
    Args:
        result_map_dict: Shared dict containing detection results for each camera
        cameras: Dict of camera configurations
        motor_config: Motor configuration dict
        enabled_flag: Boolean flag indicating if autonomous mode is enabled (runtime state)
        enabled_lock: Lock for accessing enabled_flag
        last_fire_times: Dict tracking last fire detection time per camera
    """
    print("[AUTONOMOUS] Autonomous mode worker started")
    
    # Minimum time between fire responses (in seconds) to prevent spam
    FIRE_RESPONSE_COOLDOWN = 30  # 30 seconds cooldown between autonomous responses
    
    while True:
        try:
            # Check if autonomous mode is enabled
            # First check runtime flag, then fallback to config file
            with enabled_lock:
                enabled = enabled_flag
            
            # Also check config file directly (in case config was updated externally)
            if not enabled:
                enabled = is_autonomous_mode_enabled()
            
            if not enabled:
                time.sleep(2.0)  # Check every 2 seconds when disabled
                continue
            
            # Check for fire detection in result_map
            if result_map_dict:
                for camera_name in cameras.keys():
                    try:
                        result = result_map_dict.get(camera_name)
                        if result:
                            # Safely unpack result - should be (label, prob, bbox) tuple
                            try:
                                if isinstance(result, tuple) and len(result) >= 2:
                                    label, prob = result[0], result[1]
                                    # bbox is optional (result[2] if exists)
                                else:
                                    # Invalid result format, skip
                                    continue
                            except (TypeError, IndexError) as e:
                                print(f"[AUTONOMOUS] Invalid result format for {camera_name}: {result}, error: {e}")
                                continue
                            
                            # Check if fire is detected (case-insensitive)
                            if label and isinstance(label, str) and label.lower() == "fire":
                                current_time = time.time()
                                last_time = last_fire_times.get(camera_name, 0)
                                
                                # Only respond if enough time has passed since last response
                                if current_time - last_time >= FIRE_RESPONSE_COOLDOWN:
                                    last_fire_times[camera_name] = current_time
                                    
                                    print(f"[AUTONOMOUS] Fire detected in {camera_name} camera (confidence: {prob:.1f}%)! Executing autonomous response...")
                                    
                                    # Execute autonomous response based on camera
                                    try:
                                        execute_camera_response(camera_name, motor_config)
                                    except Exception as e:
                                        print(f"[AUTONOMOUS] Error executing response for {camera_name}: {e}")
                                        import traceback
                                        traceback.print_exc()
                                    
                    except Exception as e:
                        print(f"[AUTONOMOUS] Error checking {camera_name}: {e}")
                        import traceback
                        traceback.print_exc()
                        pass
            
            time.sleep(1.0)  # Check every 1 second when enabled
            
        except Exception as e:
            print(f"[AUTONOMOUS] Error in autonomous mode worker: {e}")
            time.sleep(2.0)
