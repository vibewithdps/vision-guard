# 🛡️ VisionGuard: AI Proctoring System

## 📌 Project Overview
VisionGuard is an automated AI-based proctoring system designed to monitor online exams. It uses Computer Vision and Audio Analysis to detect suspicious activities in real-time without human intervention.

## 🚀 Key Features
1.  **Mobile Phone Detection:** Uses YOLOv8 to detect phones in the frame.
2.  **Face & Gaze Tracking:** Detects if the student looks away (Left/Right) or if no face is present.
3.  **Multi-Person Detection:** Alerts if more than one person is seen.
4.  **Audio Monitoring:** Detects talking or background noise.
5.  **Auto-Reporting:** Generates an incident log and emails the report to the examiner automatically.

## 🛠️ Tech Stack
* **Language:** Python 3.11
* **Core Logic:** OpenCV, NumPy
* **AI Models:** YOLOv8 (Object Detection), MediaPipe (Face Mesh)
* **Web Framework:** Flask
* **Hardware:** Optimized for Mac (Intel/M1)

## ⚙️ How to Run
1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Run the application:
    ```bash
    python app.py
    ```
3.  Open browser at: `http://127.0.0.1:5001`

---
*Developed by DPS