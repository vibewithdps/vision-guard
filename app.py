import os
# 🚀 SPEED FIX: Matplotlib Cache fix
os.environ['MPLCONFIGDIR'] = '/tmp/matplotlib'

import cv2
import numpy as np
import base64
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import hashlib
import gc # RAM Safai ke liye

app = Flask(__name__)
app.secret_key = 'bulletproof_key_v100'

# ================= CONFIGURATION =================
SENDER_EMAIL = "thakurdps795@gmail.com"
# ⚠️ PASSWORD YAHAN DALEIN
APP_PASSWORD = "akzw jzia itbv cmli" 
RECEIVER_EMAIL = "studydps18@gmail.com"

DB_NAME = "exam_system.db"
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, mobile TEXT, 
                  gender TEXT, role TEXT, password TEXT, photo_path TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY, user_email TEXT, alert_type TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- SAFE AI LOADING (CRASH ROKNE KE LIYE) ---
yolo_model = None
face_mesh = None

print("🚀 Starting AI Loading Sequence...")

# 1. Try Loading YOLO (Phone Detection)
try:
    from ultralytics import YOLO
    # Load Nano model (Lightweight)
    yolo_model = YOLO("yolov8n.pt")
    print("✅ YOLO Loaded Successfully")
except Exception as e:
    print(f"⚠️ YOLO Failed (Phone detection disabled): {e}")
    yolo_model = None

# 2. Try Loading MediaPipe (Face Detection)
try:
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.2,
        min_tracking_confidence=0.2
    )
    print("✅ MediaPipe Loaded Successfully")
except Exception as e:
    print(f"⚠️ MediaPipe Failed (Face detection disabled): {e}")
    face_mesh = None
    # Fix for attribute error: Force reload if needed
    try:
        import mediapipe.python.solutions.face_mesh as mp_face_mesh
        face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1)
        print("✅ MediaPipe Loaded via Fallback")
    except: pass

# --- HELPER FUNCTIONS ---
def save_base64_image(data_str, filename):
    if not data_str: return None
    try:
        header, encoded = data_str.split(",", 1)
        data = base64.b64decode(encoded)
        path = os.path.join(UPLOAD_FOLDER, filename)
        with open(path, "wb") as f:
            f.write(data)
        return "/" + path 
    except: return None

def log_violation_db(email, alert):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        timestamp = datetime.now().strftime("%H:%M:%S")
        c.execute("SELECT timestamp FROM logs WHERE user_email=? ORDER BY id DESC LIMIT 1", (email,))
        last = c.fetchone()
        if not last or last[0] != timestamp:
            c.execute("INSERT INTO logs (user_email, alert_type, timestamp) VALUES (?, ?, ?)", 
                      (email, alert, timestamp))
            conn.commit()
            print(f"🛑 LOGGED: {alert}")
        conn.close()
    except: pass

# --- ROUTES ---
@app.route('/')
def home():
    session.clear()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        photo_path = save_base64_image(data['live_photo'], f"{data['email']}_profile.jpg")
        hashed_pwd = hashlib.sha256(data['password'].encode()).hexdigest()
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (full_name, email, mobile, gender, role, password, photo_path) VALUES (?,?,?,?,?,?,?)",
                      (data['full_name'], data['email'], data['mobile'], data['gender'], data['role'], hashed_pwd, photo_path))
            conn.commit()
            return jsonify({"status": "success", "message": "Registered! Login Now."})
        except:
            return jsonify({"status": "error", "message": "Email already exists!"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    hashed_pwd = hashlib.sha256(data['password'].encode()).hexdigest()
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=? AND password=?", (data['email'], hashed_pwd))
    user = c.fetchone()
    conn.close()
    if user:
        session['user_email'] = user[2]
        session['user_name'] = user[1]
        session['role'] = user[5]
        return jsonify({"status": "success", "redirect": "/admin" if user[5] == 'Admin' else "/exam"})
    else:
        return jsonify({"status": "error", "message": "Invalid Login"})

@app.route('/exam')
def exam_dashboard():
    if 'user_email' not in session: return redirect('/')
    return render_template('exam.html', name=session['user_name'], email=session['user_email'])

@app.route('/admin')
def admin_panel():
    if session.get('role') != 'Admin': return "Access Denied"
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role='Student'")
    users = c.fetchall()
    c.execute("SELECT * FROM logs ORDER BY id DESC")
    logs = c.fetchall()
    conn.close()
    return render_template('admin.html', users=users, logs=logs)

# --- ROBUST DETECTION CORE ---
@app.route('/process_frame', methods=['POST'])
def process_frame():
    if 'user_email' not in session: return jsonify({"status": "error"})

    try:
        data = request.json['image']
        header, encoded = data.split(",", 1)
        binary = base64.b64decode(encoded)
        img_arr = np.frombuffer(binary, np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        
        # Super Small Resize (RAM Saving)
        frame = cv2.resize(frame, (240, 180))

        status = "Focused ✅"; color = "#28a745"; alert = ""

        # Face Logic
        if face_mesh:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb)
                if results.multi_face_landmarks:
                    nose_x = results.multi_face_landmarks[0].landmark[1].x
                    if nose_x < 0.2: alert = "Looking Right"
                    elif nose_x > 0.8: alert = "Looking Left"
                else: alert = "Face Missing"
            except: pass # Skip if MediaPipe glitches
        
        # YOLO Logic (Run only if RAM permits and no alert yet)
        if yolo_model and not alert:
            try:
                yolo_res = yolo_model(frame, verbose=False, classes=[67], conf=0.3)
                for r in yolo_res:
                    if len(r.boxes) > 0: alert = "Mobile Phone"
            except: pass # Skip if YOLO glitches

        if alert:
            status = f"⚠️ {alert.upper()}"; color = "#dc3545"
            log_violation_db(session['user_email'], alert)
        
        # Force Clean RAM
        gc.collect()

        return jsonify({"status": status, "color": color})
    except Exception as e:
        print(f"Frame Error: {e}")
        return jsonify({"status": "Active...", "color": "orange"})

@app.route('/record_tab_switch', methods=['POST'])
def record_tab_switch():
    log_violation_db(session['user_email'], "Tab Switched")
    return jsonify({"status": "recorded"})

# --- EMAIL ---
@app.route('/submit_exam', methods=['POST'])
def submit_exam():
    if 'user_email' not in session: return jsonify({"status": "error"})
    
    user_email = session['user_email']
    user_name = session['user_name']

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT alert_type, timestamp FROM logs WHERE user_email=?", (user_email,))
    logs = c.fetchall()
    conn.close()

    report_html = f"<h2>Report: {user_name}</h2><p>Email: {user_email}</p><hr><ul>"
    if not logs: report_html += "<li>✅ Clean Record</li>"
    else:
        for alert, time in logs: report_html += f"<li style='color:red'>[{time}] {alert}</li>"
    report_html += "</ul>"

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"Exam Report: {user_name}"
        msg.attach(MIMEText(report_html, 'html'))

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        
        return jsonify({"status": "success", "message": "Exam Submitted & Email Sent!"})

    except Exception as e:
        print(f"Email Error: {e}")
        return jsonify({"status": "success", "message": "Submitted (Email Failed)"})

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)