# app.py — DivyaDrishti | Endurance Complete Solutions
# Detection: Bottom-Hat Transform + Canny Edge Segmentation
# Camera: Switch between Laptop Webcam and ESP32-S3 via dashboard

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"]  = "3"

import cv2, numpy as np, sqlite3, uuid
import threading, time, logging, requests, base64
from datetime import datetime
from flask import (Flask, Response, render_template,
                   jsonify, send_from_directory,
                   request, abort)
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(BASE_DIR, "magicaleye.log"),
            encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("DivyaDrishti")

# ── Camera source ─────────────────────────────────────────────
# Change this to switch source, OR use the dashboard toggle
# "laptop" = built-in/USB webcam
# "esp32"  = ESP32-S3 MJPEG stream
CAMERA_SOURCE = "esp32"   # "laptop" or "esp32"

ESP32_IP    = "10.188.204.38"
ESP32_PORT  = "81"
STREAM_PATH = "/stream"
STREAM_URL  = f"http://{ESP32_IP}:{ESP32_PORT}{STREAM_PATH}"

# Webcam index — try 0, 1, 2 if camera not found
WEBCAM_INDEX = 0

SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
DB_PATH      = os.path.join(BASE_DIR, "inspections.db")

# ── Supabase ──────────────────────────────────────────────────
SUPABASE_URL = "https://iforpjipnttkloetozbk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imlmb3JwamlwbnR0a2xvZXRvemJrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM3NTkzMTgsImV4cCI6MjA4OTMzNTMxOH0.RrqTym0f5DFIrRMrNjgWRWilKMtCH2TVVWAGY61ohd4"
BUCKET_NAME  = "inspections"

# ── App config ────────────────────────────────────────────────
CAMERA_MM       = 50.0
INSPECT_EVERY   = 3.0
STREAM_FPS      = 20
STREAM_QUALITY  = 40
SNAP_QUALITY    = 88
ALERT_THRESHOLD = 7
ALERT_COOLDOWN  = 120
PORT            = 5000

# ── ROI ───────────────────────────────────────────────────────
ROI_X1 = 0.05
ROI_X2 = 0.95
ROI_Y1 = 0.05
ROI_Y2 = 0.95

# ── Detection parameters ──────────────────────────────────────
# Laptop camera profile (more conservative — bad camera)
P_LAPTOP = {
    "blur_kernel":     11,
    "clahe_clip":      1.2,
    "clahe_tile":      8,
    "bottomhat_ksize": 31,
    "canny_low":       50,
    "canny_high":      130,
    "close_ksize":     9,
    "min_area":        1500,
    "max_area":        120_000,
    "min_circularity": 0.45,
    "min_solidity":    0.70,
    "level_low":       0.3,
    "level_medium":    1.5,
    "level_high":      4.0,
}

# ESP32-S3 profile (original sensitive settings — good camera)
P_ESP32 = {
    "blur_kernel":     7,
    "clahe_clip":      2.0,
    "clahe_tile":      8,
    "bottomhat_ksize": 21,
    "canny_low":       30,
    "canny_high":      90,
    "close_ksize":     9,
    "min_area":        500,
    "max_area":        120_000,
    "min_circularity": 0.30,
    "min_solidity":    0.55,
    "level_low":       0.3,
    "level_medium":    1.5,
    "level_high":      4.0,
}

os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# ── Supabase init ─────────────────────────────────────────────
supabase_ok = False
sb          = None

try:
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    sb.table("inspections").select("id").limit(1).execute()
    supabase_ok = True
    log.info("Supabase connected")
except Exception as e:
    log.warning(f"Supabase init failed: {e}")

def upload_supabase(part_id, result, n_defects,
                    severity, confidence, size_mm, frame):
    if not supabase_ok:
        return None
    try:
        _, buf = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        filename = f"{part_id}.jpg"
        sb.storage.from_(BUCKET_NAME).upload(
            path=filename, file=buf.tobytes(),
            file_options={"content-type": "image/jpeg",
                          "upsert": "true"})
        url = sb.storage.from_(BUCKET_NAME)\
                        .get_public_url(filename)
        sb.table("inspections").upsert({
            "part_id":    part_id,
            "timestamp":  datetime.now().isoformat(),
            "result":     result,
            "n_defects":  n_defects,
            "severity":   severity,
            "confidence": round(float(confidence), 3),
            "size_mm":    size_mm,
            "image_url":  url,
            "device":     "DivyaDrishti"
        }).execute()
        log.info(f"Supabase uploaded: {part_id}")
        return url
    except Exception as e:
        log.error(f"Supabase upload error: {e}")
        return None

