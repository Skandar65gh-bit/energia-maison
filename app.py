"""
EnergiaMaison — Backend Flask complet v2.2
Corrections :
  - Route GET "/" sert index.html directement
  - face/register retourne l'erreur exacte dans le status
  - Meilleure gestion des exceptions webcam
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import time
import threading
import os

app = Flask(__name__)
CORS(app)

sensor_data = {
    "temperature": 24.0,
    "humidity":    60.0,
    "timestamp":   time.time(),
    "source":      "simulation"
}

lights = {
    "salon":   {"name": "Salon",   "room": "Piece principale", "on": True,  "brightness": 80},
    "cuisine": {"name": "Cuisine", "room": "Zone repas",       "on": False, "brightness": 60},
    "chambre": {"name": "Chambre", "room": "Etage 1",          "on": False, "brightness": 40},
    "bureau":  {"name": "Bureau",  "room": "Teletravail",      "on": True,  "brightness": 100},
}

face_capture_status = {}  # email -> "en_cours"|"termine"|"erreur"
face_capture_error  = {}  # email -> message d'erreur detail


# ════════════════════════════════════════
# ROUTE PRINCIPALE — sert le HTML
# ════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ════════════════════════════════════════
# CAPTEURS ESP32
# ════════════════════════════════════════

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


# ════════════════════════════════════════
# LAMPES
# ════════════════════════════════════════

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


# ════════════════════════════════════════
# RECONNAISSANCE FACIALE
# ════════════════════════════════════════

@app.route("/api/face/register", methods=["POST"])
def face_register():
    body  = request.get_json(silent=True) or {}
    email = body.get("email", "").strip()
    print(f"[API] Requete face_register pour : {email}")

    if not email:
        return jsonify({"error": "email manquant"}), 400

    # Reset statut si precedente erreur
    if face_capture_status.get(email) in ("erreur", "termine", "inconnu"):
        face_capture_status.pop(email, None)
        face_capture_error.pop(email, None)

    if face_capture_status.get(email) == "en_cours":
        return jsonify({"status": "deja_en_cours"}), 200

    face_capture_status[email] = "en_cours"

    def run():
        try:
            from face_auth import capture_face, train_model
            ok = capture_face(email)
            if ok:
                trained = train_model(email)
                if trained:
                    face_capture_status[email] = "termine"
                    print(f"[FACE] Inscription terminee : {email}")
                else:
                    face_capture_status[email] = "erreur"
                    face_capture_error[email]  = "Entrainement modele echoue"
            else:
                face_capture_status[email] = "erreur"
                face_capture_error[email]  = "Capture insuffisante — verifiez eclairage et positionnement"
        except Exception as e:
            err_type = type(e).__name__
            face_capture_status[email] = "erreur"
            face_capture_error[email]  = f"[{err_type}] {str(e)}"
            print(f"[FACE] Erreur critique : {err_type} - {e}")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "capture_demarree", "email": email})


@app.route("/api/face/register/status", methods=["GET"])
def face_register_status():
    email  = request.args.get("email", "")
    status = face_capture_status.get(email, "inconnu")
    error  = face_capture_error.get(email, "")
    return jsonify({"email": email, "status": status, "error": error})


@app.route("/api/face/login", methods=["POST"])
def face_login():
    try:
        from face_auth import recognize_face, folder_to_email
        folder = recognize_face(timeout=15)
        if folder:
            email = folder_to_email(folder)
            print(f"[FACE] Connexion : {email} (folder={folder})")
            return jsonify({"status": "ok", "email": email, "folder": folder})
        return jsonify({"status": "non_reconnu"}), 401
    except Exception as e:
        print(f"[FACE] Erreur login : {e}")
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════
# STATUT
# ════════════════════════════════════════

@app.route("/api/status", methods=["GET"])
def status():
    age = time.time() - sensor_data["timestamp"] if sensor_data["timestamp"] else None
    return jsonify({
        "status":            "running",
        "esp32_connected":   age is not None and age < 30,
        "last_data_age_sec": round(age, 1) if age else None,
        "lights_on":         sum(1 for l in lights.values() if l["on"]),
        "total_watts":       sum(int(l["brightness"]*0.6) for l in lights.values() if l["on"]) + 80,
        "face_model_ready":  os.path.exists("face_model.xml"),
    })


# ════════════════════════════════════════
# DEMARRAGE
# ════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 55)
    print("  EnergiaMaison Backend v2.2")
    print("  http://localhost:5000  <-- ouvre cette URL")
    print()
    print("  ESP32  : POST http://<TON_IP>:5000/api/sensors")
    print("  Status : http://localhost:5000/api/status")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)