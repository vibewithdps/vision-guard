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
app.secret_key = 'super_secret_key_visionguard'

# ================= CONFIGURATION =================
SENDER_EMAIL = "thakurdps795@gmail.com"
APP_PASSWORD = "tlqv tasd pjmo xviz"  # ⚠️ Password check kar lena
RECEIVER_EMAIL = "studydps18@gmail.com"

# RAM Management: Last processing time check
last_processed_time = 0

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('exam_system.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, mobile TEXT, 
                  gender TEXT, password TEXT, photo_path TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY, user_email TEXT, alert_type TEXT, timestamp TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- AI MODELS ---
print("⏳ Loading AI Models... (Please Wait)")
try:
    # YOLO ko CPU friendly mode mein load kar rahe hain
    yolo_model = YOLO("yolov8n.pt") 
    print("✅ YOLO Loaded")
except:
    yolo_model = None
    print("❌ YOLO Failed")

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.3,
    min_tracking_confidence=0.3
)

# --- HELPER FUNCTIONS ---
def log_violation_db(email, alert):
    try:
        conn = sqlite3.connect('exam_system.db')
        c = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 3 Second Anti-Spam
        c.execute("SELECT timestamp FROM logs WHERE user_email=? ORDER BY id DESC LIMIT 1", (email,))
        last = c.fetchone()
        should_log = True
        if last:
            last_time = datetime.strptime(last[0], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_time).seconds < 3:
                should_log = False
        
        if should_log:
            c.execute("INSERT INTO logs (user_email, alert_type, timestamp) VALUES (?, ?, ?)", 
                      (email, alert, timestamp))
            conn.commit()
            print(f"🛑 VIOLATION SAVED: {alert}")
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

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

# --- ROUTES ---

@app.route('/')
def home():
    # 🔥 FORCE LOGOUT: Jab bhi koi link khole, purana session clear karo
    session.clear()
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        photo_path = save_base64_image(data['live_photo'], f"{data['email']}_profile.jpg")
        hashed_pwd = hashlib.sha256(data['password'].encode()).hexdigest()

        conn = sqlite3.connect('exam_system.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (full_name, email, mobile, gender, password, photo_path) VALUES (?,?,?,?,?,?)",
                      (data['full_name'], data['email'], data['mobile'], data['gender'], hashed_pwd, photo_path))
            conn.commit()
            return jsonify({"status": "success", "message": "Registered Successfully!"})
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
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/exam')
def exam_dashboard():
    if 'user_email' not in session:
        return redirect('/')
    return render_template('exam.html', name=session['user_name'], email=session['user_email'])

@app.route('/admin')
def admin_panel():
    try:
        conn = sqlite3.connect('exam_system.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        users = c.fetchall()
        c.execute("SELECT * FROM logs ORDER BY timestamp DESC")
        logs = c.fetchall()
        conn.close()
        return render_template('admin.html', users=users, logs=logs)
    except:
        return "Database Error"

# ---------------- CORE AI LOGIC (OPTIMIZED) ----------------
@app.route('/process_frame', methods=['POST'])
def process_frame():
    global last_processed_time
    
    if 'user_email' not in session: return jsonify({"status": "error"})

    # ⏳ THROTTLING: Agar pichle 1 second mein check hua hai, to abhi mat karo (RAM Bachao)
    if time.time() - last_processed_time < 1.0:
        return jsonify({"status": "Skipped (Saving RAM)", "color": "#28a745"})

    try:
        last_processed_time = time.time()
        
        data = request.json['image']
        header, encoded = data.split(",", 1)
        binary = base64.b64decode(encoded)
        img_arr = np.frombuffer(binary, np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)

        # Frame Resize (Bahut Zaroori for Speed)
        frame = cv2.resize(frame, (320, 240))

        status = "Focused ✅"
        color = "#28a745"
        final_alert = ""

        # 1. Face & Gaze Detection
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        
        face_found = False
        if results.multi_face_landmarks:
            face_found = True
            for face in results.multi_face_landmarks:
                nose_x = face.landmark[1].x
                nose_y = face.landmark[1].y
                
                # Sensitivity Adjustment
                if nose_x < 0.30: final_alert = "Looking Right"
                elif nose_x > 0.70: final_alert = "Looking Left"
                elif nose_y < 0.15: final_alert = "Looking Up"
        else:
            final_alert = "Face Missing"

        # 2. YOLO Phone Detection (Sirf tab chalao agar koi aur alert nahi hai)
        if yolo_model and not final_alert:
            # conf=0.35 (Thoda sensitive)
            yolo_res = yolo_model(frame, verbose=False, classes=[67], conf=0.35)
            for r in yolo_res:
                if len(r.boxes) > 0:
                    final_alert = "Mobile Phone"

        # 3. Final Decision
        if final_alert:
            status = f"⚠️ {final_alert.upper()}"
            color = "#dc3545"
            log_violation_db(session['user_email'], final_alert)
        
        return jsonify({"status": status, "color": color})

    except Exception as e:
        print(f"Processing Error: {e}")
        return jsonify({"status": "Server Busy", "color": "orange"})

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

    conn = sqlite3.connect('exam_system.db')
    c = conn.cursor()
    c.execute("SELECT alert_type, timestamp FROM logs WHERE user_email=?", (user_email,))
    logs = c.fetchall()
    conn.close()

    report_html = f"<h2>Exam Report: {user_name}</h2><p>Email: {user_email}</p><hr><h3>Incidents:</h3><ul>"
    if not logs:
        report_html += "<li>✅ Clean Record</li>"
    else:
        for alert, time in logs:
            report_html += f"<li style='color:red'>[{time}] {alert}</li>"
    report_html += "</ul>"

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
    except Exception as e:
        print(f"Email Error: {e}")

    session.clear()
    return jsonify({"status": "success", "message": "Exam Submitted Successfully!"})

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)