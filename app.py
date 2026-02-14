from flask import Flask, render_template, Response, request, jsonify
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
import time
import os
import base64
from datetime import datetime
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import platform 

app = Flask(__name__)

# ==========================================
# ⚙️ SETTINGS
# ==========================================
SENDER_EMAIL = "thakurdps795@gmail.com"
APP_PASSWORD = "tlqv tasd pjmo xviz"  # ⚠️ Yahan apna App Password wapas daal dena
RECEIVER_EMAIL = "studydps18@gmail.com"

CONFIDENCE_THRESHOLD = 0.5
PHONE_CLASS_ID = 67 # Cell phone class ID in COCO
LOG_FOLDER = "cheating_evidence"
AUDIO_THRESHOLD = 15.0 

if not os.path.exists(LOG_FOLDER): os.makedirs(LOG_FOLDER)

# --- GLOBAL VARS ---
audio_alert = False
student_details = {"name": "Unknown", "roll": "N/A"}

# --- AUDIO MOCK SETUP (Server Crash na ho isliye) ---
# Render par mic nahi hota, isliye ye Mock Class zaroori hai
try:
    import sounddevice as sd
except (OSError, ImportError):
    print("⚠️ Audio Device Error. Using Mock Audio.")
    class MockSD:
        def InputStream(self, *args, **kwargs): 
            class MockStream:
                def start(self): pass
                def stop(self): pass
                def close(self): pass
                def __enter__(self): return self
                def __exit__(self, *args): pass
            return MockStream()
    sd = MockSD()

# --- AUDIO THREAD (Server Side) ---
# Ye thread chalta rahega taaki purana logic break na ho
def audio_callback(indata, frames, time, status):
    global audio_alert
    try:
        volume = np.linalg.norm(indata) * 10
        if volume > AUDIO_THRESHOLD:
            audio_alert = True
        else:
            audio_alert = False
    except: pass

def start_audio_stream():
    try:
        with sd.InputStream(callback=audio_callback):
            while True: time.sleep(1)
    except Exception: pass

threading.Thread(target=start_audio_stream, daemon=True).start()

# --- AI SYSTEM CLASS (Modified for Render) ---
class VisionGuardSystem:
    def __init__(self):
        print("🚀 Loading AI Models...")
        # YOLO Load
        try:
            self.yolo_model = YOLO("yolov8n.pt") 
        except Exception as e:
            print(f"YOLO Error: {e}")
            self.yolo_model = None

        # MediaPipe Load
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        self.cheating_log = [] 
        self.last_log_time = datetime.now()

    def log_incident(self, reason):
        # Spam rokne ke liye: Agar pichle 3 second mein log kiya hai to wait karo
        current_time = datetime.now()
        ts_str = current_time.strftime("%H:%M:%S")
        
        if len(self.cheating_log) > 0:
            last_log = self.cheating_log[-1]
            if reason in last_log and (current_time - self.last_log_time).seconds < 3:
                return False
                
        self.cheating_log.append(f"[{ts_str}] {reason}")
        self.last_log_time = current_time
        print(f"📝 Logged: {reason}")
        return True

    # --- NEW: Function to process single frame from Frontend ---
    def process_single_frame(self, base64_image):
        global audio_alert
        try:
            # 1. Decode Image
            header, encoded = base64_image.split(",", 1)
            binary_data = base64.b64decode(encoded)
            np_arr = np.frombuffer(binary_data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            # 2. Setup Variables
            status_text = "Focused ✅"
            color = "#28a745" # Green
            alert_reason = ""

            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # 3. Gaze Tracking (MediaPipe)
            results = self.face_mesh.process(rgb_frame)
            
            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    nose_x = face_landmarks.landmark[1].x
                    nose_y = face_landmarks.landmark[1].y
                    
                    if nose_x < 0.20:
                        status_text = "Looking RIGHT ⚠️"
                        color = "#dc3545" # Red
                        alert_reason = "Looking Away (Right)"
                    elif nose_x > 0.80:
                        status_text = "Looking LEFT ⚠️"
                        color = "#dc3545" # Red
                        alert_reason = "Looking Away (Left)"
                    elif nose_y < 0.15: 
                         status_text = "Looking UP ⚠️"
                         color = "#dc3545" 
                         alert_reason = "Looking Up"
            else:
                status_text = "No Face Detected ⚠️"
                color = "#ffc107" # Yellow
                alert_reason = "Face Missing"

            # 4. Phone Detection (YOLO)
            # Optimization: Sirf tab check karo jab status normal ho (Speed badhane ke liye)
            if self.yolo_model and alert_reason == "":
                yolo_results = self.yolo_model(frame, verbose=False, classes=[67], conf=0.5)
                for r in yolo_results:
                    if len(r.boxes) > 0:
                        status_text = "PHONE DETECTED 📱"
                        color = "#dc3545"
                        alert_reason = "Mobile Phone Detected"

            # 5. Audio Alert (Server side variable check)
            if audio_alert:
                status_text = "NOISE DETECTED 🎤"
                color = "#dc3545"
                alert_reason = "High Volume / Talking"

            # 6. Logging
            if alert_reason:
                self.log_incident(alert_reason)

            return {"status": status_text, "color": color}

        except Exception as e:
            print(f"Processing Error: {e}")
            return {"status": "Error", "color": "gray"}

    def generate_report(self):
        body = f"""
        <h2>Exam Report: {student_details['name']}</h2>
        <p>Roll No: {student_details['roll']}</p>
        <h3>Incident Log:</h3>
        <ul>
        """
        for log in self.cheating_log:
            body += f"<li>{log}</li>"
        body += "</ul>"
        return body

system = VisionGuardSystem()

# --- ROUTES ---

@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/start_exam', methods=['POST'])
def start_exam():
    global student_details
    student_details['name'] = request.form.get('name')
    student_details['roll'] = request.form.get('roll')
    # Note: start_camera() hata diya kyunki Render par webcam nahi hota
    return render_template('exam.html', student=student_details)

# --- NEW ROUTE FOR RENDER (Replaces video_feed) ---
@app.route('/process_frame', methods=['POST'])
def process_frame():
    """Browser se aayi hui photo ko process karega"""
    try:
        json_data = request.json
        image_data = json_data.get('image')
        
        # Audio status from frontend (Optional)
        frontend_audio = json_data.get('audio_alert', False)
        if frontend_audio:
            system.log_incident("Noise Detected (Frontend)")

        result = system.process_single_frame(image_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/record_incident', methods=['POST'])
def record_incident():
    data = request.json
    incident_type = data.get('type', 'Unknown Violation')
    system.log_incident(incident_type)
    return jsonify({"status": "recorded"})

@app.route('/end_exam', methods=['POST'])
def end_exam():
    try:
        report = system.generate_report()
        
        # Email Logic Preserved
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"Exam Report: {student_details['name']}"
        msg.attach(MIMEText(report, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
        
        return jsonify({"status": "success", "message": "Exam Submitted & Report Sent!"})
    except Exception as e:
        print(f"Email Error: {e}")
        return jsonify({"status": "error", "message": "Report Generated but Email Failed (Check Password)"})

if __name__ == "__main__":
    # Render port automatically set karta hai environment variable se
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)