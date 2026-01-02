#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include <esp32cam.h>
#include <ESPmDNS.h>
#include "esp_heap_caps.h"

// ================= WIFI =================
const char* WIFI_SSID = "fireextinguisher";
const char* WIFI_PASS = "fire12345678";

// ================= SERVER =================
WebServer camServer(80);

// ================= RESOLUTIONS =================
static auto loRes  = esp32cam::Resolution::find(320, 240);
static auto midRes = esp32cam::Resolution::find(640, 480);
static auto hiRes  = esp32cam::Resolution::find(800, 600);

// ================= MEMORY =================
void printMemoryStats() {
  Serial.printf("Heap: %u | PSRAM free: %u\n",
    esp_get_free_heap_size(),
    heap_caps_get_free_size(MALLOC_CAP_SPIRAM)
  );
}

// ================= JPEG =================
void serveJpg() {
  auto frame = esp32cam::capture();
  if (!frame) {
    camServer.send(503, "text/plain", "CAPTURE FAIL");
    return;
  }
  camServer.setContentLength(frame->size());
  camServer.send(200, "image/jpeg");
  frame->writeTo(camServer.client());
}

void handleLo()  { esp32cam::Camera.changeResolution(loRes);  serveJpg(); }
void handleMid() { esp32cam::Camera.changeResolution(midRes); serveJpg(); }
void handleHi()  { esp32cam::Camera.changeResolution(hiRes);  serveJpg(); }

// ================= MJPEG STREAM =================
void handleMjpegStream() {
  WiFiClient client = camServer.client();

  client.println(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n\r\n"
  );

  while (client.connected()) {
    camServer.handleClient();
    yield();

    auto frame = esp32cam::capture();
    if (!frame) continue;

    client.printf(
      "--frame\r\n"
      "Content-Type: image/jpeg\r\n"
      "Content-Length: %u\r\n\r\n",
      frame->size()
    );

    frame->writeTo(client);
    client.print("\r\n");

    delay(60);
  }
}

// ================= MOTOR (HTTP) =================
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

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  Serial2.begin(9600, SERIAL_8N1, 3, 1);  // ESP32-CAM → Arduino
  delay(2000);

  using namespace esp32cam;

  Config cfg;
  cfg.setPins(pins::AiThinker);
  cfg.setResolution(midRes);
  cfg.setBufferCount(1);
  cfg.setJpeg(55);
  Camera.begin(cfg);

  sensor_t* s = esp_camera_sensor_get();
  if (s) {
    s->set_vflip(s, 1);
    s->set_hmirror(s, 0);
  }

  printMemoryStats();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected");
  Serial.println(WiFi.localIP());

  if (MDNS.begin("firecamfront")) {
    Serial.println("mDNS: http://firecamfront.local");
  }

  // ROUTES
  camServer.on("/front/cam-lo.jpg", handleLo);
  camServer.on("/front/cam-mid.jpg", handleMid);
  camServer.on("/front/cam-hi.jpg", handleHi);
  camServer.on("/front/stream", HTTP_GET, handleMjpegStream);
  camServer.on("/front/motor", HTTP_GET, handleMotor);

  camServer.begin();
  Serial.println("Camera server started");
}

// ================= LOOP =================
void loop() {
  camServer.handleClient();

  static unsigned long last = 0;
  if (millis() - last > 15000) {
    printMemoryStats();
    last = millis();
  }
}
