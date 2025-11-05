#include "esp_camera.h"  
#include <WebServer.h>
#include <WiFi.h>
#include <esp32cam.h>
#include <ESPmDNS.h>
#include "esp_heap_caps.h"

// ---------- WiFi Configuration ----------
const char* WIFI_SSID = "fireextinguisher";
const char* WIFI_PASS = "fire12345678";

// ---------- Static IP Setup (Change if needed) ----------
IPAddress local_IP(192, 168, 0, 50);  // <-- choose an unused IP in your network
IPAddress gateway(192, 168, 0, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns(8, 8, 8, 8);

WebServer server(80);

// ---------- Camera Resolutions ----------
static auto loRes = esp32cam::Resolution::find(320, 240);  // QVGA
static auto midRes = esp32cam::Resolution::find(640, 480); // VGA
static auto hiRes = esp32cam::Resolution::find(800, 600);  // SXGA-lite

// ---------- Utility: Print Memory Stats ----------
void printMemoryStats() {
  Serial.printf("Free heap: %u bytes\n", esp_get_free_heap_size());
  size_t psramFree = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
  size_t psramTotal = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
  if (psramTotal > 0) {
    Serial.printf("PSRAM total: %u bytes\n", psramTotal);
    Serial.printf("PSRAM free:  %u bytes\n", psramFree);
  } else {
    Serial.println("No PSRAM detected!");
  }
}

// ---------- Serve JPEG Frame ----------
void serveJpg() {
  auto frame = esp32cam::capture();
  if (frame == nullptr) {
    Serial.println("CAPTURE FAIL - returning 503");
    printMemoryStats();
    server.send(503, "text/plain", "CAPTURE FAIL");
    delay(150);
    return;
  }

  Serial.printf("CAPTURE OK %dx%d %db\n", frame->getWidth(), frame->getHeight(), (int)frame->size());
  server.setContentLength(frame->size());
  server.send(200, "image/jpeg");
  WiFiClient client = server.client();
  frame->writeTo(client);
  delay(50);  // allow DMA to rest
}

// ---------- Handlers for Different Resolutions ----------
void handleJpgLo() {
  if (!esp32cam::Camera.changeResolution(loRes))
    Serial.println("SET-LO-RES FAIL");
  serveJpg();
}

void handleJpgMid() {
  if (!esp32cam::Camera.changeResolution(midRes))
    Serial.println("SET-MID-RES FAIL");
  serveJpg();
}

void handleJpgHi() {
  if (!esp32cam::Camera.changeResolution(hiRes))
    Serial.println("SET-HI-RES FAIL");
  serveJpg();
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);
  Serial.println();
  using namespace esp32cam;

  // Camera Configuration
  Config cfg;
  cfg.setPins(pins::AiThinker);
  cfg.setResolution(midRes);  // start at medium resolution
  cfg.setBufferCount(1);      // lower buffers → lower DRAM use
  cfg.setJpeg(55);            // smaller JPEG = smoother capture

  bool ok = Camera.begin(cfg);
  Serial.println(ok ? "CAMERA OK" : "CAMERA FAIL");

  // --- Rotate the image (flip vertically / mirror horizontally) ---
  sensor_t *s = esp_camera_sensor_get();
  if (s) {
  s->set_vflip(s, 1);    // 1 = flip vertically (fix upside down)
  s->set_hmirror(s, 0);  // 1 = mirror horizontally, 0 = normal
  Serial.println("Camera orientation adjusted (VFLIP ON, HMIRROR OFF)");
  }



  printMemoryStats();

  // ---------- WiFi Connection ----------
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);

  if (!WiFi.config(local_IP, gateway, subnet, dns)) {
    Serial.println("STA Failed to configure static IP");
  }

  Serial.printf("Connecting to WiFi: %s\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long startAttemptTime = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttemptTime < 15000) {
    delay(300);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected!");
    Serial.print("Static IP: http://");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWiFi connection failed. Continuing without static IP...");
  }

  // ---------- mDNS (hostname access: http://esp32cam.local) ----------
  if (MDNS.begin("esp32cam")) {
    Serial.println("mDNS responder started: http://esp32cam.local");
  } else {
    Serial.println("mDNS failed to start.");
  }

  // ---------- Server Routes ----------
  server.on("/front/cam-lo.jpg", handleJpgLo);
  server.on("/front/cam-mid.jpg", handleJpgMid);
  server.on("/front/cam-hi.jpg", handleJpgHi);
  server.begin();

  Serial.println("HTTP server started.");
  Serial.println("Available URLs:");
  Serial.print("  http://");
  Serial.print(WiFi.localIP());
  Serial.println("/front/cam-lo.jpg");
  Serial.print("  http://");
  Serial.print(WiFi.localIP());
  Serial.println("/front/cam-mid.jpg");
  Serial.print("  http://");
  Serial.print(WiFi.localIP());
  Serial.println("/front/cam-hi.jpg");
  Serial.println("or use http://esp32cam.local/ if supported.");
}

// ---------- Loop ----------
void loop() {
  server.handleClient();

  static unsigned long lastStats = 0;
  if (millis() - lastStats > 15000) {
    printMemoryStats();
    lastStats = millis();
  }
}