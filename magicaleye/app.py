# app.py — MagicalEye | Endurance Complete Solutions
# Full features: QR codes, trend alerts, predictive maintenance,
# defect sizing, traceability, Supabase cloud

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

import tensorflow as tf
Interpreter = tf.lite.Interpreter

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
log = logging.getLogger("MagicalEye")

# ── Config ───────────────────────────────────────────────────
ESP32_IP    = "10.188.204.38"
ESP32_PORT  = "81"
STREAM_PATH = "/stream"
STREAM_URL  = f"http://{ESP32_IP}:{ESP32_PORT}{STREAM_PATH}"

MODEL_PATH   = os.path.join(BASE_DIR, "best.tflite")
SNAPSHOT_DIR = os.path.join(BASE_DIR, "snapshots")
DB_PATH      = os.path.join(BASE_DIR, "inspections.db")

# ── Supabase credentials ─────────────────────────────────────
SUPABASE_URL = "https://iforpjipnttkloetozbk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imlmb3JwamlwbnR0a2xvZXRvemJrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM3NTkzMTgsImV4cCI6MjA4OTMzNTMxOH0.RrqTym0f5DFIrRMrNjgWRWilKMtCH2TVVWAGY61ohd4"
BUCKET_NAME  = "inspections"

CONF_THRESH     = 0.55
IOU_THRESH      = 0.45
MAX_BOX_RATIO   = 0.25
CAMERA_MM       = 50.0
INSPECT_EVERY   = 3.0
STREAM_FPS      = 6
ALERT_THRESHOLD = 7
ALERT_COOLDOWN  = 120
PORT            = 5000

os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# ── Supabase ──────────────────────────────────────────────────
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
            file_options={"content-type":"image/jpeg",
                          "upsert":"true"})
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
            "device":     "MagicalEye-ESP32S3"
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
        data = (f"MagicalEye Inspection\n"
                f"Part   : {part_id}\n"
                f"Result : {result}\n"
                f"Sev    : {severity}\n"
                f"Time   : {timestamp}\n"
                f"URL    : http://localhost:{PORT}/part/{part_id}")
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(
            fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(
            buf.getvalue()).decode("utf-8")
    except ImportError:
        log.warning("qrcode not installed: pip install qrcode pillow")
        return ""
    except Exception as e:
        log.error(f"QR error: {e}")
        return ""

# ── Local SQLite ──────────────────────────────────────────────
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
            CREATE INDEX IF NOT EXISTS idx_r
                ON inspections(result);
            CREATE INDEX IF NOT EXISTS idx_t
                ON inspections(timestamp DESC);
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
            "UPDATE inspections SET image_url=? "
            "WHERE part_id=?", (url, part_id))

def db_insert_alert(alert_type, message):
    with get_db() as db:
        db.execute("""
            INSERT INTO alerts
            (timestamp,alert_type,message)
            VALUES(?,?,?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              alert_type, message))
    supabase_insert_alert(alert_type, message)

def db_get_inspections(limit=50, offset=0,
                       rf=None, sf=None):
    with get_db() as db:
        where, params = [], []
        if rf in ("OK","NOK"):
            where.append("result=?"); params.append(rf)
        if sf in ("LOW","MEDIUM","CRITICAL"):
            where.append("severity=?"); params.append(sf)
        clause = ("WHERE "+" AND ".join(where)) if where else ""
        rows = db.execute(f"""
            SELECT * FROM inspections {clause}
            ORDER BY id DESC LIMIT ? OFFSET ?
        """, params+[limit,offset]).fetchall()
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
        d["yield_pct"]   = round((d["ok_count"] or 0)/t*100,1)
        d["defect_rate"] = round((d["nok_count"] or 0)/t*100,1)

        # Hourly trend
        trend = db.execute("""
            SELECT strftime('%H:00',timestamp) AS hour,
                   COUNT(*) AS total,
                   SUM(CASE WHEN result='NOK'
                       THEN 1 ELSE 0 END) AS nok
            FROM inspections
            WHERE timestamp >= datetime('now','-12 hours')
            GROUP BY hour ORDER BY hour
        """).fetchall()
        d["trend"] = [dict(x) for x in trend]

        # Recent 10 for alert engine
        recent = db.execute("""
            SELECT result FROM inspections
            ORDER BY id DESC LIMIT 10
        """).fetchall()
        d["recent_nok"] = sum(
            1 for x in recent if x["result"]=="NOK")

        # Active alerts
        alerts = db.execute("""
            SELECT * FROM alerts WHERE resolved=0
            ORDER BY id DESC LIMIT 5
        """).fetchall()
        d["active_alerts"] = [dict(a) for a in alerts]

        # Predictive maintenance: defect rate last hour vs previous
        curr = db.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN result='NOK'
                       THEN 1 ELSE 0 END) AS nok
            FROM inspections
            WHERE timestamp >= datetime('now','-1 hours')
        """).fetchone()
        prev = db.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN result='NOK'
                       THEN 1 ELSE 0 END) AS nok
            FROM inspections
            WHERE timestamp >= datetime('now','-2 hours')
              AND timestamp <  datetime('now','-1 hours')
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

