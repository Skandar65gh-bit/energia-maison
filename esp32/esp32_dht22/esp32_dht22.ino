#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ── À MODIFIER ──────────────────────────────────
const char* WIFI_SSID     = "NOM_DE_TON_WIFI";
const char* WIFI_PASSWORD = "MOT_DE_PASSE_WIFI";
const char* SERVER_URL    = "http://192.168.1.85:5000/api/sensors";
// ────────────────────────────────────────────────

#define DHT_PIN  4
#define DHT_TYPE DHT22
DHT dht(DHT_PIN, DHT_TYPE);

void setup() {
  Serial.begin(115200);
  dht.begin();

  Serial.print("Connexion WiFi...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connecte !");
  Serial.print("IP ESP32 : ");
  Serial.println(WiFi.localIP());
}

void loop() {
  float temperature = dht.readTemperature();
  float humidity    = dht.readHumidity();

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("Erreur lecture DHT22 !");
    delay(5000);
    return;
  }

  Serial.printf("Temp=%.1fC  Hum=%.1f%%\n", temperature, humidity);

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(SERVER_URL);
    http.addHeader("Content-Type", "application/json");

    StaticJsonDocument<128> doc;
    doc["temperature"] = temperature;
    doc["humidity"]    = humidity;
    String body;
    serializeJson(doc, body);

    int httpCode = http.POST(body);
    if (httpCode == 200) {
      Serial.println("Envoye au serveur OK");
    } else {
      Serial.printf("Erreur HTTP : %d\n", httpCode);
    }
    http.end();
  }

  delay(5000);
}