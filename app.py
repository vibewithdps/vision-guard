from flask import Flask, render_template, Response, request, jsonify
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
import time
import os
import socket  # IP nikalne ke liye
import base64  # Mobile frame decode karne ke liye
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
APP_PASSWORD = "rprx wpxo dbgf fevr"  # Apna password yahan rakho
RECEIVER_EMAIL = "studydps18@gmail.com"

CONFIDENCE_THRESHOLD = 0.5
PHONE_CLASS_ID = 67
LOG_FOLDER = "cheating_evidence"
AUDIO_THRESHOLD = 0.5
FRAME_SKIP = 3        
RESIZE_WIDTH = 640    

if not os.path.exists(LOG_FOLDER): os.makedirs(LOG_FOLDER)

# --- GLOBAL VARS ---
audio_alert = False
student_details = {"name": "Unknown", "roll": "N/A", "camera_type": "Laptop"}

# --- Is code ko 'import sounddevice as sd' ki jagah paste karein ---
try:
    import sounddevice as sd
except (OSError, ImportError):
    print("⚠️ Server par Audio Device nahi mila. Audio disabled.")
    # Ye ek Nakli (Dummy) Audio system hai taaki code crash na ho
    class MockSD:
        def query_devices(self, kind=None): return 0
        def rec(self, *args, **kwargs): pass
        def wait(self): pass
        def stop(self): pass
        def InputStream(self, *args, **kwargs): 
            class MockStream:
                def start(self): pass
                def stop(self): pass
                def close(self): pass
                def __enter__(self): return self
                def __exit__(self, *args): pass
            return MockStream()
            
    sd = MockSD()
# -------------------------------------------------------------------
# --- HELPER: GET LOCAL IP (QR Code ke liye) ---
def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Google DNS se connect karke apna IP pata karte hain
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# --- AUDIO THREAD ---
def audio_callback(indata, frames, time, status):
    global audio_alert
    try:
        volume = np.linalg.norm(indata) * 10
        audio_alert = volume > AUDIO_THRESHOLD
    except: pass

def start_audio_stream():
    try:
        with sd.InputStream(callback=audio_callback):
            while True: time.sleep(1)
    except Exception as e:
        print(f"❌ Audio Error: {e}")

threading.Thread(target=start_audio_stream, daemon=True).start()