# ── Load TFLite ───────────────────────────────────────────────
log.info("Loading YOLO TFLite model...")
interpreter = Interpreter(model_path=MODEL_PATH)
interpreter.allocate_tensors()
inp_d      = interpreter.get_input_details()
out_d      = interpreter.get_output_details()
INPUT_SIZE = inp_d[0]["shape"][1]
model_lock = threading.Lock()
log.info(f"Model ready -- {INPUT_SIZE}x{INPUT_SIZE}")

# ── Camera ────────────────────────────────────────────────────
camera_frame = None
camera_lock  = threading.Lock()
camera_ok    = False
current_url  = STREAM_URL

def camera_thread():
    global camera_frame, camera_ok, current_url
    while True:
        log.info(f"Connecting: {current_url}")
        try:
            resp = requests.get(
                current_url, stream=True, timeout=10)
            if resp.status_code != 200:
                log.warning(f"ESP32 {resp.status_code}")
                time.sleep(3); continue
            camera_ok = True
            log.info("ESP32-S3 connected!")
            buf = b""
            for chunk in resp.iter_content(chunk_size=1024):
                buf += chunk
                a = buf.find(b'\xff\xd8')
                b = buf.find(b'\xff\xd9')
                if a != -1 and b != -1:
                    jpg = buf[a:b+2]
                    buf = buf[b+2:]
                    img = cv2.imdecode(
                        np.frombuffer(jpg, dtype=np.uint8),
                        cv2.IMREAD_COLOR)
                    if img is not None:
                        with camera_lock:
                            camera_frame = img
                    if len(buf) > 200000:
                        buf = b""
        except requests.exceptions.ConnectionError:
            camera_ok = False
            log.warning("ESP32 lost. Retry 3s...")
            time.sleep(3)
        except Exception as e:
            camera_ok = False
            log.error(f"Camera: {e}")
            time.sleep(3)

# ── YOLO ─────────────────────────────────────────────────────
def nms(boxes, scores, thresh):
    if not len(boxes): return []
    x1=boxes[:,0].astype(float); y1=boxes[:,1].astype(float)
    x2=boxes[:,2].astype(float); y2=boxes[:,3].astype(float)
    areas=(x2-x1)*(y2-y1)
    order=scores.argsort()[::-1]; keep=[]
    while order.size:
        i=order[0]; keep.append(i)
        xx1=np.maximum(x1[i],x1[order[1:]])
        yy1=np.maximum(y1[i],y1[order[1:]])
        xx2=np.minimum(x2[i],x2[order[1:]])
        yy2=np.minimum(y2[i],y2[order[1:]])
        w=np.maximum(0.,xx2-xx1)
        h=np.maximum(0.,yy2-yy1)
        iou=(w*h)/(areas[i]+areas[order[1:]]-(w*h)+1e-6)
        order=order[np.where(iou<=thresh)[0]+1]
    return keep

def run_yolo(frame):
    h,w  = frame.shape[:2]
    rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    inp  = np.expand_dims(
        cv2.resize(rgb,(INPUT_SIZE,INPUT_SIZE)
    ).astype(np.float32)/255., 0)
    with model_lock:
        interpreter.set_tensor(inp_d[0]["index"], inp)
        interpreter.invoke()
        pred = interpreter.get_tensor(out_d[0]["index"])[0]
    if pred.shape[0] < pred.shape[1]: pred = pred.T
    scores = (pred[:,4] if pred.shape[1]==5
              else pred[:,4:].max(1))
    coords = pred[:,:4]
    mask   = scores > CONF_THRESH
    if not np.any(mask): return [],[]
    fb,fs  = coords[mask],scores[mask]
    cx,cy  = fb[:,0]*w,fb[:,1]*h
    bw,bh  = fb[:,2]*w,fb[:,3]*h
    x1=np.clip(cx-bw/2,0,w).astype(int)
    y1=np.clip(cy-bh/2,0,h).astype(int)
    x2=np.clip(cx+bw/2,0,w).astype(int)
    y2=np.clip(cy+bh/2,0,h).astype(int)
    boxes=np.stack([x1,y1,x2,y2],axis=1)
    keep=nms(boxes,fs,IOU_THRESH)
    fb2,fs2=[],[]
    for i in keep:
        bx=boxes[i]
        if (bx[2]-bx[0])*(bx[3]-bx[1])<w*h*MAX_BOX_RATIO:
            fb2.append(bx); fs2.append(fs[i])
    return fb2,fs2

