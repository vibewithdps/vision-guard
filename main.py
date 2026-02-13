import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
import time
import os
from datetime import datetime

# --- CONFIGURATION ---
CONFIDENCE_THRESHOLD = 0.5
PHONE_CLASS_ID = 67   # COCO ID for cell phone
LOG_FOLDER = "cheating_evidence"

# Evidence folder banayein agar nahi hai
if not os.path.exists(LOG_FOLDER):
    os.makedirs(LOG_FOLDER)

class VisionGuard:
    def __init__(self):
        print("Initializing VisionGuard Systems...")
        
        # 1. Load Models
        print("- Loading YOLO model...")
        self.yolo_model = YOLO("yolov8n.pt") 
        
        print("- Loading Face Mesh...")
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=2,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )
        
        # 2. Camera Setup
        self.cap = cv2.VideoCapture(0)
        
        # 3. Screenshot Cooldown (Taaki spam na ho)
        self.last_capture_time = 0
        self.capture_delay = 2.0 # Har 2 second mein max ek photo

    def save_evidence(self, frame, reason):
        current_time = time.time()
        # Check agar 2 second ho gaye hain pichli photo se
        if current_time - self.last_capture_time > self.capture_delay:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{LOG_FOLDER}/Alert_{timestamp}_{reason}.jpg"
            cv2.imwrite(filename, frame)
            print(f"📸 EVIDENCE SAVED: {filename}")
            self.last_capture_time = current_time

    def get_gaze_ratio(self, eye_points, landmarks):
        left_corner = np.array([landmarks[eye_points[0]].x, landmarks[eye_points[0]].y])
        right_corner = np.array([landmarks[eye_points[1]].x, landmarks[eye_points[1]].y])
        iris_center = np.array([landmarks[eye_points[2]].x, landmarks[eye_points[2]].y])
        
        total_width = np.linalg.norm(right_corner - left_corner)
        dist_to_left = np.linalg.norm(iris_center - left_corner)
        return dist_to_left / total_width

    def run(self):
        print("VisionGuard Active. Press 'q' to exit.")
        
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret: break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, _ = frame.shape
            
            status = "Secure"
            color = (0, 255, 0)
            cheating_detected = False
            cheat_reason = ""

            # --- 1. PHONE DETECTION ---
            results = self.yolo_model(frame, stream=True, verbose=False)
            for result in results:
                for box in result.boxes:
                    if int(box.cls[0]) == PHONE_CLASS_ID and float(box.conf[0]) > CONFIDENCE_THRESHOLD:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        cv2.putText(frame, "PHONE", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                        cheating_detected = True
                        cheat_reason = "Phone"

            # --- 2. FACE ANALYSIS ---
            face_results = self.face_mesh.process(rgb_frame)
            
            if face_results.multi_face_landmarks:
                # Multiple Faces
                if len(face_results.multi_face_landmarks) > 1:
                    cheating_detected = True
                    cheat_reason = "Multiple_Faces"
                    cv2.putText(frame, "MULTIPLE FACES!", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

                # Gaze Tracking (On first face)
                mesh_points = face_results.multi_face_landmarks[0].landmark
                left_r = self.get_gaze_ratio([33, 133, 468], mesh_points)
                right_r = self.get_gaze_ratio([362, 263, 473], mesh_points)
                avg_ratio = (left_r + right_r) / 2
                
                if avg_ratio < 0.40:
                    status = "Looking Left"
                    color = (0, 255, 255) # Yellow warning
                elif avg_ratio > 0.60:
                    status = "Looking Right"
                    color = (0, 255, 255)
            else:
                cheating_detected = True
                cheat_reason = "No_Face"
                cv2.putText(frame, "NO FACE DETECTED", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

            # --- ACTION: SAVE PROOF ---
            if cheating_detected:
                status = f"WARNING: {cheat_reason}"
                color = (0, 0, 255)
                # Save screenshot
                self.save_evidence(frame, cheat_reason)

            # Draw Status Bar
            cv2.rectangle(frame, (0, 0), (w, 50), color, -1)
            cv2.putText(frame, f"Status: {status}", (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            cv2.imshow('VisionGuard Proctoring', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = VisionGuard()
    app.run()