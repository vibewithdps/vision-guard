import cv2
import torch
import ultralytics
import mediapipe as mp

print(f"OpenCV Version: {cv2.__version__}")
print(f"PyTorch Version: {torch.__version__}")
print(f"Ultralytics works! (YOLO ready)")
print("MediaPipe imported successfully!")

# Check if GPU is available (Optional)
if torch.cuda.is_available():
    print("CUDA is available. GPU will be used.")
elif torch.backends.mps.is_available():
    print("Apple Metal (MPS) is available.")
else:
    print("Running on CPU.")