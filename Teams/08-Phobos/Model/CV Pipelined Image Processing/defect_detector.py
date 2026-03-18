"""
Industrial Defect Detector — Die Casting / Metal Sheets
=========================================================
Detects REAL defects: holes, voids, pores, cracks on metal parts.
Ignores surface texture and micro-noise.

Install:
    pip install opencv-python numpy

Run:
    python defect_detector.py

Controls (click the window first):
    1  →  METAL mode      (die casting, machined parts — grey metallic surface)
    2  →  SHEET mode      (punched holes / anomalies on flat metal sheet)
    3  →  DARK VOID mode  (dark pores on bright polished surface)
    +/-→  Sensitivity up/down
    B  →  Toggle binary mask view
    S  →  Save frame
    Q  →  Quit
"""

import cv2
import numpy as np
import time
import os
import platform
from datetime import datetime

# ─── Detection profiles ────────────────────────────────────────────────────────
# Each profile is tuned for a different real-world use case.

PROFILES = {
    # Die casting surfaces — grey/silver metallic, pores appear as dark spots
    "1_METAL": {
        "label":           "DIE CASTING / METAL PART",
        "blur_kernel":     7,
        "clahe_clip":      2.5,
        "clahe_tile":      8,
        "threshold":       "adaptive",
        "adaptive_block":  51,      # large block = ignores gradual lighting changes
        "adaptive_c":      8,       # higher C = only catches strong dark spots
        "morph_open":      5,       # removes fine texture noise
        "morph_close":     7,
        "min_pore_area":   200,     # px² — ignore tiny surface texture
        "max_pore_area":   80_000,
        "min_circularity": 0.10,    # allow elongated cracks too
        "min_solidity":    0.40,    # filters jagged noise contours
        "level_low":       0.5,
        "level_medium":    2.0,
        "level_high":      5.0,
    },

    # Punched / drilled holes in metal sheet — holes are much larger
    "2_SHEET": {
        "label":           "METAL SHEET HOLES / ANOMALY",
        "blur_kernel":     9,
        "clahe_clip":      2.0,
        "clahe_tile":      6,
        "threshold":       "otsu",  # good for high-contrast hole vs metal
        "adaptive_block":  51,
        "adaptive_c":      10,
        "morph_open":      9,       # aggressive open to remove surface marks
        "morph_close":     11,
        "min_pore_area":   800,     # holes are big — ignore anything smaller
        "max_pore_area":   200_000,
        "min_circularity": 0.20,
        "min_solidity":    0.50,
        "level_low":       0.3,
        "level_medium":    1.0,
        "level_high":      3.0,
    },

    # Polished bright surface — pores appear as dark voids (e.g. castings after machining)
    "3_DARK_VOID": {
        "label":           "DARK VOIDS — POLISHED SURFACE",
        "blur_kernel":     5,
        "clahe_clip":      4.0,
        "clahe_tile":      4,       # smaller tile = finer local contrast
        "threshold":       "adaptive",
        "adaptive_block":  31,
        "adaptive_c":      6,
        "morph_open":      3,
        "morph_close":     5,
        "min_pore_area":   120,
        "max_pore_area":   50_000,
        "min_circularity": 0.25,    # dark pores are roundish
        "min_solidity":    0.45,
        "level_low":       0.3,
        "level_medium":    1.5,
        "level_high":      4.0,
    },
}

SEVERITY_COLORS = {   # BGR
    "OK":       (50,  210,  50),
    "LOW":      (0,   210, 210),
    "MEDIUM":   (0,   160, 255),
    "HIGH":     (0,    50, 255),
    "CRITICAL": (0,     0, 220),
}

SENS_STEPS = [50, 100, 200, 400, 800, 1500, 3000]


