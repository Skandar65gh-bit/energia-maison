"""
EnergiaMaison — Module Reconnaissance Faciale v2.3
Améliorations :
  - Support CAP_DSHOW pour Windows (plus stable)
  - Integration Firebase (upload des visages)
  - Seuil de confiance plus flexible (80)
"""

import cv2
import os
import pickle
import firebase_admin
from firebase_admin import credentials, storage
import numpy as np
import time

# ── CONFIGURATION ───────────────────────────────────────────
KNOWN_FACES_DIR = "known_faces"
RECOGNIZER_FILE = "face_model.xml"
LABEL_MAP_FILE  = "label_map.pkl"
FACE_CASCADE    = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

# ── CONFIGURATION FIREBASE ───────────────────────────────────
# Placez votre fichier 'firebase-key.json' dans le dossier du projet
# et configurez votre bucket (ex: 'votre-projet.appspot.com')
FIREBASE_KEY = "firebase-key.json"
FIREBASE_BUCKET = "energiamaison.appspot.com" # EX: "energia-maison.appspot.com"

try:
    if os.path.exists(FIREBASE_KEY) and FIREBASE_BUCKET:
        cred = credentials.Certificate(FIREBASE_KEY)
        firebase_admin.initialize_app(cred, {'storageBucket': FIREBASE_BUCKET})
        print("[FIREBASE] Initialisé avec succès.")
    else:
        print("[FIREBASE] Non configuré (ou bucket manquant).")
except Exception as e:
    print(f"[FIREBASE] Erreur init: {e}")

os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

def check_opencv_contrib():
    if not hasattr(cv2, "face"):
        print("[FACE] Erreur : opencv-contrib-python n'est pas installé.")
        return False
    return True

def folder_to_email(folder: str) -> str:
    """ Convertit un nom de dossier (skandar_at_gmail_com) en email """
    return folder.replace("_at_", "@").replace("_", ".")

# ── PHASE 1 : Capture des photos ─────────────────────────────
def capture_face(email: str, n_photos: int = 30) -> bool:
    if not check_opencv_contrib(): return False

    folder   = email.replace("@", "_at_").replace(".", "_")
    user_dir = os.path.join(KNOWN_FACES_DIR, folder)
    os.makedirs(user_dir, exist_ok=True)

    # Nettoyage
    for f in os.listdir(user_dir):
        try: os.remove(os.path.join(user_dir, f))
        except: pass

    face_cascade = cv2.CascadeClassifier(FACE_CASCADE)
    
    # Essai webcam DSHOW (Windows) puis Standard
    cap = None
    for idx in [0, 1, 2]:
        print(f"[FACE] Essai caméra {idx} (DSHOW)...")
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened(): break
        cap.release()
    
    if not cap or not cap.isOpened():
        print("[FACE] DSHOW échoué, essai standard...")
        for idx in [0, 1, 2]:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened(): break
            cap.release()

    if not cap or not cap.isOpened():
        print("[FACE] Erreur : Aucune caméra accessible.")
        return False

    count = 0
    print(f"[FACE] Début capture pour {email}...")
    
    start_time = time.time()
    while count < n_photos:
        ret, frame = cap.read()
        if not ret: break
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        for (x, y, w, h) in faces:
            count += 1
            face_img = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            cv2.imwrite(os.path.join(user_dir, f"{count}.jpg"), face_img)
            cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
            cv2.putText(frame, f"Capture: {count}/{n_photos}", (x, y-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        cv2.imshow("Enregistrement Visage", frame)
        if cv2.waitKey(1) & 0xFF == ord('q') or (time.time() - start_time > 30):
            break

    cap.release()
    cv2.destroyAllWindows()
    return count >= 10

# ── PHASE 2 : Entraînement ───────────────────────────────────
def train_model(email: str = None) -> bool:
    if not check_opencv_contrib(): return False
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    faces, labels = [], []
    label_map = {}
    label_id = 0

    if not os.path.exists(KNOWN_FACES_DIR): return False

    for folder in os.listdir(KNOWN_FACES_DIR):
        f_path = os.path.join(KNOWN_FACES_DIR, folder)
        if not os.path.isdir(f_path): continue
        
        imgs = 0
        for f_name in os.listdir(f_path):
            img = cv2.imread(os.path.join(f_path, f_name), cv2.IMREAD_GRAYSCALE)
            if img is None: continue
            faces.append(cv2.resize(img, (200, 200)))
            labels.append(label_id)
            imgs += 1
        
        if imgs > 0:
            label_map[label_id] = folder
            label_id += 1

    if not faces: return False
    recognizer.train(faces, np.array(labels))
    recognizer.save(RECOGNIZER_FILE)
    with open(LABEL_MAP_FILE, "wb") as f:
        pickle.dump(label_map, f)
    
    print(f"[TRAIN] Modèle sauvegardé ({label_id} utilisateurs).")
    if email:
        sync_faces_to_firebase(email)
    return True

def sync_faces_to_firebase(email: str):
    if not firebase_admin._apps or not FIREBASE_BUCKET: return
    folder = email.replace("@", "_at_").replace(".", "_")
    user_dir = os.path.join(KNOWN_FACES_DIR, folder)
    if not os.path.exists(user_dir): return
    
    print(f"[FIREBASE] Sync {email}...")
    try:
        bucket = storage.bucket()
        for f in os.listdir(user_dir):
            if f.endswith(".jpg"):
                blob = bucket.blob(f"faces/{folder}/{f}")
                blob.upload_from_filename(os.path.join(user_dir, f))
        print("[FIREBASE] Sync terminée.")
    except Exception as e:
        print(f"[FIREBASE] Erreur sync: {e}")

# ── PHASE 3 : Reconnaissance ─────────────────────────────────
def recognize_face(timeout: int = 15):
    if not check_opencv_contrib(): return None
    if not os.path.exists(RECOGNIZER_FILE): return None

    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(RECOGNIZER_FILE)
    with open(LABEL_MAP_FILE, "rb") as f:
        label_map = pickle.load(f)

    face_cascade = cv2.CascadeClassifier(FACE_CASCADE)
    
    cap = None
    for idx in [0, 1, 2]:
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened(): break
        cap.release()
    if not cap or not cap.isOpened():
        for idx in [0, 1, 2]:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened(): break
            cap.release()

    if not cap or not cap.isOpened(): return None

    start = time.time()
    result = None
    
    while (time.time() - start) < timeout:
        ret, frame = cap.read()
        if not ret: break
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.2, 5)

        for (x, y, w, h) in faces:
            roi = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
            lbl, conf = recognizer.predict(roi)
            
            # Seuil de confiance : 80 (plus flexible)
            if conf < 80:
                result = label_map.get(lbl)
                color = (0, 255, 0)
                txt = f"OK ({int(conf)})"
            else:
                color = (0, 0, 255)
                txt = "Inconnu"
            
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
            cv2.putText(frame, txt, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.imshow("Connexion Visage", frame)
        if cv2.waitKey(1) & 0xFF == ord('q') or result: break

    cap.release()
    cv2.destroyAllWindows()
    return result