# --- AI SYSTEM CLASS ---
class VisionGuardSystem:
    def __init__(self):
        print("🚀 Loading AI Models...")
        self.yolo_model = YOLO("yolov8n.pt") 
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(max_num_faces=2, refine_landmarks=True)
        self.cap = None 
        
        # Mobile Mode Vars
        self.mobile_mode = False
        self.latest_mobile_frame = None # Yahan mobile ka frame save hoga
        
        # Init vars
        self.last_capture_time = 0
        self.capture_delay = 3.0 
        self.frame_count = 0
        self.cheating_log = [] 
        self.cached_status = "System Ready"
        self.cached_color = (0, 255, 0)
        self.cached_boxes = []

    def start_camera(self, mode):
        # Reset Logic
        self.mobile_mode = False
        if self.cap is not None:
            self.cap.release()
            cv2.destroyAllWindows()
        
        print(f"🔄 Initializing Camera Mode: {mode}")
        
        if mode == "mobile":
            # Mobile ke liye hum capture object nahi banayenge, bas flag set karenge
            self.mobile_mode = True
            print("📱 Waiting for Mobile Camera Connection...")
        else:
            # Laptop Logic (Same as before)
            print("💻 Opening Laptop Webcam...")
            if platform.system() == "Darwin":
                self.cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
            else:
                self.cap = cv2.VideoCapture(0)

            if not self.cap.isOpened():
                print("❌ Camera Access Failed! Trying Index 1...")
                self.cap = cv2.VideoCapture(1)

    def update_mobile_frame(self, image_data):
        """ Mobile se jo image aayegi use decode karke yahan save karenge """
        try:
            # Base64 string ko clean karo
            header, encoded = image_data.split(",", 1)
            binary_data = base64.b64decode(encoded)
            image_array = np.frombuffer(binary_data, dtype=np.uint8)
            frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            self.latest_mobile_frame = frame
            return True
        except Exception as e:
            print(f"Mobile Frame Error: {e}")
            return False

    def log_incident(self, reason):
        if time.time() - self.last_capture_time > self.capture_delay:
            ts = datetime.now().strftime("%H:%M:%S")
            self.cheating_log.append(f"[{ts}] {reason}")
            print(f"📝 Logged: {reason}")
            return True
        return False

    def get_gaze_ratio(self, eye_points, landmarks):
        left = np.array([landmarks[eye_points[0]].x, landmarks[eye_points[0]].y])
        right = np.array([landmarks[eye_points[1]].x, landmarks[eye_points[1]].y])
        center = np.array([landmarks[eye_points[2]].x, landmarks[eye_points[2]].y])
        return np.linalg.norm(center - left) / np.linalg.norm(right - left)

    def generate_frames(self):
        global audio_alert
        while True:
            frame = None
            
            # --- INPUT SOURCE SELECTION ---
            if self.mobile_mode:
                # Agar mobile mode hai, to latest uploaded frame uthao
                if self.latest_mobile_frame is None:
                    # Loading screen
                    blank = np.zeros((480, 640, 3), np.uint8)
                    cv2.putText(blank, "Scan QR Code with Mobile...", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    ret, buffer = cv2.imencode('.jpg', blank)
                    yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                    time.sleep(0.5)
                    continue
                else:
                    frame = self.latest_mobile_frame.copy()
            else:
                # Laptop Mode
                if self.cap is None or not self.cap.isOpened():
                    time.sleep(1); continue
                success, img = self.cap.read()
                if not success: break
                frame = cv2.flip(img, 1)

            # --- PROCESS FRAME (AI LOGIC - SAME AS BEFORE) ---
            try:
                # Resize
                h, w = frame.shape[:2]
                aspect_ratio = w / h
                new_w = RESIZE_WIDTH
                new_h = int(new_w / aspect_ratio)
                frame = cv2.resize(frame, (new_w, new_h))
                
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                if self.frame_count % FRAME_SKIP == 0:
                    self.cached_boxes = []
                    status = "Secure"; color = (0, 255, 0); cheating = False; reason = ""

                    if audio_alert:
                        cheating = True; reason = "Talking / Noise"; status = "WARNING: Talking"; color = (0, 165, 255)

                    # 1. Phone Detection (YOLO)
                    try:
                        results = self.yolo_model(frame, stream=True, verbose=False, imgsz=320)
                        for result in results:
                            for box in result.boxes:
                                if int(box.cls[0]) == PHONE_CLASS_ID and float(box.conf[0]) > CONFIDENCE_THRESHOLD:
                                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                                    self.cached_boxes.append((x1, y1, x2, y2))
                                    cheating = True; reason = "Mobile Phone"; status = "WARNING: Phone"; color = (0, 0, 255)
                    except: pass

                    # 2. Face & Gaze
                    try:
                        face_results = self.face_mesh.process(rgb_frame)
                        if face_results.multi_face_landmarks:
                            if len(face_results.multi_face_landmarks) > 1:
                                cheating = True; reason = "Multiple Faces"; status = "WARNING: Multiple Faces"; color = (0, 0, 255)
                            
                            mesh_points = face_results.multi_face_landmarks[0].landmark
                            left_r = self.get_gaze_ratio([33, 133, 468], mesh_points)
                            right_r = self.get_gaze_ratio([362, 263, 473], mesh_points)
                            avg = (left_r + right_r) / 2
                            
                            if avg < 0.40: status = "Looking Left"; color = (0, 255, 255)
                            elif avg > 0.60: status = "Looking Right"; color = (0, 255, 255)
                        else:
                            cheating = True; reason = "No Face"; status = "WARNING: No Face"; color = (0, 0, 255)
                    except: pass

                    self.cached_status = status; self.cached_color = color
                    
                    if cheating:
                        if self.log_incident(reason):
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            try: cv2.imwrite(f"{LOG_FOLDER}/Alert_{ts}.jpg", frame)
                            except: pass
                            self.last_capture_time = time.time()

                # Drawing UI
                for (x1, y1, x2, y2) in self.cached_boxes:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.rectangle(frame, (0, 0), (new_w, 40), self.cached_color, -1)
                cv2.putText(frame, f"Status: {self.cached_status}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                self.frame_count += 1
                ret, buffer = cv2.imencode('.jpg', frame)
                yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

            except Exception as e:
                print(f"Frame Error: {e}")
                continue

    def generate_report(self):
        global student_details
        body = f"""<html><body><h2>🛡️ VisionGuard Report</h2>
        <p>Name: {student_details['name']} | Roll: {student_details['roll']}</p>
        <p>Mode: {student_details['camera_type']}</p>
        <p>Incidents: {len(self.cheating_log)}</p>
        <hr><ul>"""
        for log in self.cheating_log: body += f"<li>{log}</li>"
        body += "</ul></body></html>"
        return body

system = VisionGuardSystem()

# --- ROUTES ---

@app.route('/')
def login_page():
    # Ab hum koi IP ya QR code calculate nahi karenge
    # Seedha Login page dikhayenge sabko (Mobile aur Laptop dono ko)
    return render_template('login.html')

# --- app.py ke andar ye wala function update karo ---

@app.route('/start_exam', methods=['POST'])
def start_exam():
    global student_details
    name = request.form.get('name')
    roll = request.form.get('roll')
    mode = request.form.get('camera_mode') 

    student_details = {"name": name, "roll": roll, "camera_type": mode}
    
    # Camera Logic
    system.start_camera(mode)
    
    # 🟢 NEW: Mobile URL generate karo taaki QR code ban sake
    ip = get_ip_address()
    mobile_url = f"http://{ip}:5001/mobile_scanner"

    # 🟢 NEW: 'mobile_url' aur 'mode' ko template me bhejo
    return render_template('index.html', name=name, mobile_url=mobile_url, mode=mode)

# Ye naya route hai jo Mobile Phone khulega
@app.route('/mobile_scanner')
def mobile_scanner():
    return render_template('exam.html')

# Ye route Mobile se aayi hui photos receive karega
@app.route('/upload_frame', methods=['POST'])
def upload_frame():
    try:
        data = request.json['image']
        system.update_mobile_frame(data)
        return jsonify({"status": system.cached_status, "color": "red" if "WARNING" in system.cached_status else "green"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/video_feed')
def video_feed():
    return Response(system.generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/record_tab_switch', methods=['POST'])
def record_tab_switch():
    system.log_incident("Tab Switched")
    return jsonify({"status": "recorded"})

@app.route('/end_exam', methods=['POST'])
def end_exam():
    email_content = system.generate_report()
    try:
        msg = MIMEMultipart(); msg['From'] = SENDER_EMAIL; msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = f"Exam Report: {student_details['name']}"
        msg.attach(MIMEText(email_content, 'html'))
        s = smtplib.SMTP('smtp.gmail.com', 587); s.starttls(); s.login(SENDER_EMAIL, APP_PASSWORD)
        s.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string()); s.quit()
        return jsonify({"status": "success", "message": "Sent!"})
    except Exception as e: return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    ip = get_ip_address()
    print(f"✅ Server Started! Open Laptop at: http://{ip}:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)