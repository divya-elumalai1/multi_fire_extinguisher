#include "esp_camera.h"
#include <WebServer.h>
#include <WiFi.h>
#include <esp32cam.h>
#include <ESPmDNS.h>
#include "esp_heap_caps.h"

// ================= WiFi =================
const char* WIFI_SSID = "fireextinguisher";
const char* WIFI_PASS = "fire12345678";

// ================= Server =================
WebServer server(81);

// ================= Resolutions =================
static auto loRes  = esp32cam::Resolution::find(320, 240);
static auto midRes = esp32cam::Resolution::find(640, 480);
static auto hiRes  = esp32cam::Resolution::find(800, 600);

// ================= Memory Debug =================
void printMemoryStats() {
  Serial.printf("Free heap: %u bytes\n", esp_get_free_heap_size());
  size_t psramFree  = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  size_t psramTotal = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
  if (psramTotal > 0) {
    Serial.printf("PSRAM total: %u bytes\n", psramTotal);
    Serial.printf("PSRAM free : %u bytes\n", psramFree);
  }
}

// ================= Single JPEG =================
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

// ================= JPEG Handlers =================
void handleJpgLo()  { esp32cam::Camera.changeResolution(loRes);  serveJpg(); }
void handleJpgMid() { esp32cam::Camera.changeResolution(midRes); serveJpg(); }
void handleJpgHi()  { esp32cam::Camera.changeResolution(hiRes);  serveJpg(); }

// ================= MJPEG STREAM =================
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

    //delay(40);  // ~25 FPS (stable)
    delay(80); // ~ 16FPS (more stable WiFi)
  }
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  Serial.println();

  using namespace esp32cam;

  // ---- Camera Config ----
  Config cfg;
  cfg.setPins(pins::AiThinker);
  cfg.setResolution(midRes);
  cfg.setBufferCount(1);
 // cfg.setJpeg(55);
  cfg.setJpeg(60); // smaller frames , less WiFi congestion
 
  if (!Camera.begin(cfg)) {
    Serial.println("CAMERA INIT FAILED");
    return;
  }
  Serial.println("CAMERA OK");

  // Orientation fix
  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 0);
  }

  printMemoryStats();

  // ---- WiFi ----
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // ---- mDNS ----
  if (MDNS.begin("firecamback")) {
    Serial.println("mDNS started: http://firecamback.local");
  }

  // ---- Routes ----
  server.on("/back/cam-lo.jpg",  handleJpgLo);
  server.on("/back/cam-mid.jpg", handleJpgMid);
  server.on("/back/cam-hi.jpg",  handleJpgHi);
  server.on("/back/stream", HTTP_GET, handleMjpegStream);

  server.begin();
  Serial.println("HTTP server started");

  Serial.println("Endpoints:"); 
  Serial.println("----live vieo MJPEG------");
  Serial.println("  http://firecamback.local/back/stream");     // live video MPEG
  Serial.println("----live vieo single frame ------");
  Serial.println("  http://firecamback.local/back/cam-mid.jpg"); // single Frame
  Serial.println("  http://firecamback.local/back/cam-mid.jpg");
  Serial.println("  http://firecamback.local/back/cam-mid.jpg");
}

// ================= LOOP =================
void loop() {
  server.handleClient();
}
