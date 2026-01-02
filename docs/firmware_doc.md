# Firmware Technical Implementation Documentation

## Table of Contents
1. [Overview](#overview)
2. [Hardware Requirements](#hardware-requirements)
3. [Code Structure](#code-structure)
4. [WiFi Configuration](#wifi-configuration)
5. [Camera Configuration](#camera-configuration)
6. [Server Architecture](#server-architecture)
7. [MJPEG Streaming](#mjpeg-streaming)
8. [Motor Control](#motor-control)
9. [Memory Management](#memory-management)
10. [mDNS Setup](#mdns-setup)
11. [API Endpoints](#api-endpoints)
12. [Troubleshooting](#troubleshooting)

---

## Overview

The firmware runs on ESP32-CAM modules and provides:
- Live MJPEG video streaming over HTTP
- Single JPEG frame capture endpoints
- Motor control interface (front camera only)
- mDNS hostname resolution
- Multiple resolution support

**Supported Cameras:**
- Front (`front.ino`) - Port 80, includes motor control
- Back (`back.ino`) - Port 81
- Left (`left.ino`) - Port 82
- Right (`right.ino`) - Port 83

**Framework:** Arduino/ESP32 with esp32cam library

---

## Hardware Requirements

### ESP32-CAM Module
- **Model:** AI-Thinker ESP32-CAM
- **Camera:** OV2640 (default)
- **Memory:** PSRAM recommended for better performance
- **WiFi:** 2.4GHz WiFi support

### Pin Configuration
Uses `pins::AiThinker` configuration from esp32cam library:
- Camera pins pre-configured for AI-Thinker board
- Serial2 pins (GPIO 3, 1) for motor control (front camera only)

### Power Requirements
- **Voltage:** 5V via USB or external power
- **Current:** ~200-300mA during operation
- **Stability:** Requires stable power supply for reliable streaming

---

## Code Structure

### File Organization

```
firmware/
├── front.ino    # Front camera (port 80, motor control)
├── back.ino     # Back camera (port 81)
├── left.ino     # Left camera (port 82)
└── right.ino    # Right camera (port 83)
```

### Common Structure

All firmware files follow the same structure:

1. **Includes and Libraries**
2. **WiFi Credentials**
3. **Server Declaration**
4. **Resolution Definitions**
5. **Memory Debug Functions**
6. **JPEG Handlers**
7. **MJPEG Stream Handler**
8. **Motor Handler** (front.ino only)
9. **Setup Function**
10. **Loop Function**

---

## WiFi Configuration

### Credentials

**Location:** Lines 8-10 in all firmware files

```cpp
const char* WIFI_SSID = "fireextinguisher";
const char* WIFI_PASS = "fire12345678";
```

### Connection Process

**Location:** `setup()` function, lines 103-114 (back.ino example)

```cpp
WiFi.mode(WIFI_STA);  // Station mode (client)
WiFi.begin(WIFI_SSID, WIFI_PASS);

Serial.print("Connecting to WiFi");
while (WiFi.status() != WL_CONNECTED) {
  delay(500);
  Serial.print(".");
}

Serial.println("\nWiFi connected");
Serial.print("IP Address: ");
Serial.println(WiFi.localIP());
```

**Behavior:**
- Connects in station mode (not access point)
- Blocks until connected
- Prints IP address on Serial monitor
- Timeout: None (infinite retry)

### Network Requirements

- **SSID:** Must match exactly (case-sensitive)
- **Password:** Must match exactly
- **Band:** 2.4GHz (ESP32 doesn't support 5GHz)
- **Security:** WPA/WPA2 supported

---

## Camera Configuration

### Initialization

**Location:** `setup()` function, lines 79-91 (back.ino example)

```cpp
using namespace esp32cam;

Config cfg;
cfg.setPins(pins::AiThinker);
cfg.setResolution(midRes);
cfg.setBufferCount(1);
cfg.setJpeg(60);  // JPEG quality

if (!Camera.begin(cfg)) {
  Serial.println("CAMERA INIT FAILED");
  return;
}
```

### Configuration Parameters

#### **Pins**
- `pins::AiThinker`: Pre-configured pin mapping for AI-Thinker ESP32-CAM
- Includes camera data pins, clock, reset, power, etc.

#### **Resolution**
Three resolutions defined:
```cpp
static auto loRes  = esp32cam::Resolution::find(320, 240);
static auto midRes = esp32cam::Resolution::find(640, 480);
static auto hiRes  = esp32cam::Resolution::find(800, 600);
```

**Default:** `midRes` (640x480)

**Usage:**
- Changed dynamically via endpoint handlers
- `handleJpgLo()`: Switches to 320x240
- `handleJpgMid()`: Switches to 640x480
- `handleJpgHi()`: Switches to 800x600

#### **Buffer Count**
- `cfg.setBufferCount(1)`: Single frame buffer
- Reduces memory usage
- May cause frame drops under high load

#### **JPEG Quality**
- **Front camera:** 55 (line 104 in front.ino)
- **Other cameras:** 60 (line 85 in back.ino, left.ino, right.ino)
- Range: 0-100 (higher = better quality, larger size)
- Lower quality reduces WiFi congestion

### Sensor Settings

**Location:** Lines 93-98 (back.ino example)

```cpp
sensor_t *s = esp_camera_sensor_get();
if (s) {
  s->set_vflip(s, 1);   // Vertical flip enabled
  s->set_hmirror(s, 0); // Horizontal mirror disabled
}
```

**Purpose:**
- Corrects camera orientation
- `vflip`: Flips image vertically (often needed for mounting)
- `hmirror`: Mirrors horizontally (disabled by default)

---

## Server Architecture

### WebServer Declaration

**Location:** Line 13 (back.ino example)

```cpp
WebServer server(81);  // Port number varies by camera
```

**Ports:**
- Front: 80
- Back: 81
- Left: 82
- Right: 83

### Server Initialization

**Location:** `setup()` function, line 127 (back.ino)

```cpp
server.begin();
Serial.println("HTTP server started");
```

### Request Handling

**Location:** `loop()` function, line 141 (back.ino)

```cpp
void loop() {
  server.handleClient();
}
```

**Behavior:**
- Non-blocking request handling
- Must be called frequently in loop()
- Processes one request per call

---

## MJPEG Streaming

### Stream Handler

**Location:** Lines 50-70 (back.ino example)

```cpp
void handleMjpegStream() {
  WiFiClient client = server.client();

  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  client.println();

  while (client.connected()) {
    auto frame = esp32cam::capture();
    if (!frame) continue;

    client.println("--frame");
    client.println("Content-Type: image/jpeg");
    client.printf("Content-Length: %d\r\n\r\n", frame->size());
    frame->writeTo(client);
    client.println();

    delay(80);  // ~12.5 FPS (1000ms / 80ms)
  }
}
```

### Protocol Details

**MJPEG Format:**
- Content-Type: `multipart/x-mixed-replace; boundary=frame`
- Each frame is a multipart section
- Boundary: `--frame`
- Headers: Content-Type and Content-Length per frame

**Frame Structure:**
```
--frame\r\n
Content-Type: image/jpeg\r\n
Content-Length: [size]\r\n\r\n
[JPEG bytes]
\r\n
```

### Frame Rate Control

**Delay Values:**
- **Back/Left/Right:** `delay(80)` → ~12.5 FPS
- **Front:** `delay(60)` → ~16.7 FPS (line 70 in front.ino)

**Calculation:**
- FPS = 1000ms / delay_ms
- 80ms delay = 12.5 FPS
- 60ms delay = 16.7 FPS

**Trade-offs:**
- Lower delay = higher FPS but more WiFi congestion
- Higher delay = lower FPS but more stable connection

### Stream Endpoints

**Routes:**
- Front: `/front/stream`
- Back: `/back/stream`
- Left: `/left/stream`
- Right: `/right/stream`

**Access:**
- Via mDNS: `http://firecamfront.local/front/stream`
- Via IP: `http://192.168.1.100/front/stream`

---

## Motor Control

### Implementation (Front Camera Only)

**Location:** Lines 74-90 in `front.ino`

```cpp
void handleMotor() {
  if (!camServer.hasArg("cmd")) {
    camServer.send(400, "text/plain", "Missing cmd");
    return;
  }

  char cmd = camServer.arg("cmd")[0];

  // Send to Arduino
  Serial2.write(cmd);

  Serial.print("MOTOR CMD: ");
  Serial.println(cmd);

  camServer.send(200, "text/plain", String("OK: ") + cmd);
}
```

### Serial Communication

**Configuration:** Line 95 in `front.ino`

```cpp
Serial2.begin(9600, SERIAL_8N1, 3, 1);  // ESP32-CAM → Arduino
```

**Parameters:**
- **Baud Rate:** 9600
- **Data Bits:** 8
- **Parity:** None
- **Stop Bits:** 1
- **RX Pin:** GPIO 3
- **TX Pin:** GPIO 1

### Endpoint

**Route:** `/front/motor`

**Usage:**
```
GET http://firecamfront.local/front/motor?cmd=0
```

**Parameters:**
- `cmd`: Single character command (e.g., "0", "1", "2")

**Response:**
- `200 OK`: Command sent successfully
- `400 Bad Request`: Missing cmd parameter

**Behavior:**
- Receives command via HTTP GET
- Forwards to Arduino via Serial2
- Returns confirmation

---

## Memory Management

### Memory Debug Function

**Location:** Lines 21-29 (back.ino example)

```cpp
void printMemoryStats() {
  Serial.printf("Free heap: %u bytes\n", esp_get_free_heap_size());
  size_t psramFree  = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  size_t psramTotal = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
  if (psramTotal > 0) {
    Serial.printf("PSRAM total: %u bytes\n", psramTotal);
    Serial.printf("PSRAM free : %u bytes\n", psramFree);
  }
}
```

### Memory Monitoring

**Location:** `loop()` function, lines 140-144 (back.ino)

```cpp
static unsigned long last = 0;
if (millis() - last > 15000) {
  printMemoryStats();
  last = millis();
}
```

**Frequency:** Every 15 seconds

**Purpose:**
- Monitor heap usage
- Detect memory leaks
- Verify PSRAM availability

### Memory Optimization

**Strategies:**
1. **Single Buffer:** `setBufferCount(1)` reduces memory
2. **JPEG Quality:** Lower quality = smaller frames = less memory
3. **Resolution:** Lower resolution = less memory per frame
4. **Frame Rate:** Lower FPS = less memory pressure

---

## mDNS Setup

### Initialization

**Location:** Lines 116-119 (back.ino example)

```cpp
if (MDNS.begin("firecamback")) {
  Serial.println("mDNS started: http://firecamback.local");
}
```

### Hostnames

**Camera-Specific:**
- Front: `firecamfront.local`
- Back: `firecamback.local`
- Left: `firecamleft.local`
- Right: `firecamright.local`

### Requirements

**Network:**
- Router must support mDNS/Bonjour
- Same network as client devices
- Firewall must allow mDNS traffic (port 5353 UDP)

**Client:**
- Windows: Requires Bonjour Print Services
- macOS: Built-in support
- Linux: Requires Avahi or similar

**Fallback:**
- If mDNS fails, use IP address directly
- IP printed to Serial monitor on startup

---

## API Endpoints

### Single JPEG Endpoints

**Routes:**
- Low Res: `/{camera}/cam-lo.jpg` (320x240)
- Mid Res: `/{camera}/cam-mid.jpg` (640x480)
- High Res: `/{camera}/cam-hi.jpg` (800x600)

**Examples:**
- `http://firecamfront.local/front/cam-mid.jpg`
- `http://firecamback.local/back/cam-lo.jpg`

**Handler Function:**
```cpp
void serveJpg() {
  auto frame = esp32cam::capture();
  if (!frame) {
    server.send(503, "text/plain", "CAPTURE FAIL");
    return;
  }
  server.setContentLength(frame->size());
  server.send(200, "image/jpeg");
  frame->writeTo(server.client());
}
```

**Behavior:**
- Captures single frame
- Returns JPEG image
- Sets Content-Length header
- Returns 503 if capture fails

### MJPEG Stream Endpoints

**Routes:**
- `/{camera}/stream`

**Examples:**
- `http://firecamfront.local/front/stream`
- `http://firecamback.local/back/stream`

**Content-Type:** `multipart/x-mixed-replace; boundary=frame`

**Behavior:**
- Continuous stream of JPEG frames
- Client must support MJPEG protocol
- Stream ends when client disconnects

### Motor Endpoint (Front Only)

**Route:** `/front/motor`

**Method:** GET

**Parameters:**
- `cmd`: Command character (required)

**Response:**
- `200 OK`: Command sent
- `400 Bad Request`: Missing parameter

---

## Route Registration

### Front Camera Routes

**Location:** Lines 126-130 in `front.ino`

```cpp
camServer.on("/front/cam-lo.jpg", handleLo);
camServer.on("/front/cam-mid.jpg", handleMid);
camServer.on("/front/cam-hi.jpg", handleHi);
camServer.on("/front/stream", HTTP_GET, handleMjpegStream);
camServer.on("/front/motor", HTTP_GET, handleMotor);
```

### Other Cameras Routes

**Location:** Lines 122-125 (back.ino example)

```cpp
server.on("/back/cam-lo.jpg",  handleJpgLo);
server.on("/back/cam-mid.jpg", handleJpgMid);
server.on("/back/cam-hi.jpg",  handleJpgHi);
server.on("/back/stream", HTTP_GET, handleMjpegStream);
```

**Pattern:**
- Replace `/back/` with `/{camera}/` for each camera
- Same handler functions (resolution-specific)

---

## Error Handling

### Camera Capture Failures

**Detection:**
```cpp
auto frame = esp32cam::capture();
if (!frame) continue;  // Skip frame, try next
```

**Behavior:**
- Skips failed frame
- Continues streaming
- No error response to client

### WiFi Connection Loss

**Detection:**
- `WiFi.status() != WL_CONNECTED` in loop
- Client disconnection in stream handler

**Recovery:**
- Automatic reconnection in `loop()` (if implemented)
- Stream handler exits when client disconnects

### Server Errors

**HTTP Errors:**
- `503 Service Unavailable`: Camera capture failed
- `400 Bad Request`: Missing required parameters

---

## Performance Considerations

### Frame Rate Optimization

**Factors:**
1. **Delay Value:** Primary control (60-80ms typical)
2. **JPEG Quality:** Lower = faster encoding
3. **Resolution:** Lower = faster capture
4. **WiFi Signal:** Stronger = faster transmission

### Memory Constraints

**Limitations:**
- Limited heap memory (~200KB free typically)
- PSRAM helps but not unlimited
- Single buffer reduces memory usage

**Best Practices:**
- Use single buffer (`setBufferCount(1)`)
- Moderate JPEG quality (55-60)
- Moderate resolution (640x480)
- Monitor memory stats

### Network Optimization

**Strategies:**
1. **Lower FPS:** Reduces bandwidth
2. **Lower Quality:** Smaller frames
3. **Lower Resolution:** Less data per frame
4. **Stable WiFi:** 5GHz router (ESP32 uses 2.4GHz)

---

## Uploading Firmware

### Arduino IDE Setup

**Required Libraries:**
- `esp32cam` by ESP32 Arduino
- `WebServer` (included with ESP32)
- `WiFi` (included with ESP32)
- `ESPmDNS` (included with ESP32)

**Board Settings:**
- Board: "ESP32 Wrover Module" or "AI Thinker ESP32-CAM"
- Upload Speed: 115200
- CPU Frequency: 240MHz
- Flash Frequency: 80MHz
- Flash Mode: QIO
- Flash Size: 4MB
- Partition Scheme: Default
- PSRAM: Enabled (if available)

### Upload Process

1. Connect ESP32-CAM via USB
2. Select correct board and port
3. Open firmware file (e.g., `front.ino`)
4. Update WiFi credentials if needed
5. Upload sketch
6. Open Serial Monitor (115200 baud)
7. Verify connection and IP address

### Serial Monitor

**Baud Rate:** 115200

**Expected Output:**
```
Connecting to WiFi.....
WiFi connected
IP Address: 192.168.1.100
mDNS started: http://firecamfront.local
HTTP server started
Endpoints:
  http://firecamfront.local/front/stream
  http://firecamfront.local/front/cam-mid.jpg
```

---

## Troubleshooting

### Camera Not Initializing

**Symptoms:**
- Serial shows "CAMERA INIT FAILED"
- No video stream

**Solutions:**
1. Check power supply (5V, stable)
2. Verify camera module connection
3. Check pin configuration matches board
4. Try different resolution
5. Restart ESP32

### WiFi Connection Issues

**Symptoms:**
- Stuck on "Connecting to WiFi"
- No IP address

**Solutions:**
1. Verify SSID and password (case-sensitive)
2. Check router is 2.4GHz (not 5GHz)
3. Check signal strength
4. Verify router allows new devices
5. Try static IP configuration

### mDNS Not Working

**Symptoms:**
- Can't access via `.local` hostname
- IP address works

**Solutions:**
1. Use IP address directly (printed to Serial)
2. Check router supports mDNS
3. Install Bonjour on Windows
4. Check firewall allows mDNS (port 5353)
5. Try different network

### Stream Disconnects Frequently

**Symptoms:**
- Stream works but disconnects often
- "NO SIGNAL" in viewer

**Solutions:**
1. Increase delay in stream handler (lower FPS)
2. Lower JPEG quality
3. Lower resolution
4. Improve WiFi signal strength
5. Reduce network congestion
6. Check power supply stability

### High Memory Usage

**Symptoms:**
- System crashes
- Memory stats show low free heap

**Solutions:**
1. Use single buffer (`setBufferCount(1)`)
2. Lower JPEG quality
3. Lower resolution
4. Reduce frame rate
5. Monitor memory stats regularly

### Motor Control Not Working (Front Camera)

**Symptoms:**
- Motor endpoint returns OK but motor doesn't move

**Solutions:**
1. Check Serial2 connection to Arduino
2. Verify baud rate matches (9600)
3. Check Arduino is receiving commands
4. Verify motor wiring
5. Test with Serial Monitor output

---

## Code Differences Between Cameras

### Front Camera (`front.ino`)

**Unique Features:**
- Motor control handler
- Serial2 initialization
- Port 80
- Slightly different delay (60ms vs 80ms)

### Other Cameras (`back.ino`, `left.ino`, `right.ino`)

**Common Features:**
- No motor control
- Ports 81, 82, 83 respectively
- Same delay (80ms)
- Same structure

**Differences:**
- Hostname in mDNS
- Route paths (`/back/`, `/left/`, `/right/`)
- Server port number

---

## Security Considerations

### Current Implementation

**Security Status:**
- No authentication
- No encryption
- Open HTTP (not HTTPS)
- WiFi password is only protection

### Recommendations

**For Production:**
1. Implement HTTP Basic Auth
2. Use HTTPS (requires certificate)
3. Restrict network access (firewall)
4. Change default WiFi credentials
5. Implement rate limiting

**Current Limitations:**
- Suitable for local network only
- Not recommended for internet exposure
- No protection against unauthorized access

---

## Future Enhancements

Potential improvements:
- OTA (Over-The-Air) updates
- Configuration via web interface
- Authentication system
- HTTPS support
- Advanced camera settings (exposure, white balance)
- Motion detection
- Local storage (SD card)
- Multiple stream quality options
- WebSocket support for control

---

## Dependencies

### Required Libraries

**ESP32 Core:**
- ESP32 Arduino Core (v2.0.0+)

**External Libraries:**
- `esp32cam` by ESP32 Arduino

**Built-in Libraries:**
- `WiFi`
- `WebServer`
- `ESPmDNS`
- `esp_camera.h` (ESP32 camera driver)

### Library Installation

**Arduino IDE:**
1. Tools → Manage Libraries
2. Search "esp32cam"
3. Install by ESP32 Arduino

**PlatformIO:**
```ini
lib_deps = 
    esp32cam
```

---

## Version Information

**Firmware Version:** 1.0
**Last Updated:** 2025
**ESP32 Core Version:** 2.0.0+
**esp32cam Library:** Latest

---

## Support and Maintenance

### Debugging Tips

1. **Serial Monitor:** Always check for error messages
2. **Memory Stats:** Monitor regularly for leaks
3. **Network Tools:** Use ping and telnet to test connectivity
4. **Browser DevTools:** Check network tab for HTTP errors

### Common Modifications

**Change WiFi Credentials:**
- Edit `WIFI_SSID` and `WIFI_PASS` constants

**Change Port:**
- Edit `WebServer server(PORT)` declaration

**Change Resolution:**
- Edit `cfg.setResolution()` in setup()

**Change Frame Rate:**
- Edit `delay()` value in stream handler

**Change JPEG Quality:**
- Edit `cfg.setJpeg()` value in setup()

---

## Conclusion

The firmware provides a robust foundation for multi-camera fire detection. Key strengths:
- Simple, maintainable code structure
- Efficient MJPEG streaming
- Flexible resolution options
- Reliable WiFi connectivity
- Memory-efficient operation

For production use, consider adding authentication, HTTPS, and OTA update capabilities.