def supabase_insert_alert(alert_type, message):
    if not supabase_ok:
        return
    try:
        sb.table("alerts").insert({
            "timestamp":  datetime.now().isoformat(),
            "alert_type": alert_type,
            "message":    message,
            "resolved":   0
        }).execute()
    except Exception as e:
        log.error(f"Supabase alert error: {e}")

# ── QR Code ───────────────────────────────────────────────────
def generate_qr_b64(part_id, result, timestamp, severity):
    try:
        import qrcode
        data = (f"DivyaDrishti Inspection\n"
                f"Part   : {part_id}\n"
                f"Result : {result}\n"
                f"Sev    : {severity}\n"
                f"Time   : {timestamp}\n"
                f"URL    : http://localhost:{PORT}/part/{part_id}")
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except ImportError:
        return ""
    except Exception as e:
        log.error(f"QR error: {e}")
        return ""

# ── SQLite ────────────────────────────────────────────────────
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn; conn.commit()
    except Exception as e:
        conn.rollback(); raise e
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS inspections (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id    TEXT NOT NULL,
                timestamp  TEXT NOT NULL,
                result     TEXT NOT NULL,
                n_defects  INTEGER DEFAULT 0,
                severity   TEXT DEFAULT '---',
                confidence REAL DEFAULT 0.0,
                size_mm    TEXT DEFAULT '---',
                image_file TEXT DEFAULT '',
                image_url  TEXT DEFAULT '',
                qr_code    TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                message    TEXT NOT NULL,
                resolved   INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_r ON inspections(result);
            CREATE INDEX IF NOT EXISTS idx_t ON inspections(timestamp DESC);
        """)
    log.info("Local DB ready")

def db_insert(part_id, result, n_defects, severity,
              confidence, size_mm, image_file,
              image_url="", qr_code=""):
    with get_db() as db:
        db.execute("""
            INSERT INTO inspections
            (part_id,timestamp,result,n_defects,
             severity,confidence,size_mm,
             image_file,image_url,qr_code)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (part_id,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              result, n_defects, severity,
              round(float(confidence), 3),
              size_mm, image_file, image_url, qr_code))

def db_update_url(part_id, url):
    with get_db() as db:
        db.execute(
            "UPDATE inspections SET image_url=? WHERE part_id=?",
            (url, part_id))

