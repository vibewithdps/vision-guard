import os
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
import base64
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import hashlib

app = Flask(__name__)
app.secret_key = 'super_secret_key_visionguard'

# ================= CONFIGURATION =================
SENDER_EMAIL = "thakurdps795@gmail.com"
APP_PASSWORD = "tlqv tasd pjmo xviz"  # ⚠️ Apna password yahan dalein
RECEIVER_EMAIL = "studydps18@gmail.com"

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('exam_system.db')
    c = conn.cursor()
    # User Table (Photo path bhi save karega)
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, mobile TEXT, 
                  gender TEXT, password TEXT, photo_path TEXT)''')
    # Logs Table (Saari cheating yahan save hogi)
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY, user_email TEXT, alert_type TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- AI MODELS ---
try:
    yolo_model = YOLO("yolov8n.pt")
except:
    yolo_model = None

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)

# --- HELPER FUNCTIONS ---
def save_base64_image(data_str, filename):
    if not data_str: return None
    try:
        header, encoded = data_str.split(",", 1)
        data = base64.b64decode(encoded)
        path = os.path.join(UPLOAD_FOLDER, filename)
        with open(path, "wb") as f:
            f.write(data)
        return path
    except:
        return None

def log_violation_db(email, alert):
    """Har detection ko database mein save karega"""
    conn = sqlite3.connect('exam_system.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Spam check (Agar 3 sec pehle same alert tha toh mat likho)
    c.execute("SELECT timestamp FROM logs WHERE user_email=? ORDER BY id DESC LIMIT 1", (email,))
    last = c.fetchone()
    should_log = True
    if last:
        last_time = datetime.strptime(last[0], "%Y-%m-%d %H:%M:%S")
        if (datetime.now() - last_time).seconds < 2:
            should_log = False
    
    if should_log:
        c.execute("INSERT INTO logs (user_email, alert_type, timestamp) VALUES (?, ?, ?)", 
                  (email, alert, timestamp))
        conn.commit()
        print(f"💾 Saved to DB: {alert} for {email}")
    conn.close()

# --- ROUTES ---

@app.route('/')
def home():
    if 'user_email' in session:
        return redirect(url_for('exam_dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        # Photo save karna
        photo_filename = f"{data['email']}_profile.jpg"
        photo_path = save_base64_image(data['live_photo'], photo_filename)
        
        # Password Hash
        hashed_pwd = hashlib.sha256(data['password'].encode()).hexdigest()

        conn = sqlite3.connect('exam_system.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (full_name, email, mobile, gender, password, photo_path) VALUES (?,?,?,?,?,?)",
                      (data['full_name'], data['email'], data['mobile'], data['gender'], hashed_pwd, photo_path))
            conn.commit()
            status = "success"
            msg = "Registration Successful!"
        except sqlite3.IntegrityError:
            status = "error"
            msg = "Email already exists!"
        finally:
            conn.close()

        return jsonify({"status": status, "message": msg})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    hashed_pwd = hashlib.sha256(data['password'].encode()).hexdigest()

    conn = sqlite3.connect('exam_system.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=? AND password=?", (data['email'], hashed_pwd))
    user = c.fetchone()
    conn.close()

    if user:
        session['user_email'] = user[2]
        session['user_name'] = user[1]
        return jsonify({"status": "success", "redirect": "/exam"})
    else:
        return jsonify({"status": "error", "message": "Wrong Email or Password"})

@app.route('/exam')
def exam_dashboard():
    if 'user_email' not in session:
        return redirect('/')
    return render_template('exam.html', name=session['user_name'], email=session['user_email'])

@app.route('/process_frame', methods=['POST'])
def process_frame():
    if 'user_email' not in session: return jsonify({"status": "error"})

    try:
        data = request.json['image']
        header, encoded = data.split(",", 1)
        binary = base64.b64decode(encoded)
        img_arr = np.frombuffer(binary, np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

        status = "Focused ✅"
        color = "#28a745"
        alert = ""

        # AI Detection Logic
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        
        if results.multi_face_landmarks:
            for face in results.multi_face_landmarks:
                nose_x = face.landmark[1].x
                if nose_x < 0.2:
                    alert = "Looking Right"
                    status = "Looking RIGHT ⚠️"; color = "#dc3545"
                elif nose_x > 0.8:
                    alert = "Looking Left"
                    status = "Looking LEFT ⚠️"; color = "#dc3545"
        else:
            alert = "Face Missing"
            status = "No Face Detected ⚠️"; color = "#ffc107"

        if yolo_model and not alert:
            yolo_res = yolo_model(frame, verbose=False, classes=[67], conf=0.4)
            for r in yolo_res:
                if len(r.boxes) > 0:
                    alert = "Mobile Phone"
                    status = "PHONE DETECTED 📱"; color = "#dc3545"

        # 🛑 DATABASE SAVE (Yaha ho raha hai save)
        if alert:
            log_violation_db(session['user_email'], alert)

        return jsonify({"status": status, "color": color})
    except:
        return jsonify({"status": "error"})

@app.route('/record_tab_switch', methods=['POST'])
def record_tab_switch():
    if 'user_email' in session:
        log_violation_db(session['user_email'], "Tab Switched")
    return jsonify({"status": "recorded"})

@app.route('/submit_exam', methods=['POST'])
def submit_exam():
    if 'user_email' not in session: return jsonify({"status": "error"})
    
    # Email logic (Same as before)
    # ... (Email code yaha same rahega)
    
    session.clear()
    return jsonify({"status": "success", "message": "Exam Submitted!"})

# --- NEW: ADMIN PANEL ROUTE (Yahan dikhega data) ---
@app.route('/admin')
def admin_panel():
    conn = sqlite3.connect('exam_system.db')
    c = conn.cursor()
    
    # Get Users
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    
    # Get Logs
    c.execute("SELECT * FROM logs ORDER BY timestamp DESC")
    logs = c.fetchall()
    conn.close()
    
    return render_template('admin.html', users=users, logs=logs)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)