# ─── Camera ────────────────────────────────────────────────────────────────────
def open_camera():
    OS = platform.system()
    order = (
        [(cv2.CAP_DSHOW, "DirectShow"), (cv2.CAP_MSMF, "MSMF"), (cv2.CAP_ANY, "Auto")]
        if OS == "Windows" else
        [(cv2.CAP_ANY, "AVFoundation")]
        if OS == "Darwin" else
        [(cv2.CAP_V4L2, "V4L2"), (cv2.CAP_ANY, "Auto")]
    )
    for backend, name in order:
        for idx in range(4):
            try:
                cap = cv2.VideoCapture(idx, backend)
                if not cap.isOpened():
                    cap.release(); continue
                ok, frame = cap.read()
                if ok and frame is not None and frame.size > 0:
                    print(f"[Camera] Device {idx} via {name}")
                    return cap
                cap.release()
            except Exception:
                pass
    return None


# ─── Detection ─────────────────────────────────────────────────────────────────
def detect(frame, p):
    """
    p = one profile dict from PROFILES.
    Returns (pores, porosity_pct, severity, binary_mask)
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 1. CLAHE — boost contrast so real defects stand out
    clahe    = cv2.createCLAHE(clipLimit=p["clahe_clip"],
                                tileGridSize=(p["clahe_tile"], p["clahe_tile"]))
    enhanced = clahe.apply(gray)

    # 2. Gaussian blur — smooth out surface texture
    k        = p["blur_kernel"] | 1
    blurred  = cv2.GaussianBlur(enhanced, (k, k), 0)

    # 3. Threshold
    if p["threshold"] == "otsu":
        _, binary = cv2.threshold(blurred, 0, 255,
                                  cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    else:
        binary = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            p["adaptive_block"], p["adaptive_c"]
        )

    # 4. Morphology — eliminate surface grain, keep real holes
    ko = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                   (p["morph_open"],  p["morph_open"]))
    kc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                   (p["morph_close"], p["morph_close"]))
    cleaned = cv2.morphologyEx(binary,  cv2.MORPH_OPEN,  ko)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kc)

    # 5. Contours → filter by area, circularity, solidity
    cnts, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    pores = []
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if not (p["min_pore_area"] <= area <= p["max_pore_area"]):
            continue

        # Circularity
        peri = cv2.arcLength(cnt, True)
        circ = (4 * np.pi * area / peri ** 2) if peri > 0 else 0
        if circ < p["min_circularity"]:
            continue

        # Solidity = area / convex_hull_area  (filters jagged noise)
        hull    = cv2.convexHull(cnt)
        h_area  = cv2.contourArea(hull)
        solidity = area / h_area if h_area > 0 else 0
        if solidity < p["min_solidity"]:
            continue

        x, y, bw, bh = cv2.boundingRect(cnt)
        M  = cv2.moments(cnt)
        cx = int(M["m10"] / M["m00"]) if M["m00"] else x + bw // 2
        cy = int(M["m01"] / M["m00"]) if M["m00"] else y + bh // 2

        pores.append({
            "cnt":      cnt,
            "area":     area,
            "cx": cx,   "cy": cy,
            "bbox":     (x, y, bw, bh),
            "circ":     round(circ, 3),
            "solidity": round(solidity, 3),
        })

    total   = sum(p2["area"] for p2 in pores)
    por_pct = total / (h * w) * 100

    lo, med, hi = p["level_low"], p["level_medium"], p["level_high"]
    if   por_pct < lo:      sev = "OK"
    elif por_pct < med:     sev = "LOW"
    elif por_pct < hi:      sev = "MEDIUM"
    elif por_pct < hi * 2:  sev = "HIGH"
    else:                   sev = "CRITICAL"

    return pores, round(por_pct, 3), sev, cleaned


# ─── Overlay ────────────────────────────────────────────────────────────────────
def draw(frame, pores, por_pct, sev, profile, fps, show_ids):
    out   = frame.copy()
    color = SEVERITY_COLORS[sev]

    # Draw each defect — filled contour + bounding box + ID label
    for i, p in enumerate(pores):
        x, y, bw, bh = p["bbox"]

        # Semi-filled contour
        mask = np.zeros(out.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [p["cnt"]], -1, 255, -1)
        tint = out.copy()
        tint[mask > 0] = [c // 2 + b // 2
                          for c, b in zip(color, tint[mask > 0].T.reshape(-1, 3).mean(axis=0).astype(int))]
        cv2.addWeighted(tint, 0.35, out, 0.65, 0, out)

        # Bounding box
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)

        # Label with area
        if show_ids:
            label = f"#{i+1}  {p['area']:.0f}px2"
            cv2.putText(out, label, (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)

    # ── HUD panel ──────────────────────────────────────────────────────────────
    ov = out.copy()
    cv2.rectangle(ov, (0, 0), (310, 170), (10, 10, 10), -1)
    cv2.addWeighted(ov, 0.65, out, 0.35, 0, out)

    rows = [
        (f"Mode     : {profile['label'][:22]}",     (200, 200, 200), 0.46),
        (f"Porosity : {por_pct:.3f} %",              color,           0.58),
        (f"Defects  : {len(pores)}",                 (220, 220, 220), 0.55),
        (f"Severity : {sev}",                        color,           0.58),
        (f"Min area : {profile['min_pore_area']}px2",(140, 140, 140), 0.44),
        (f"FPS      : {fps:.1f}",                    (120, 120, 120), 0.44),
    ]
    for i, (txt, col, sc) in enumerate(rows):
        cv2.putText(out, txt, (8, 22 + i * 24),
                    cv2.FONT_HERSHEY_SIMPLEX, sc, col, 1, cv2.LINE_AA)

    # Severity badge (top-right)
    (tw, th), _ = cv2.getTextSize(sev, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
    bx = out.shape[1] - tw - 24
    ov2 = out.copy()
    cv2.rectangle(ov2, (bx - 10, 6), (bx + tw + 10, 6 + th + 14), (10, 10, 10), -1)
    cv2.addWeighted(ov2, 0.7, out, 0.3, 0, out)
    cv2.putText(out, sev, (bx, 6 + th + 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2, cv2.LINE_AA)

    # Bottom hint
    hint = "1=Metal  2=Sheet  3=Void  +/-=sens  B=mask  I=IDs  S=save  Q=quit"
    cv2.putText(out, hint, (8, out.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (140, 140, 140), 1, cv2.LINE_AA)

    return out


def binary_panel(binary, h, w):
    b3    = cv2.cvtColor(cv2.resize(binary, (w // 2, h)), cv2.COLOR_GRAY2BGR)
    # Colour the detected regions red for clarity
    b3[binary[:, :w//2].T.T > 0] = [0, 60, 220]  # blue-tinted
    mask_resized = cv2.resize(binary, (w // 2, h))
    b3[mask_resized > 0] = (0, 80, 255)
    cv2.putText(b3, "Binary mask  (red = detected defects)", (6, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    return b3


# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n╔══════════════════════════════════════════════════╗")
    print("║  Industrial Defect Detector — LIVE               ║")
    print("║  Die casting  •  Metal sheets  •  Drilled holes  ║")
    print("╚══════════════════════════════════════════════════╝\n")
    print("  Keys:  1=Die casting   2=Sheet holes   3=Dark voids")
    print("         +/- sensitivity    B=mask    I=labels    Q=quit\n")

    cap = open_camera()
    if cap is None:
        print("[Error] Webcam not found. Close other apps using camera and retry.")
        input("Press Enter to exit...")
        return

    for rw, rh in [(1280, 720), (640, 480)]:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  rw)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, rh)
        ok, f = cap.read()
        if ok and f is not None and f.size > 0:
            break

    for _ in range(8):
        cap.read(); time.sleep(0.03)

    cam_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cam_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[Camera] {cam_w}x{cam_h}  — live detection ON\n")

    if platform.system() == "Linux":
        cv2.startWindowThread()

    WIN = "Industrial Defect Detector — LIVE  [click here first]"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, min(cam_w, 1280), min(cam_h, 720))

    os.makedirs("defect_captures", exist_ok=True)

    # ── State ──────────────────────────────────────────────────────────────────
    profile_keys = list(PROFILES.keys())
    prof_idx     = 0                          # start on DIE CASTING
    profile      = PROFILES[profile_keys[0]]
    show_bin     = False
    show_ids     = True
    fail_count   = 0
    fps          = 0.0
    fps_t        = time.perf_counter()
    frame_cnt    = 0
    last_display = None

    # Sensitivity index aligned to current profile's min_pore_area
    def best_sens(profile):
        return SENS_STEPS.index(min(SENS_STEPS,
                                    key=lambda v: abs(v - profile["min_pore_area"])))
    sens_idx = best_sens(profile)

    print(f"[App] Starting in profile: {profile['label']}")
    print("[App] CLICK the window, then press keys.\n")

    while True:
        ret, frame = cap.read()

        if not ret or frame is None or frame.size == 0:
            fail_count += 1
            if fail_count > 50:
                cap.release(); time.sleep(0.8)
                cap = open_camera()
                if cap is None: break
                fail_count = 0
            time.sleep(0.03)
            continue
        fail_count = 0

        # ── Run detection ──────────────────────────────────────────────────────
        pores, por_pct, severity, binary = detect(frame, profile)

        # ── FPS ────────────────────────────────────────────────────────────────
        frame_cnt += 1
        now = time.perf_counter()
        if now - fps_t >= 0.5:
            fps = frame_cnt / (now - fps_t)
            frame_cnt = 0; fps_t = now

        # ── Compose display ────────────────────────────────────────────────────
        annotated = draw(frame, pores, por_pct, severity, profile, fps, show_ids)

        if show_bin:
            panel   = binary_panel(binary, cam_h, cam_w)
            display = np.hstack([annotated, panel])
        else:
            display = annotated

        last_display = display.copy()
        cv2.imshow(WIN, display)

        # ── Keys ───────────────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF

        if key in (ord('q'), 27):
            break

        elif key == ord('1'):
            prof_idx = 0
            profile  = PROFILES[profile_keys[0]]
            sens_idx = best_sens(profile)
            print(f"[App] Profile → {profile['label']}")

        elif key == ord('2'):
            prof_idx = 1
            profile  = PROFILES[profile_keys[1]]
            sens_idx = best_sens(profile)
            print(f"[App] Profile → {profile['label']}")

        elif key == ord('3'):
            prof_idx = 2
            profile  = PROFILES[profile_keys[2]]
            sens_idx = best_sens(profile)
            print(f"[App] Profile → {profile['label']}")

        elif key in (ord('+'), ord('=')):
            sens_idx = min(sens_idx + 1, len(SENS_STEPS) - 1)
            profile  = dict(profile)
            profile["min_pore_area"] = SENS_STEPS[sens_idx]
            print(f"[App] Min defect area → {profile['min_pore_area']} px²  (less sensitive)")

        elif key == ord('-'):
            sens_idx = max(sens_idx - 1, 0)
            profile  = dict(profile)
            profile["min_pore_area"] = SENS_STEPS[sens_idx]
            print(f"[App] Min defect area → {profile['min_pore_area']} px²  (more sensitive)")

        elif key == ord('b'):
            show_bin = not show_bin
            cv2.resizeWindow(WIN,
                             min(cam_w * (2 if show_bin else 1), 1600),
                             min(cam_h, 720))
            print(f"[App] Binary mask {'ON' if show_bin else 'OFF'}")

        elif key == ord('i'):
            show_ids = not show_ids
            print(f"[App] Defect labels {'ON' if show_ids else 'OFF'}")

        elif key == ord('s'):
            fname = f"defect_captures/defect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            cv2.imwrite(fname, last_display)
            print(f"[App] Saved → {fname}")

    cap.release()
    cv2.destroyAllWindows()
    print("[App] Done.")


if __name__ == "__main__":
    main()
