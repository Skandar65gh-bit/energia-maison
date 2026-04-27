"""
EnergiaMaison — Backend Flask pour ESP32
L'ESP32 envoie temp+humidité via HTTP POST toutes les 5s.
Flask stocke les données et les expose au frontend HTML.
 
Installation :
    pip install flask flask-cors
 
Lancement :
    python app.py
"""
 
from flask import Flask, jsonify, request
from flask_cors import CORS
import time
 
app = Flask(__name__)
CORS(app)
 
sensor_data = {
    "temperature": 0.0,
    "humidity": 0.0,
    "timestamp": 0,
    "source": "en attente de l'ESP32..."
}
 
lights = {
    "salon":   {"name": "Salon",   "room": "Pièce principale", "on": False, "brightness": 80},
    "cuisine": {"name": "Cuisine", "room": "Zone repas",       "on": False, "brightness": 60},
    "chambre": {"name": "Chambre", "room": "Étage 1",          "on": False, "brightness": 40},
    "bureau":  {"name": "Bureau",  "room": "Télétravail",      "on": False, "brightness": 100},
}
 
# L'ESP32 appelle : POST http://TON_IP_PC:5000/api/sensors
# Body JSON : {"temperature": 25.3, "humidity": 60.1}
@app.route("/api/sensors", methods=["POST"])
def receive_sensors():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "JSON invalide"}), 400
    sensor_data["temperature"] = round(float(body.get("temperature", 0)), 1)
    sensor_data["humidity"]    = round(float(body.get("humidity",    0)), 1)
    sensor_data["timestamp"]   = time.time()
    sensor_data["source"]      = "ESP32 DHT22"
    print(f"[ESP32] Temp={sensor_data['temperature']}C  Hum={sensor_data['humidity']}%")
    return jsonify({"status": "ok"}), 200
 
@app.route("/api/sensors", methods=["GET"])
def get_sensors():
    return jsonify(sensor_data)
 
@app.route("/api/lights", methods=["GET"])
def get_lights():
    return jsonify(lights)
 
@app.route("/api/lights/<light_id>", methods=["POST"])
def update_light(light_id):
    if light_id not in lights:
        return jsonify({"error": "Lampe introuvable"}), 404
    body = request.get_json(silent=True) or {}
    if "on"         in body: lights[light_id]["on"]         = bool(body["on"])
    if "brightness" in body: lights[light_id]["brightness"] = int(body["brightness"])
    print(f"[LAMPE] {light_id} => {'ON' if lights[light_id]['on'] else 'OFF'}")
    return jsonify({"status": "ok", "light": lights[light_id]})
 
@app.route("/api/status", methods=["GET"])
def status():
    age = time.time() - sensor_data["timestamp"] if sensor_data["timestamp"] else None
    return jsonify({
        "status": "running",
        "esp32_connected": age is not None and age < 30,
        "last_data_age_sec": round(age, 1) if age else None,
        "lights_on": sum(1 for l in lights.values() if l["on"]),
        "total_watts": sum(int(l["brightness"]*0.6) for l in lights.values() if l["on"]) + 80,
    })
 
if __name__ == "__main__":
    print("="*50)
    print("  EnergiaMaison Backend — http://0.0.0.0:5000")
    print("  ESP32 doit POST vers http://<TON_IP_PC>:5000/api/sensors")
    print("="*50)
    app.run(host="0.0.0.0", port=5000, debug=True)