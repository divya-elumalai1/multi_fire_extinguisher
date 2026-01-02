Why MJPEG and how these scripts function

Goal
- Get images from an ESP32‑CAM to a laptop Python process for ML inference with minimal latency and simple integration.

Two acquisition strategies
1) Single-frame HTTP snapshots (pull one JPEG per request)
   - Python requests a single JPEG from an HTTP endpoint repeatedly.
   - Good for occasional frames or low-rate polling.

2) MJPEG stream (continuous multipart JPEG over HTTP)
   - One persistent HTTP connection delivers a sequence of JPEG frames.
   - Good for low-latency, real-time processing.

Why MJPEG for live streaming
- Low connection overhead: Keeps one HTTP connection open and pushes frames continuously (multipart/x-mixed-replace) instead of opening a new connection per frame.
- Simplicity: Each frame is a standard JPEG. Decoding is trivial with OpenCV/PIL; no special codecs.
- Robustness: If a frame is dropped or corrupted, the next one arrives independently (no inter-frame dependencies like H.264).
- ESP32-friendly: The ESP32‑CAM natively produces JPEG; serving MJPEG avoids heavy video encoders that exceed RAM/CPU constraints.

Trade-offs of MJPEG
- Higher bandwidth than inter-frame codecs, since every frame is a full JPEG.
- Latency and FPS still depend on Wi‑Fi quality and server loop rate.
- Best for live viewing/processing rather than archival video.

How the Arduino sketches relate
- The *.ino files configure the ESP32‑CAM, Wi‑Fi, and HTTP endpoints:
  - /right/cam-lo.jpg (or similar): returns a single JPEG snapshot per request.
  - /right/stream: returns an MJPEG stream (multipart JPEGs separated by boundaries).
- Variants like right_v2.ino (single-frame) and right_v3.ino (MJPEG) set up these endpoints and tune camera settings (resolution, quality) for latency vs. clarity.

mDNS/DNS rationale (firecam.local)
- The ESP32 does not handle repeated DNS/mDNS lookups efficiently under load.
- We resolve the hostname on the laptop once, then use the raw IP for all subsequent requests.
- This keeps the ESP32 work minimal and reduces latency spikes.

Python scripts in this folder

1) experiment/single_frame/refresh_cam.py (single-frame pull)
- Resolves IP once: ip = socket.gethostbyname("firecam.local").
- Builds a snapshot URL: http://<ip>/right/cam-lo.jpg.
- Loop: requests.get(url, timeout=1) -> cv2.imdecode -> cv2.imshow.
- Best when you want periodic snapshots, simpler error isolation, or reduced bandwidth.

2) experiment/mjpeg/refresh_cam2.py (MJPEG stream)
- Resolves IP once: ip = socket.gethostbyname("firecam.local").
- Builds a stream URL: http://<ip>/right/stream.
- Uses OpenCV VideoCapture(url) to read frames continuously and display them.
- Best when you want the freshest frames at low latency for real-time inference.

High-level ML integration
- Acquisition (single-frame or MJPEG) -> decode to numpy array (BGR/RGB) -> pre-process (resize/normalize) -> model inference (e.g., using trained_model.pth) -> post-process -> optional actions (e.g., email alert).
- For MJPEG, consider processing every Nth frame to manage CPU load while maintaining responsiveness.

Reliability and performance tips
- Timeouts/retries: Implement timeouts; if the stream drops, reconnect.
- Backpressure: For MJPEG, avoid large buffers; keep only the latest frame for real-time behavior.
- Camera tuning on ESP32: Lower resolution and moderate JPEG quality generally reduce latency and bandwidth.
- Network: Prefer strong Wi‑Fi signal; consider fixed IP or reliable mDNS resolution.

Quick usage
- Ensure the ESP32‑CAM is powered and connected; note the hostname firecam.local resolves from the laptop.
- Single-frame: run experiment/single_frame/refresh_cam.py to poll http://<ip>/right/cam-lo.jpg.
- MJPEG: run experiment/mjpeg/refresh_cam2.py to open http://<ip>/right/stream.

Summary
- Use single-frame when you only need occasional images or simple polling.
- Use MJPEG when you need continuous, low-latency frames suitable for live ML inference.
- Resolving firecam.local once on the laptop keeps the ESP32 load low and reduces latency spikes.