import cv2

# Webcam open karein (0 usually default camera hota hai)
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Camera nahi khul raha hai.")
    exit()

print("Camera chalu hai! Band karne ke liye 'q' dabayein.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Frame receive nahi hua.")
        break

    # Frame ko show karein
    cv2.imshow('Visionguard Camera Test', frame)

    # 'q' dabane par band karein
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()