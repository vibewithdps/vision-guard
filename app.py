from flask import Flask, render_template, Response, request, jsonify
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
import time
import os
import socket
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
APP_PASSWORD = "rbwg hvip ojxb wabc"  # Apna App Password Dalein
RECEIVER_EMAIL = "studydps18@gmail.com"

CONFIDENCE_THRESHOLD = 0.5
PHONE_CLASS_ID = 67
LOG_FOLDER = "cheating_evidence"
# Audio threshold thoda badha diya taaki fan ki aawaz se trigger na ho
AUDIO_THRESHOLD = 15.0 
FRAME_SKIP = 3        
RESIZE_WIDTH = 640    

if not os.path.exists(LOG_FOLDER): os.makedirs(LOG_FOLDER)

# --- GLOBAL VARS ---
audio_alert = False
student_details = {"name": "Unknown", "roll": "N/A", "camera_type": "Laptop"}

# --- AUDIO MOCK SETUP (Server Crash na ho isliye) ---
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

# --- AUDIO THREAD ---
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

# --- AI SYSTEM CLASS ---
class VisionGuardSystem:
    def __init__(self):
        print("🚀 Loading AI Models...")
        self.yolo_model = YOLO("yolov8n.pt") 
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.cap = None 
        self.cheating_log = [] 
        
    def start_camera(self):
        if self.cap is not None: self.cap.release()
        if platform.system() == "Darwin":
            self.cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
        else:
            self.cap = cv2.VideoCapture(0)

    def log_incident(self, reason):
        # Spam rokne ke liye: Agar pichle 2 second mein log kiya hai to dobara mat karo
        current_time = datetime.now()
        ts_str = current_time.strftime("%H:%M:%S")
        
        # Check duplicate logs (Simple throttling)
        if len(self.cheating_log) > 0:
            last_log = self.cheating_log[-1]
            if reason in last_log and (current_time - self.last_log_time).seconds < 3:
                return False
                
        self.cheating_log.append(f"[{ts_str}] {reason}")
        self.last_log_time = current_time
        print(f"📝 Logged: {reason}")
        return True

    def generate_frames(self):
        global audio_alert
        self.last_log_time = datetime.now()
        
        while True:
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1); continue
            
            success, frame = self.cap.read()
            if not success: break
            
            # Mirror frame for user comfort
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            
            # --- 1. DETECT GAZE (IDHAR UDHAR DEKHNA) ---
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb_frame)
            
            status_text = "Status: Focused ✅"
            color = (0, 255, 0)
            
            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    # Nose Tip (Index 1) coordinates nikalo
                    nose_x = face_landmarks.landmark[1].x
                    nose_y = face_landmarks.landmark[1].y
                    
                    # Logic: Agar naak screen ke 20% left ya 80% right se bahar gayi
                    if nose_x < 0.20:
                        status_text = "WARNING: Looking RIGHT ⚠️"
                        color = (0, 0, 255)
                        self.log_incident("Looking Away (Right)")
                    elif nose_x > 0.80:
                        status_text = "WARNING: Looking LEFT ⚠️"
                        color = (0, 0, 255)
                        self.log_incident("Looking Away (Left)")
                    elif nose_y < 0.15: # Too high (Looking up)
                         status_text = "WARNING: Looking UP ⚠️"
                         color = (0, 0, 255)
                         self.log_incident("Looking Up")
            else:
                status_text = "WARNING: No Face Detected ⚠️"
                color = (0, 0, 255)
                # self.log_incident("Face Missing") # Optional

            # --- 2. AUDIO ALERT ---
            if audio_alert:
                cv2.putText(frame, "NOISE DETECTED 🎤", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                self.log_incident("High Volume / Talking")

            # --- 3. PHONE DETECTION (YOLO) ---
            # Har frame par YOLO mat chalao, heavy ho jayega. Har 5th frame par chalao
            # (Simplification for speed)
            
            cv2.putText(frame, status_text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            
            ret, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

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
    
    system.start_camera()
    return render_template('exam.html', student=student_details)

@app.route('/video_feed')
def video_feed():
    return Response(system.generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

# TAB SWITCH RECORD KARNE KE LIYE
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
        # Email logic same as before...
        return jsonify({"status": "success", "message": "Exam Submitted!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)