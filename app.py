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
import time

app = Flask(__name__)
app.secret_key = 'visionguard_final_key'

# ================= CONFIGURATION =================
SENDER_EMAIL = "thakurdps795@gmail.com"
APP_PASSWORD = "YOUR_APP_PASSWORD_HERE"  # ⚠️ Yahan Google App Password Dalein
RECEIVER_EMAIL = "studydps18@gmail.com"

DB_NAME = "visionguard_final.db" # ✅ FIXED NAME
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

# --- AI MODELS ---
print("🚀 Loading AI Models...")
try:
    yolo_model = YOLO("yolov8n.pt") 
    print("✅ YOLO Loaded")
except:
    yolo_model = None
    print("❌ YOLO Failed")

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.2, # 🔥 Aggressive Detection
    min_tracking_confidence=0.2
)

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
    except: return None

def log_violation_db(email, alert):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1 Second Anti-Spam (Thoda fast kiya)
        c.execute("SELECT timestamp FROM logs WHERE user_email=? ORDER BY id DESC LIMIT 1", (email,))
        last = c.fetchone()
        should_log = True
        if last:
            last_time = datetime.strptime(last[0], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_time).seconds < 1:
                should_log = False
        
        if should_log:
            c.execute("INSERT INTO logs (user_email, alert_type, timestamp) VALUES (?, ?, ?)", 
                      (email, alert, timestamp))
            conn.commit()
            print(f"🛑 SAVED TO DB: {alert} | {email}")
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

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
            return jsonify({"status": "success", "message": "Registered! Please Login."})
        except sqlite3.IntegrityError:
            return jsonify({"status": "error", "message": "Email already exists!"})
        finally:
            conn.close()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/login', methods=['POST'])
def login():
    try:
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
            if user[5] == 'Admin':
                return jsonify({"status": "success", "redirect": "/admin"})
            else:
                return jsonify({"status": "success", "redirect": "/exam"})
        else:
            return jsonify({"status": "error", "message": "Wrong Credentials"})
    except:
        return jsonify({"status": "error", "message": "Login Failed"})

@app.route('/exam')
def exam_dashboard():
    if 'user_email' not in session: return redirect('/')
    return render_template('exam.html', name=session['user_name'], email=session['user_email'])

@app.route('/admin')
def admin_panel():
    if 'user_email' not in session or session.get('role') != 'Admin':
        return "<h3>Access Denied! <a href='/'>Go Home</a></h3>"

    conn = sqlite3.connect(DB_NAME) # ✅ USING CORRECT DB
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role='Student'")
    users = c.fetchall()
    c.execute("SELECT * FROM logs ORDER BY id DESC")
    logs = c.fetchall()
    conn.close()
    return render_template('admin.html', users=users, logs=logs)

# ---------------- DETECTION LOGIC ----------------
@app.route('/process_frame', methods=['POST'])
def process_frame():
    if 'user_email' not in session: return jsonify({"status": "error"})

    try:
        data = request.json['image']
        header, encoded = data.split(",", 1)
        binary = base64.b64decode(encoded)
        img_arr = np.frombuffer(binary, np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

        # Resize for speed but keep it decent for YOLO
        frame = cv2.resize(frame, (320, 240))

        status = "Focused ✅"
        color = "#28a745"
        alert = ""

        # 1. Face & Gaze
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        
        if results.multi_face_landmarks:
            for face in results.multi_face_landmarks:
                nose_x = face.landmark[1].x
                # Sensitive Thresholds
                if nose_x < 0.2: alert = "Looking Right"
                elif nose_x > 0.8: alert = "Looking Left"
        else:
            alert = "Face Missing"

        # 2. YOLO (Independent Check) - Always runs if no face alert yet
        if yolo_model and not alert:
            yolo_res = yolo_model(frame, verbose=False, classes=[67], conf=0.3)
            for r in yolo_res:
                if len(r.boxes) > 0:
                    alert = "Mobile Phone"

        if alert:
            status = f"⚠️ {alert.upper()}"
            color = "#dc3545"
            log_violation_db(session['user_email'], alert)
        
        return jsonify({"status": status, "color": color})

    except:
        return jsonify({"status": "Checking...", "color": "orange"})

@app.route('/record_tab_switch', methods=['POST'])
def record_tab_switch():
    if 'user_email' in session:
        log_violation_db(session['user_email'], "Tab Switched")
    return jsonify({"status": "recorded"})

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

    # Generate Report
    report_html = f"<h2>Exam Report: {user_name}</h2><p>Email: {user_email}</p><hr><h3>Incidents:</h3><ul>"
    if not logs:
        report_html += "<li>✅ Clean Record</li>"
    else:
        for alert, time in logs:
            report_html += f"<li style='color:red'>[{time}] {alert}</li>"
    report_html += "</ul>"

    email_status = "Email Sent"
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"Exam Report: {user_name}"
        msg.attach(MIMEText(report_html, 'html'))

        s = smtplib.SMTP('smtp.gmail.com', 587)
        s.starttls()
        s.login(SENDER_EMAIL, APP_PASSWORD)
        s.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        s.quit()
        print(f"✅ Email sent to {RECEIVER_EMAIL}")
    except Exception as e:
        print(f"❌ Email Failed: {e}")
        email_status = f"Email Failed (Check Server Logs)"

    return jsonify({"status": "success", "message": f"Exam Submitted! {email_status}"})

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)