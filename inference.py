import cv2
import numpy as np
import requests
from ultralytics import YOLO

# 1. Load the YOLO model
model = YOLO("best.pt")

# 2. THE URL - I have combined the parts so there are no typos
ip = "10.188.204.38"
port = "81"
stream_path = "/stream"
url = f"http://{ip}:{port}{stream_path}"

print(f"Targeting ESP32-CAM at: {url}")

try:
    # Open the connection
    print("Opening stream... (Press Ctrl+C in terminal or 'q' on image to stop)")
    r = requests.get(url, stream=True, timeout=10)
    
    if r.status_code == 200:
        print("CONNECTED SUCCESSFULLY!")
        bytes_data = b''
        
        # Process the incoming data chunks
        for chunk in r.iter_content(chunk_size=1024):
            bytes_data += chunk
            a = bytes_data.find(b'\xff\xd8') # JPEG Start
            b = bytes_data.find(b'\xff\xd9') # JPEG End
            
            if a != -1 and b != -1:
                jpg = bytes_data[a:b+2]
                bytes_data = bytes_data[b+2:]
                
                # Decode and Run YOLO
                img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is not None:
                    results = model(img, verbose=False)
                    cv2.imshow('YOLO LIVE FEED', results[0].plot())
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    else:
        print(f"Server reached but returned error code: {r.status_code}")

except Exception as e:
    print(f"CONNECTION ERROR: {e}")

cv2.destroyAllWindows()