def db_insert_alert(alert_type, message):
    with get_db() as db:
        db.execute("""
            INSERT INTO alerts (timestamp,alert_type,message)
            VALUES(?,?,?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              alert_type, message))
    supabase_insert_alert(alert_type, message)

def db_get_inspections(limit=50, offset=0, rf=None, sf=None):
    with get_db() as db:
        where, params = [], []
        if rf in ("OK", "NOK"):
            where.append("result=?"); params.append(rf)
        if sf in ("LOW", "MEDIUM", "CRITICAL"):
            where.append("severity=?"); params.append(sf)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = db.execute(f"""
            SELECT * FROM inspections {clause}
            ORDER BY id DESC LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()
        return [dict(r) for r in rows]

def db_get_stats():
    with get_db() as db:
        r = db.execute("""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN result='OK'         THEN 1 ELSE 0 END) AS ok_count,
              SUM(CASE WHEN result='NOK'        THEN 1 ELSE 0 END) AS nok_count,
              SUM(CASE WHEN severity='CRITICAL' THEN 1 ELSE 0 END) AS critical,
              SUM(CASE WHEN severity='MEDIUM'   THEN 1 ELSE 0 END) AS medium,
              SUM(CASE WHEN severity='LOW'      THEN 1 ELSE 0 END) AS low_sev
            FROM inspections
        """).fetchone()
        d = dict(r)
        t = d["total"] or 1
        d["yield_pct"]   = round((d["ok_count"] or 0) / t * 100, 1)
        d["defect_rate"] = round((d["nok_count"] or 0) / t * 100, 1)
        trend = db.execute("""
            SELECT strftime('%H:00',timestamp) AS hour,
                   COUNT(*) AS total,
                   SUM(CASE WHEN result='NOK' THEN 1 ELSE 0 END) AS nok
            FROM inspections
            WHERE timestamp >= datetime('now','-12 hours')
            GROUP BY hour ORDER BY hour
        """).fetchall()
        d["trend"] = [dict(x) for x in trend]
        recent = db.execute("""
            SELECT result FROM inspections
            ORDER BY id DESC LIMIT 10
        """).fetchall()
        d["recent_nok"] = sum(
            1 for x in recent if x["result"] == "NOK")
        alerts = db.execute("""
            SELECT * FROM alerts WHERE resolved=0
            ORDER BY id DESC LIMIT 5
        """).fetchall()
        d["active_alerts"] = [dict(a) for a in alerts]
        curr = db.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN result='NOK' THEN 1 ELSE 0 END) AS nok
            FROM inspections
            WHERE timestamp >= datetime('now','-1 hours')
        """).fetchone()
        prev = db.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN result='NOK' THEN 1 ELSE 0 END) AS nok
            FROM inspections
            WHERE timestamp >= datetime('now','-2 hours')
              AND timestamp < datetime('now','-1 hours')
        """).fetchone()
        curr_rate = ((curr["nok"] or 0) /
                     max(curr["total"] or 1, 1) * 100)
        prev_rate = ((prev["nok"] or 0) /
                     max(prev["total"] or 1, 1) * 100)
        d["curr_hour_rate"] = round(curr_rate, 1)
        d["prev_hour_rate"] = round(prev_rate, 1)
        d["rate_change"]    = round(curr_rate - prev_rate, 1)
        return d

def db_total():
    with get_db() as db:
        return db.execute(
            "SELECT COUNT(*) FROM inspections").fetchone()[0]

def db_get_part(part_id):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM inspections WHERE part_id=?",
            (part_id,)).fetchone()
        return dict(row) if row else None

# ── Alert engine ──────────────────────────────────────────────
last_alert_time = 0

def check_trend_alert(recent_nok, rate_change):
    global last_alert_time
    now = time.time()
    if now - last_alert_time < ALERT_COOLDOWN:
        return
    if recent_nok >= ALERT_THRESHOLD:
        msg = (f"HIGH DEFECT RATE: {recent_nok}/10 recent "
               f"parts failed. Check machining tool immediately.")
        log.warning(f"ALERT: {msg}")
        db_insert_alert("HIGH_DEFECT_RATE", msg)
        last_alert_time = now
    elif rate_change >= 15:
        msg = (f"RISING DEFECT TREND: Rate increased "
               f"{rate_change:.1f}% vs last hour. "
               f"Possible tool wear detected.")
        log.warning(f"ALERT: {msg}")
        db_insert_alert("RISING_TREND", msg)
        last_alert_time = now

# ── ALL shared state ──────────────────────────────────────────
camera_frame  = None
camera_lock   = threading.Lock()
camera_ok     = False
current_url   = STREAM_URL
camera_source = CAMERA_SOURCE   # live-switchable

last_boxes  = []
last_scores = []
boxes_lock  = threading.Lock()
latest      = {"label": "--", "part_id": "--", "n_defects": 0,
               "severity": "---", "confidence": 0,
               "size_mm": "---", "timestamp": "--",
               "image_url": "", "qr_code": "",
               "camera_source": CAMERA_SOURCE}
latest_lock = threading.Lock()
last_infer  = 0

