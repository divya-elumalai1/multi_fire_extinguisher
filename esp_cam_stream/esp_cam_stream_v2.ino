#include <WebServer.h>
#include <WiFi.h>
#include <esp32cam.h>
#include "esp_heap_caps.h"

const char* WIFI_SSID = "keto's lab";
const char* WIFI_PASS = "keto90666";

WebServer server(80);

// Use safe, standard resolutions
static auto loRes = esp32cam::Resolution::find(320, 240);  // QVGA
static auto midRes = esp32cam::Resolution::find(640, 480); // VGA
static auto hiRes = esp32cam::Resolution::find(800, 600);  // SXGA-lite

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

void serveJpg() {
  auto frame = esp32cam::capture();
  if (frame == nullptr) {
    Serial.println("CAPTURE FAIL - returning 503");
    printMemoryStats();
    server.send(503, "text/plain", "CAPTURE FAIL");
    delay(150);
    return;
  }

  Serial.printf("CAPTURE OK %dx%d %db\n",
                frame->getWidth(), frame->getHeight(), (int)frame->size());
  server.setContentLength(frame->size());
  server.send(200, "image/jpeg");
  WiFiClient client = server.client();
  frame->writeTo(client);
  delay(50);  // allow DMA to rest
}

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

void setup() {
  Serial.begin(115200);
  Serial.println();
  using namespace esp32cam;

  Config cfg;
  cfg.setPins(pins::AiThinker);

  // 🧠 Start conservatively — midRes is usually stable
  cfg.setResolution(midRes);
  cfg.setBufferCount(1);    // ✅ fewer buffers → less DRAM usage
  cfg.setJpeg(55);          // ✅ smaller JPEG = less DMA stress

  bool ok = Camera.begin(cfg);
  Serial.println(ok ? "CAMERA OK" : "CAMERA FAIL");

  printMemoryStats();

  // ---- WiFi connect ----
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  Serial.print("http://");
  Serial.println(WiFi.localIP());
  Serial.println("  /cam-lo.jpg");
  Serial.println("  /cam-mid.jpg");
  Serial.println("  /cam-hi.jpg");

  // ---- Route handlers ----
  server.on("/cam-lo.jpg", handleJpgLo);
  server.on("/cam-mid.jpg", handleJpgMid);
  server.on("/cam-hi.jpg", handleJpgHi);
  server.begin();
}

void loop() {
  server.handleClient();

  static unsigned long lastStats = 0;
  if (millis() - lastStats > 15000) {
    printMemoryStats();
    lastStats = millis();
  }
}