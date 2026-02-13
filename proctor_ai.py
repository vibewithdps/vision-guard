import cv2
import mediapipe as mp
import numpy as np
from ultralytics import YOLO
import math

class ProctoringSystem:
    def __init__(self):
        # 1. Load Face Mesh (Lightweight, runs on CPU)
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            min_detection_confidence=0.5, 
            min_tracking_confidence=0.5,
            refine_landmarks=True
        )
        
        # 2. Load YOLOv8 Nano (Smallest model for speed on Intel Mac)
        # It will auto-download 'yolov8n.pt' on first run
        self.yolo_model = YOLO("yolov8n.pt") 
        
        # Constants for Gaze/Head Pose
        self.alert_status = "Secure"
        self.alert_color = (0, 255, 0) # Green

    def get_head_pose(self, image, landmarks):
        # 3D Model points of a generic face
        img_h, img_w, _ = image.shape
        face_3d = []
        face_2d = []

        # Specific landmarks for head pose (Nose, Chin, Eyes, Mouth)
        key_landmarks = [33, 263, 1, 61, 291, 199]

        for idx, lm in enumerate(landmarks.landmark):
            if idx in key_landmarks:
                x, y = int(lm.x * img_w), int(lm.y * img_h)
                face_2d.append([x, y])
                face_3d.append([x, y, lm.z])

        face_2d = np.array(face_2d, dtype=np.float64)
        face_3d = np.array(face_3d, dtype=np.float64)

        # Camera matrix (Approximation)
        focal_length = 1 * img_w
        cam_matrix = np.array([[focal_length, 0, img_h / 2],
                               [0, focal_length, img_w / 2],
                               [0, 0, 1]])
        dist_matrix = np.zeros((4, 1), dtype=np.float64)

        # Solve PnP
        success, rot_vec, trans_vec = cv2.solvePnP(face_3d, face_2d, cam_matrix, dist_matrix)
        rmat, jac = cv2.Rodrigues(rot_vec)
        angles, mtxR, mtxQ, Q, x, y, z = cv2.RQDecomp3x3(rmat)

        # Return angles: x (pitch), y (yaw), z (roll)
        return angles[0] * 360, angles[1] * 360

    def process_frame(self, frame):
        # Flip for mirror effect
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img_h, img_w, _ = frame.shape
        
        self.alert_status = "Secure"
        self.alert_color = (0, 255, 0) # Green

        # --- STEP 1: Object Detection (Phone) ---
        # Run YOLO every frame might be slow on Intel Mac, so we accept a bit of lag
        # Filtering for class 67 (cell phone) in COCO dataset
        results = self.yolo_model(frame, stream=True, verbose=False, conf=0.4)
        
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls = int(box.cls[0])
                if cls == 67: # 67 is Cell Phone
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    cv2.putText(frame, "PHONE DETECTED", (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    self.alert_status = "Critical: Phone Detected"
                    self.alert_color = (0, 0, 255)

        # --- STEP 2: Face & Gaze Analysis ---
        results_mesh = self.face_mesh.process(rgb_frame)

        if results_mesh.multi_face_landmarks:
            if len(results_mesh.multi_face_landmarks) > 1:
                self.alert_status = "Multiple Faces Detected"
                self.alert_color = (0, 0, 255)
            
            for face_landmarks in results_mesh.multi_face_landmarks:
                # Calculate Head Pose
                pitch, yaw = self.get_head_pose(frame, face_landmarks)
                
                # Draw facial mesh (optional, looks cool)
                mp.solutions.drawing_utils.draw_landmarks(
                    image=frame,
                    landmark_list=face_landmarks,
                    connections=self.mp_face_mesh.FACEMESH_TESSELATION,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=mp.solutions.drawing_styles.get_default_face_mesh_tesselation_style()
                )

                # Check Looking Direction
                text = "Looking Center"
                if yaw < -10:
                    text = "Looking Right"
                    self.alert_status = "Suspicious: Looking Away"
                    self.alert_color = (0, 165, 255) # Orange
                elif yaw > 10:
                    text = "Looking Left"
                    self.alert_status = "Suspicious: Looking Away"
                    self.alert_color = (0, 165, 255)
                elif pitch < -10:
                    text = "Looking Down"
                    self.alert_status = "Suspicious: Looking Down"
                    self.alert_color = (0, 165, 255)

                # Display text on screen
                cv2.putText(frame, f"Head: {text}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        else:
            self.alert_status = "No Face Detected"
            self.alert_color = (0, 0, 255)

        # Overlay System Status
        cv2.rectangle(frame, (0, img_h-50), (img_w, img_h), self.alert_color, -1)
        cv2.putText(frame, f"STATUS: {self.alert_status}", (20, img_h-15), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        return frame, self.alert_status