# ── Camera thread — handles BOTH sources ─────────────────────
def camera_thread():
    global camera_frame, camera_ok, current_url, camera_source
    cap = None   # holds webcam capture object

    while True:
        src = camera_source   # read current source (may change live)

        # ── LAPTOP WEBCAM ─────────────────────────────────────
        if src == "laptop":
            if cap is None:
                log.info(f"Opening webcam index {WEBCAM_INDEX}")
                cap = cv2.VideoCapture(WEBCAM_INDEX)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS,          30)
                cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
                # Force manual exposure for better metal detection
                cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
                cap.set(cv2.CAP_PROP_EXPOSURE,      -5)
                if not cap.isOpened():
                    log.error("Webcam not found. Change WEBCAM_INDEX.")
                    cap = None
                    time.sleep(3); continue
                camera_ok = True
                log.info("Laptop webcam connected!")

            ret, frame = cap.read()
            if not ret:
                log.warning("Webcam frame dropped")
                time.sleep(0.05); continue
            with camera_lock:
                camera_frame = frame

        # ── ESP32-S3 MJPEG STREAM ─────────────────────────────
        else:
            # Release webcam if it was open
            if cap is not None:
                cap.release(); cap = None
                log.info("Webcam released — switching to ESP32")

            log.info(f"Connecting ESP32: {current_url}")
            try:
                resp = requests.get(
                    current_url, stream=True, timeout=10)
                if resp.status_code != 200:
                    log.warning(f"ESP32 returned {resp.status_code}")
                    time.sleep(3); continue
                camera_ok = True
                log.info("ESP32-S3 connected!")
                buf = b""
                for chunk in resp.iter_content(chunk_size=8192):
                    # If source changed mid-stream, break out
                    if camera_source != "esp32":
                        break
                    buf += chunk
                    a = buf.find(b'\xff\xd8')
                    b = buf.find(b'\xff\xd9')
                    if a != -1 and b != -1:
                        jpg = buf[a:b+2]; buf = buf[b+2:]
                        img = cv2.imdecode(
                            np.frombuffer(jpg, dtype=np.uint8),
                            cv2.IMREAD_COLOR)
                        if img is not None:
                            with camera_lock:
                                camera_frame = img
                        if len(buf) > 65536:
                            buf = buf[-65536:]
            except requests.exceptions.ConnectionError:
                camera_ok = False
                log.warning("ESP32 lost. Retry 3s...")
                time.sleep(3)
            except Exception as e:
                camera_ok = False
                log.error(f"ESP32 camera: {e}")
                time.sleep(3)

# ── NMS ───────────────────────────────────────────────────────
def nms(boxes, scores, thresh):
    if not len(boxes): return []
    x1 = boxes[:, 0].astype(float); y1 = boxes[:, 1].astype(float)
    x2 = boxes[:, 2].astype(float); y2 = boxes[:, 3].astype(float)
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]; keep = []
    while order.size:
        i = order[0]; keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0., xx2 - xx1)
        h = np.maximum(0., yy2 - yy1)
        iou = (w * h) / (areas[i] + areas[order[1:]] - (w * h) + 1e-6)
        order = order[np.where(iou <= thresh)[0] + 1]
    return keep