def get_severity(box,h,w):
    a=(box[2]-box[0])*(box[3]-box[1])/(h*w)
    if a>=0.04: return "CRITICAL",(0,0,220)
    if a>=0.01: return "MEDIUM",  (0,140,255)
    return "LOW",(0,220,255)

def draw_boxes(frame,boxes,scores):
    h,w=frame.shape[:2]
    for box,score in zip(boxes,scores):
        x1,y1,x2,y2=box
        sev,color=get_severity(box,h,w)
        wm=round((x2-x1)*CAMERA_MM/w,1)
        hm=round((y2-y1)*CAMERA_MM/h,1)
        cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
        txt=f"{sev} {score:.0%} {wm}x{hm}mm"
        (tw,th),_=cv2.getTextSize(
            txt,cv2.FONT_HERSHEY_SIMPLEX,0.5,1)
        cv2.rectangle(frame,
            (x1,y1-th-8),(x1+tw+4,y1),color,-1)
        cv2.putText(frame,txt,(x1+2,y1-5),
            cv2.FONT_HERSHEY_SIMPLEX,0.5,(255,255,255),1)
    return frame

# ── Shared state ──────────────────────────────────────────────
last_boxes  = []
last_scores = []
boxes_lock  = threading.Lock()
latest      = {"label":"--","part_id":"--","n_defects":0,
               "severity":"---","confidence":0,
               "size_mm":"---","timestamp":"--",
               "image_url":"","qr_code":""}
latest_lock = threading.Lock()
last_infer  = 0

# ── Inference loop ────────────────────────────────────────────
def inference_loop():
    global last_infer, latest, last_boxes, last_scores
    while True:
        time.sleep(0.1)
        if time.time()-last_infer < INSPECT_EVERY: continue
        with camera_lock:
            if camera_frame is None: continue
            frame = camera_frame.copy()
        last_infer = time.time()

        try:
            boxes,scores = run_yolo(frame)
        except Exception as e:
            log.error(f"Inference: {e}"); continue

        with boxes_lock:
            last_boxes  = boxes
            last_scores = scores

        n       = len(boxes)
        label   = "NOK" if n>0 else "OK"
        part_id = str(uuid.uuid4())[:8].upper()
        h,w     = frame.shape[:2]
        ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sev,conf,size_mm = "---",0.,"---"
        if n>0:
            best   = int(np.argmax(scores))
            sev,_  = get_severity(boxes[best],h,w)
            conf   = float(scores[best])
            wm=round((boxes[best][2]-boxes[best][0])*CAMERA_MM/w,1)
            hm=round((boxes[best][3]-boxes[best][1])*CAMERA_MM/h,1)
            size_mm=f"{wm}x{hm}"

        qr_b64 = generate_qr_b64(part_id,label,ts,sev)

        ann = draw_boxes(frame.copy(),boxes,scores)
        clr = (0,210,0) if label=="OK" else (0,0,220)
        cv2.rectangle(ann,(0,0),(w,46),(10,12,20),-1)
        cv2.putText(ann,label,(10,33),
            cv2.FONT_HERSHEY_SIMPLEX,1.2,clr,3)
        cv2.putText(ann,
            f"ID:{part_id}  {ts}  Defects:{n}",
            (120,25),cv2.FONT_HERSHEY_SIMPLEX,
            0.5,(160,170,180),1)

        img_file = f"{part_id}.jpg"
        cv2.imwrite(
            os.path.join(SNAPSHOT_DIR,img_file),
            ann,[cv2.IMWRITE_JPEG_QUALITY,88])

        db_insert(part_id,label,n,sev,
                  conf,size_mm,img_file,"",qr_b64)

        stats = db_get_stats()
        check_trend_alert(
            stats.get("recent_nok",0),
            stats.get("rate_change",0))

        with latest_lock:
            latest = {
                "label":label,"part_id":part_id,
                "n_defects":n,"severity":sev,
                "confidence":round(conf,3),
                "size_mm":size_mm,
                "timestamp":datetime.now().strftime("%H:%M:%S"),
                "image_url":"","qr_code":qr_b64
            }

        log.info(f"[{part_id}] {label} defects:{n} sev:{sev}")

        ann_copy = ann.copy()
        def bg_upload(pid,lbl,nd,sv,cf,sm,img):
            url = upload_supabase(pid,lbl,nd,sv,cf,sm,img)
            if url:
                db_update_url(pid,url)
                with latest_lock:
                    if latest["part_id"]==pid:
                        latest["image_url"]=url

        threading.Thread(
            target=bg_upload,
            args=(part_id,label,n,sev,conf,size_mm,ann_copy),
            daemon=True).start()

