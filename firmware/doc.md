All these sketches are pushed to the microcontroller using arduino ide.

## How to Push Firmware to Arduino

1. **Install Arduino IDE**: Download and install Arduino IDE from [arduino.cc](https://www.arduino.cc/en/software)

2. **Install Required Libraries**: 
   - All required libraries are included in the `libraries/` folder
   - Copy these libraries to your Arduino IDE libraries folder (usually `~/Documents/Arduino/libraries/`)

3. **Select Board and Port**:
   - For Arduino Uno: Go to `Tools > Board > Arduino AVR Boards > Arduino Uno`
   - For ESP32 cameras: Go to `Tools > Board > ESP32 Arduino > ESP32 Dev Module` (or your specific ESP32 board)
   - Select the correct COM port under `Tools > Port`

4. **Open and Upload Sketch**:
   - Open the desired `.ino` file (e.g., `motor_function.ino`, `front_camera.ino`)
   - Click the Upload button (→) or press `Ctrl+U` (Windows/Linux) / `Cmd+U` (Mac)
   - Wait for compilation and upload to complete

5. **Verify Upload**: Check the serial monitor (`Tools > Serial Monitor`) to confirm the device is running correctly

Library files included all the library


## System Architecture

### Arduino Uno - Motor Controller
The motor controller runs on Arduino Uno and receives serial commands from the ESP32 cameras. It controls:
- **Servo motor** (trolley open/close)
- **Mist system** (on/off)
- **DC motors** (movement: forward, backward, left, right, stop)

**Communication**: Receives commands via SoftwareSerial (A0/A1 pins) from ESP32-CAM

**Motor Commands**:
- `'1'` - Open servo (trolley)
- `'0'` - Close servo (trolley)
- `'2'` - Mist ON
- `'3'` - Mist OFF
- `'4'` - Motor ON
- `'5'` - Motor OFF
- `'6'` - Move forward
- `'7'` - Move backward
- `'8'` - Turn right
- `'9'` - Turn left
- `'p'` - Stop

### ESP32 Cameras

All cameras connect to WiFi network `fireextinguisher` and provide HTTP endpoints for video streaming and control.

#### Front Camera (Port 80)
- **mDNS**: `firecamfront.local`
- **Single Frame Endpoints**:
  - `http://firecamfront.local/front/cam-lo.jpg` - Low resolution (320x240) JPEG
  - `http://firecamfront.local/front/cam-mid.jpg` - Medium resolution (640x480) JPEG
  - `http://firecamfront.local/front/cam-hi.jpg` - High resolution (800x600) JPEG
- **Stream Endpoint**:
  - `http://firecamfront.local/front/stream` - MJPEG video stream
- **Motor Control Endpoint**:
  - `http://firecamfront.local/front/motor?cmd=<command>` - Send motor command to Arduino Uno
    - Example: `http://firecamfront.local/front/motor?cmd=6` (move forward)

#### Back Camera (Port 81)
- **mDNS**: `firecamback.local`
- **Single Frame Endpoints**:
  - `http://firecamback.local/back/cam-lo.jpg` - Low resolution (320x240) JPEG
  - `http://firecamback.local/back/cam-mid.jpg` - Medium resolution (640x480) JPEG
  - `http://firecamback.local/back/cam-hi.jpg` - High resolution (800x600) JPEG
- **Stream Endpoint**:
  - `http://firecamback.local/back/stream` - MJPEG video stream

#### Left Camera (Port 82)
- **mDNS**: `firecamleft.local`
- **Single Frame Endpoints**:
  - `http://firecamleft.local/left/cam-lo.jpg` - Low resolution (320x240) JPEG
  - `http://firecamleft.local/left/cam-mid.jpg` - Medium resolution (640x480) JPEG
  - `http://firecamleft.local/left/cam-hi.jpg` - High resolution (800x600) JPEG
- **Stream Endpoint**:
  - `http://firecamleft.local/left/stream` - MJPEG video stream

#### Right Camera (Port 83)
- **mDNS**: `firecamright.local`
- **Single Frame Endpoints**:
  - `http://firecamright.local/right/cam-lo.jpg` - Low resolution (320x240) JPEG
  - `http://firecamright.local/right/cam-mid.jpg` - Medium resolution (640x480) JPEG
  - `http://firecamright.local/right/cam-hi.jpg` - High resolution (800x600) JPEG
- **Stream Endpoint**:
  - `http://firecamright.local/right/stream` - MJPEG video stream