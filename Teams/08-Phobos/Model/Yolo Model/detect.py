import cv2
import numpy as np
import time

# ==============================
# CAMERA
# ==============================
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Camera not working")
    exit()

prev_time = 0

print("🔥 Universal Hole Detection Started")

# ==============================
# MAIN LOOP
# ==============================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Resize (optional for speed)
    frame = cv2.resize(frame, (800, 600))

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Blur
    blur = cv2.GaussianBlur(gray, (9, 9), 0)

    # Adaptive threshold (handles all lighting)
    thresh = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11, 2
    )

    # Morphology (clean noise)
    kernel = np.ones((5,5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        area = cv2.contourArea(cnt)

        # Ignore too small noise
        if area < 300:
            continue

        # Ignore too large (optional)
        if area > 50000:
            continue

        peri = cv2.arcLength(cnt, True)
        if peri == 0:
            continue

        circularity = 4 * np.pi * area / (peri * peri)

        # Key condition → ANY HOLE SHAPE
        if circularity > 0.2:   # flexible for all holes

            x, y, w, h = cv2.boundingRect(cnt)

            # Draw RED box
            cv2.rectangle(frame, (x,y), (x+w,y+h), (0,0,255), 2)

            cv2.putText(frame, "HOLE",
                        (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0,0,255), 2)

    # FPS
    current_time = time.time()
    fps = 1/(current_time-prev_time) if prev_time!=0 else 0
    prev_time = current_time

    cv2.putText(frame, f"FPS: {int(fps)}", (20,40),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,0), 2)

    cv2.imshow("UNIVERSAL HOLE DETECTION", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()