# ── Bottom-Hat + Canny detection ─────────────────────────────
def detect_pores(frame):
    """
    Selects detection profile based on current camera source:
      laptop → P_LAPTOP  (conservative, handles bad camera)
      esp32  → P_ESP32   (sensitive, good camera)
    """
    p  = P_LAPTOP if camera_source == "laptop" else P_ESP32
    fh, fw = frame.shape[:2]

    # Crop to ROI
    rx1 = int(fw * ROI_X1); rx2 = int(fw * ROI_X2)
    ry1 = int(fh * ROI_Y1); ry2 = int(fh * ROI_Y2)
    roi  = frame[ry1:ry2, rx1:rx2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    rh, rw = gray.shape

    # CLAHE
    clahe    = cv2.createCLAHE(
        clipLimit=p["clahe_clip"],
        tileGridSize=(p["clahe_tile"], p["clahe_tile"]))
    enhanced = clahe.apply(gray)

    # Gaussian blur
    k       = p["blur_kernel"] | 1
    blurred = cv2.GaussianBlur(enhanced, (k, k), 0)

    # Channel A: Bottom-Hat
    bh_k      = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (p["bottomhat_ksize"], p["bottomhat_ksize"]))
    bottomhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, bh_k)
    bh_mean, bh_std = cv2.meanStdDev(bottomhat)
    bh_thresh = float(bh_mean[0][0]) + 1.5 * float(bh_std[0][0])
    bh_thresh = max(bh_thresh, 12)
    _, mask_bh = cv2.threshold(
        bottomhat, bh_thresh, 255, cv2.THRESH_BINARY)

    # Channel B: Canny + Close + Flood-fill
    edges  = cv2.Canny(blurred, p["canny_low"], p["canny_high"])
    ck     = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (p["close_ksize"], p["close_ksize"]))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, ck)
    flood  = closed.copy()
    fill   = np.zeros((rh + 2, rw + 2), np.uint8)
    cv2.floodFill(flood, fill, (0, 0), 255)
    mask_edge = cv2.bitwise_not(flood)

    # Combine + cleanup
    combined = cv2.bitwise_or(mask_bh, mask_edge)
    open_k   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    close_k  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    cleaned  = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  open_k)
    cleaned  = cv2.morphologyEx(cleaned,  cv2.MORPH_CLOSE, close_k)

    # Contour extraction + filters
    cnts, _ = cv2.findContours(
        cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    raw_boxes  = []
    raw_scores = []

    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if not (p["min_area"] <= area <= p["max_area"]):
            continue
        peri = cv2.arcLength(cnt, True)
        circ = (4 * np.pi * area / peri ** 2) if peri > 0 else 0
        if circ < p["min_circularity"]:
            continue
        hull     = cv2.convexHull(cnt)
        h_area   = cv2.contourArea(hull)
        solidity = area / h_area if h_area > 0 else 0
        if solidity < p["min_solidity"]:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        raw_boxes.append(np.array([
            x + rx1, y + ry1,
            x + rx1 + bw, y + ry1 + bh
        ], dtype=float))
        score = float(min(0.99, circ * 0.5 + solidity * 0.5 + 0.2))
        raw_scores.append(score)

    if not raw_boxes:
        return [], []

    boxes_np  = np.array(raw_boxes,  dtype=float)
    scores_np = np.array(raw_scores, dtype=float)
    keep      = nms(boxes_np, scores_np, 0.30)

    final_boxes  = []
    final_scores = []
    for i in keep:
        bx       = boxes_np[i]
        box_area = (bx[2] - bx[0]) * (bx[3] - bx[1])
        if box_area < fw * fh * 0.15:
            final_boxes.append(bx)
            final_scores.append(float(scores_np[i]))

    return final_boxes, final_scores

# ── Severity ──────────────────────────────────────────────────
def get_severity(box, h, w):
    a = (int(box[2]) - int(box[0])) * (int(box[3]) - int(box[1])) / (h * w)
    if a >= 0.04: return "CRITICAL", (0, 0,   220)
    if a >= 0.01: return "MEDIUM",   (0, 140, 255)
    return               "LOW",      (0, 220, 255)

# ── Draw boxes ────────────────────────────────────────────────
def draw_boxes(frame, boxes, scores):
    h, w = frame.shape[:2]
    for box, score in zip(boxes, scores):
        x1 = int(box[0]); y1 = int(box[1])
        x2 = int(box[2]); y2 = int(box[3])
        sev, color = get_severity(box, h, w)
        wm  = round((x2 - x1) * CAMERA_MM / w, 1)
        hm  = round((y2 - y1) * CAMERA_MM / h, 1)
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        txt = f"{sev} {float(score):.0%} {wm}x{hm}mm"
        (tw, th), _ = cv2.getTextSize(
            txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame,
            (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, txt, (x1 + 2, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame

# ── Inference loop ────────────────────────────────────────────
def inference_loop():
    global last_infer, latest, last_boxes, last_scores
    while True:
        time.sleep(0.1)
        if time.time() - last_infer < INSPECT_EVERY: continue
        with camera_lock:
            if camera_frame is None: continue
            frame = camera_frame.copy()
        last_infer = time.time()

        try:
            boxes, scores = detect_pores(frame)
        except Exception as e:
            log.error(f"Detection: {e}"); continue

        with boxes_lock:
            last_boxes  = boxes
            last_scores = scores

        n       = len(boxes)
        label   = "NOK" if n > 0 else "OK"
        part_id = str(uuid.uuid4())[:8].upper()
        h, w    = frame.shape[:2]
        ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sev, conf, size_mm = "---", 0., "---"
        if n > 0:
            scores_arr = [float(s) for s in scores]
            best       = int(np.argmax(scores_arr))
            sev, _     = get_severity(boxes[best], h, w)
            conf       = float(scores_arr[best])
            wm = round((boxes[best][2] - boxes[best][0]) * CAMERA_MM / w, 1)
            hm = round((boxes[best][3] - boxes[best][1]) * CAMERA_MM / h, 1)
            size_mm = f"{wm}x{hm}"

        qr_b64 = generate_qr_b64(part_id, label, ts, sev)

        ann = draw_boxes(frame.copy(), boxes, scores)
        fh2, fw2 = ann.shape[:2]
        rx1s = int(fw2 * ROI_X1); rx2s = int(fw2 * ROI_X2)
        ry1s = int(fh2 * ROI_Y1); ry2s = int(fh2 * ROI_Y2)
        cv2.rectangle(ann, (rx1s, ry1s), (rx2s, ry2s), (0, 180, 255), 1)
        clr = (0, 210, 0) if label == "OK" else (0, 0, 220)
        cv2.rectangle(ann, (0, 0), (w, 46), (10, 12, 20), -1)
        cv2.putText(ann, label, (10, 33),
            cv2.FONT_HERSHEY_SIMPLEX, 1.2, clr, 3)
        src_tag = "LAPTOP" if camera_source == "laptop" else "ESP32-S3"
        cv2.putText(ann,
            f"ID:{part_id}  {ts}  Defects:{n}  [{src_tag}]",
            (120, 25), cv2.FONT_HERSHEY_SIMPLEX,
            0.45, (160, 170, 180), 1)

        img_file = f"{part_id}.jpg"
        cv2.imwrite(
            os.path.join(SNAPSHOT_DIR, img_file),
            ann, [cv2.IMWRITE_JPEG_QUALITY, SNAP_QUALITY])

        db_insert(part_id, label, n, sev,
                  conf, size_mm, img_file, "", qr_b64)

        stats = db_get_stats()
        check_trend_alert(
            stats.get("recent_nok", 0),
            stats.get("rate_change", 0))

        with latest_lock:
            latest = {
                "label":         label,
                "part_id":       part_id,
                "n_defects":     n,
                "severity":      sev,
                "confidence":    round(conf, 3),
                "size_mm":       size_mm,
                "timestamp":     datetime.now().strftime("%H:%M:%S"),
                "image_url":     "",
                "qr_code":       qr_b64,
                "camera_source": camera_source
            }

        log.info(f"[{part_id}] {label} defects:{n} "
                 f"sev:{sev} src:{camera_source}")

        ann_copy = ann.copy()
        def bg_upload(pid, lbl, nd, sv, cf, sm, img):
            url = upload_supabase(pid, lbl, nd, sv, cf, sm, img)
            if url:
                db_update_url(pid, url)
                with latest_lock:
                    if latest["part_id"] == pid:
                        latest["image_url"] = url

        threading.Thread(
            target=bg_upload,
            args=(part_id, label, n, sev, conf, size_mm, ann_copy),
            daemon=True).start()

# ── MJPEG stream ──────────────────────────────────────────────
def gen_stream():
    interval  = 1.0 / STREAM_FPS
    prev_hash = None
    while True:
        t0 = time.time()
        with camera_lock:
            if camera_frame is None:
                time.sleep(0.02); continue
            frame = camera_frame.copy()

        frame_hash = hash(frame.tobytes()[::500])
        if frame_hash == prev_hash:
            time.sleep(max(0, interval - (time.time() - t0)))
            continue
        prev_hash = frame_hash

        with boxes_lock:
            boxes  = list(last_boxes)
            scores = list(last_scores)

        frame = draw_boxes(frame, boxes, scores)

        fh, fw = frame.shape[:2]
        rx1 = int(fw * ROI_X1); rx2 = int(fw * ROI_X2)
        ry1 = int(fh * ROI_Y1); ry2 = int(fh * ROI_Y2)
        cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (0, 180, 255), 1)
        cv2.putText(frame, "INSPECTION ZONE",
                    (rx1 + 4, ry1 + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 180, 255), 1)

        label = "NOK" if boxes else "OK"
        clr   = (0, 210, 0) if label == "OK" else (0, 0, 220)
        src_tag = "LAPTOP" if camera_source == "laptop" else "ESP32-S3"
        cv2.rectangle(frame, (0, fh - 28), (fw, fh), (10, 12, 20), -1)
        cv2.putText(frame, label, (8, fh - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, clr, 2)
        cv2.putText(frame, f"[{src_tag}]", (70, fh - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4,
            (0, 200, 255) if camera_source == "esp32" else (180, 180, 180), 1)
        ts = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, ts, (fw - 70, fh - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 130, 150), 1)

        _, buf = cv2.imencode(".jpg", frame, [
            cv2.IMWRITE_JPEG_QUALITY,  STREAM_QUALITY,
            cv2.IMWRITE_JPEG_OPTIMIZE, 1])
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n"
               + buf.tobytes() + b"\r\n")
        time.sleep(max(0, interval - (time.time() - t0)))

# ── Flask ─────────────────────────────────────────────────────
app = Flask(__name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"))

@app.route("/")
def index(): return render_template("index.html")

@app.route("/monitor")
def monitor(): return render_template("monitor.html")

@app.route("/analytics")
def analytics(): return render_template("analytics.html")

@app.route("/log")
def log_page(): return render_template("log.html")

@app.route("/alerts")
def alerts_page(): return render_template("alerts.html")

@app.route("/companies")
def companies_page(): return render_template("companies.html")

@app.route("/video_feed")
def video_feed():
    return Response(gen_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/stats")
def api_stats():
    return jsonify({"ok": True, "data": db_get_stats()})

@app.route("/api/latest")
def api_latest():
    with latest_lock:
        return jsonify({"ok": True, "data": latest})

@app.route("/api/inspections")
def api_inspections():
    limit  = request.args.get("limit",   50,  type=int)
    offset = request.args.get("offset",  0,   type=int)
    rf     = request.args.get("result",  None)
    sf     = request.args.get("severity", None)
    return jsonify({"ok": True,
                    "data": db_get_inspections(limit, offset, rf, sf),
                    "total": db_total(),
                    "limit": limit, "offset": offset})

@app.route("/api/inspections/<part_id>")
def api_detail(part_id):
    row = db_get_part(part_id)
    if not row: abort(404)
    return jsonify({"ok": True, "data": row})

@app.route("/part/<part_id>")
def part_page(part_id):
    row = db_get_part(part_id)
    if not row: abort(404)
    return render_template("index.html")

@app.route("/api/alerts")
def api_alerts():
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM alerts ORDER BY id DESC LIMIT 20
        """).fetchall()
        return jsonify({"ok": True,
                        "data": [dict(r) for r in rows]})

@app.route("/api/alerts/<int:alert_id>/resolve",
           methods=["POST"])
def resolve_alert(alert_id):
    with get_db() as db:
        db.execute(
            "UPDATE alerts SET resolved=1 WHERE id=?",
            (alert_id,))
    if supabase_ok:
        try:
            sb.table("alerts")\
              .update({"resolved": 1})\
              .eq("id", alert_id).execute()
        except Exception as e:
            log.error(f"Supabase resolve: {e}")
    return jsonify({"ok": True})

# ── Camera switch API ─────────────────────────────────────────
@app.route("/api/camera/source", methods=["POST"])
def set_camera_source():
    """
    Switch between laptop webcam and ESP32-S3 at runtime.
    POST body: {"source": "laptop"} or {"source": "esp32"}
    """
    global camera_source, camera_ok, camera_frame
    data = request.get_json()
    src  = data.get("source", "").lower()
    if src not in ("laptop", "esp32"):
        return jsonify({"ok": False,
                        "error": "source must be 'laptop' or 'esp32'"}), 400
    old = camera_source
    camera_source = src
    camera_ok     = False   # will re-check on next frame
    camera_frame  = None    # flush stale frame
    log.info(f"Camera source: {old} -> {src}")
    return jsonify({"ok": True, "source": src})

@app.route("/api/camera/source", methods=["GET"])
def get_camera_source():
    return jsonify({"ok": True, "source": camera_source,
                    "camera_ok": camera_ok})

# ── ESP32 IP config ───────────────────────────────────────────
@app.route("/api/esp32/config", methods=["POST"])
def update_esp32():
    global current_url, ESP32_IP
    data = request.get_json()
    if "ip" not in data:
        return jsonify({"ok": False, "error": "No IP"}), 400
    ESP32_IP    = data["ip"]
    current_url = f"http://{ESP32_IP}:{ESP32_PORT}{STREAM_PATH}"
    log.info(f"ESP32 IP updated: {ESP32_IP}")
    return jsonify({"ok": True, "ip": ESP32_IP,
                    "stream_url": current_url})

# ── Companies ─────────────────────────────────────────────────
COMPANIES = [
    {"id": "tata",     "name": "Tata Motors",        "color": "#1a56db"},
    {"id": "hero",     "name": "Hero MotoCorp",       "color": "#e02424"},
    {"id": "mahindra", "name": "Mahindra & Mahindra", "color": "#d03801"},
    {"id": "maruti",   "name": "Maruti Suzuki",       "color": "#057a55"},
    {"id": "bajaj",    "name": "Bajaj Auto",          "color": "#7e3af2"},
    {"id": "honda",    "name": "Honda India",         "color": "#c81e1e"},
]

def get_company_for_index(idx):
    return COMPANIES[idx % len(COMPANIES)]

@app.route("/api/company-inspections")
def api_company_inspections():
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM inspections
            ORDER BY id DESC LIMIT 120
        """).fetchall()
        data = [dict(r) for r in rows]
    for i, row in enumerate(data):
        co = get_company_for_index(i)
        row["company_id"]    = co["id"]
        row["company_name"]  = co["name"]
        row["company_color"] = co["color"]
    return jsonify({"ok": True, "data": data})

@app.route("/api/health")
def api_health():
    return jsonify({
        "ok":           True,
        "camera":       camera_ok,
        "camera_source": camera_source,
        "esp32_ip":     ESP32_IP,
        "supabase":     supabase_ok,
        "model":        "Bottom-Hat + Canny Edge",
        "uptime":       round(time.time() - start_time, 1)
    })

@app.route("/snapshots/<filename>")
def snapshot(filename):
    return send_from_directory(SNAPSHOT_DIR, filename)

@app.route("/api/frame")
def api_frame():
    with camera_lock:
        if camera_frame is None:
            return jsonify({"ok": False, "frame": None})
        frame = camera_frame.copy()
    with boxes_lock:
        boxes  = list(last_boxes)
        scores = list(last_scores)
    frame = draw_boxes(frame, boxes, scores)
    label = "NOK" if boxes else "OK"
    clr   = (0, 210, 0) if label == "OK" else (0, 0, 220)
    h, w  = frame.shape[:2]
    cv2.rectangle(frame, (0, h - 28), (w, h), (10, 12, 20), -1)
    cv2.putText(frame, label, (8, h - 8),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, clr, 2)
    _, buf = cv2.imencode(
        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    return jsonify({"ok": True, "frame": b64, "label": label,
                    "ts": datetime.now().strftime("%H:%M:%S")})

@app.errorhandler(404)
def e404(e): return jsonify({"ok": False, "error": "Not found"}), 404

@app.errorhandler(500)
def e500(e): return jsonify({"ok": False, "error": str(e)}), 500

# ── Start ─────────────────────────────────────────────────────
if __name__ == "__main__":
    start_time = time.time()
    init_db()
    threading.Thread(target=camera_thread,  daemon=True).start()
    threading.Thread(target=inference_loop, daemon=True).start()
    time.sleep(2)
    log.info(f"Dashboard      : http://localhost:{PORT}")
    log.info(f"Camera source  : {CAMERA_SOURCE.upper()}")
    log.info(f"ESP32 IP       : {ESP32_IP}")
    log.info(f"Detection      : Bottom-Hat + Canny Edge")
    log.info(f"Supabase       : {'connected' if supabase_ok else 'NOT configured'}")
    log.info(f"Switch camera  : POST /api/camera/source {{\"source\":\"laptop\"|\"esp32\"}}")
    app.run(host="0.0.0.0", port=PORT,
            threaded=True, use_reloader=False)