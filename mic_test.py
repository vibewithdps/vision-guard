import sounddevice as sd
import numpy as np

def callback(indata, frames, time, status):
    if status:
        print(status)
    # Volume calculate karein
    volume = np.linalg.norm(indata) * 10
    # Terminal mein volume print karein taaki hum dekh sakein
    print(f"Volume Level: {volume:.2f}")

print("🎤 Mic Testing... Kuch boliye ya taali bajayein!")
print("Stop karne ke liye Ctrl+C dabayein.")

# Stream start karein
with sd.InputStream(callback=callback):
    sd.sleep(100000)