# ── Stream ────────────────────────────────────────────────────
def gen_stream():
    interval = 1.0/STREAM_FPS
    while True:
        t0 = time.time()
        with camera_lock:
            if camera_frame is None:
                time.sleep(0.05); continue
            frame = camera_frame.copy()
        with boxes_lock:
            boxes  = list(last_boxes)
            scores = list(last_scores)
        frame = draw_boxes(frame,boxes,scores)
        label = "NOK" if boxes else "OK"
        clr   = (0,210,0) if label=="OK" else (0,0,220)
        cv2.putText(frame,label,(10,35),
            cv2.FONT_HERSHEY_SIMPLEX,1.1,clr,2)
        _,buf = cv2.imencode(
            ".jpg",frame,[cv2.IMWRITE_JPEG_QUALITY,60])
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n"
               +buf.tobytes()+b"\r\n")
        time.sleep(max(0,interval-(time.time()-t0)))

# ── Flask ─────────────────────────────────────────────────────
app = Flask(__name__,
    template_folder=os.path.join(BASE_DIR,"templates"),
    static_folder=os.path.join(BASE_DIR,"static"))

@app.route("/")
def index(): return render_template("index.html")

# Add these routes after the existing @app.route("/") route

@app.route("/monitor")
def monitor(): return render_template("monitor.html")

@app.route("/analytics")
def analytics(): return render_template("analytics.html")

@app.route("/log")
def log_page(): return render_template("log.html")

@app.route("/alerts")
def alerts_page(): return render_template("alerts.html")

@app.route("/video_feed")
def video_feed():
    return Response(gen_stream(),
        mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/stats")
def api_stats():
    return jsonify({"ok":True,"data":db_get_stats()})

@app.route("/api/latest")
def api_latest():
    with latest_lock:
        return jsonify({"ok":True,"data":latest})

@app.route("/api/inspections")
def api_inspections():
    limit  = request.args.get("limit",  50,  type=int)
    offset = request.args.get("offset", 0,   type=int)
    rf     = request.args.get("result", None)
    sf     = request.args.get("severity",None)
    return jsonify({"ok":True,
                    "data":db_get_inspections(limit,offset,rf,sf),
                    "total":db_total(),
                    "limit":limit,"offset":offset})

@app.route("/api/inspections/<part_id>")
def api_detail(part_id):
    row = db_get_part(part_id)
    if not row: abort(404)
    return jsonify({"ok":True,"data":row})

@app.route("/part/<part_id>")
def part_page(part_id):
    row = db_get_part(part_id)
    if not row: abort(404)
    return render_template("dashboard.html")

@app.route("/api/alerts")
def api_alerts():
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM alerts
            ORDER BY id DESC LIMIT 20
        """).fetchall()
        return jsonify({"ok":True,
                        "data":[dict(r) for r in rows]})

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
              .update({"resolved":1})\
              .eq("id",alert_id).execute()
        except Exception as e:
            log.error(f"Supabase resolve: {e}")
    return jsonify({"ok":True})

@app.route("/api/health")
def api_health():
    return jsonify({
        "ok":True,"camera":camera_ok,
        "esp32_ip":ESP32_IP,
        "supabase":supabase_ok,
        "model":True,
        "uptime":round(time.time()-start_time,1)
    })

@app.route("/api/esp32/config",methods=["POST"])
def update_esp32():
    global current_url,ESP32_IP
    data=request.get_json()
    if "ip" not in data:
        return jsonify({"ok":False,"error":"No IP"}),400
    ESP32_IP    = data["ip"]
    current_url = (f"http://{ESP32_IP}:"
                   f"{ESP32_PORT}{STREAM_PATH}")
    return jsonify({"ok":True,"ip":ESP32_IP})

@app.route("/snapshots/<filename>")
def snapshot(filename):
    return send_from_directory(SNAPSHOT_DIR,filename)



@app.errorhandler(404)
def e404(e):
    return jsonify({"ok":False,"error":"Not found"}),404
@app.errorhandler(500)
def e500(e):
    return jsonify({"ok":False,"error":str(e)}),500

if __name__=="__main__":
    start_time=time.time()
    init_db()
    threading.Thread(
        target=camera_thread, daemon=True).start()
    threading.Thread(
        target=inference_loop,daemon=True).start()
    time.sleep(2)
    log.info(f"Dashboard : http://localhost:{PORT}")
    log.info(f"Supabase  : {'connected' if supabase_ok else 'NOT configured'}")
    app.run(host="0.0.0.0",port=PORT,
            threaded=True,use_reloader=False)