"""
Metal Pore Detector — Morphological Boundary + Edge Segmentation
=================================================================
Detects real pores / holes on metal surfaces with minimal noise.

Pipeline:
  Grayscale → CLAHE → Gaussian Blur
      → Bottom-Hat Transform   (isolates dark pores on bright metal)
      → Canny Edge Detection   (finds pore boundaries precisely)
      → Morphological Close    (seals open edge loops into closed regions)
      → Flood-fill / Contours  (extracts filled pore blobs)
      → Strict filters         (area + circularity + solidity)

Install:
    pip install opencv-python numpy

Run:
    python pore_detector.py

Controls (click the window first):
    +  / =   →  raise min pore size  (less noise)
    -        →  lower min pore size  (more detections)
    E        →  toggle edge map overlay
    B        →  toggle binary mask panel
    I        →  toggle defect ID labels
    S        →  save frame
    Q / ESC  →  quit
"""

import cv2
import numpy as np
import time
import os
import platform
from datetime import datetime


# ─── Parameters ────────────────────────────────────────────────────────────────
# These are deliberately conservative — tuned to IGNORE surface texture.

P = {
    # Pre-processing
    "blur_kernel":     7,       # smooths surface grain before edge detection
    "clahe_clip":      2.0,     # mild contrast boost — don't over-enhance noise
    "clahe_tile":      8,

    # Bottom-hat transform kernel (detects dark blobs on bright surface)
    "bottomhat_ksize": 21,      # bigger = catches larger dark regions; min ~15

    # Canny edge detection
    "canny_low":       30,
    "canny_high":      90,

    # Morphological close after Canny (seals broken edge loops)
    "close_ksize":     9,

    # Pore filters — the main noise gate
    "min_area":        500,     # px²  — raise if still noisy (try 800, 1200)
    "max_area":        120_000, # px²
    "min_circularity": 0.30,    # pores are roundish; raise to 0.5 for round holes only
    "min_solidity":    0.55,    # rejects jagged / fragmented contours

    # Severity thresholds (% of frame area covered by pores)
    "level_low":       0.3,
    "level_medium":    1.5,
    "level_high":      4.0,
}

# Min-area presets for +/- keys
SENS_STEPS = [200, 350, 500, 750, 1000, 1500, 2500, 4000]

SEVERITY_COLORS = {   # BGR
    "OK":       (50,  210,  50),
    "LOW":      (0,   200, 200),
    "MEDIUM":   (0,   150, 255),
    "HIGH":     (0,    40, 255),
    "CRITICAL": (0,     0, 210),
}


# ─── Camera ────────────────────────────────────────────────────────────────────
def open_camera():
    OS = platform.system()
    order = (
        [(cv2.CAP_DSHOW,"DirectShow"),(cv2.CAP_MSMF,"MSMF"),(cv2.CAP_ANY,"Auto")]
        if OS == "Windows" else
        [(cv2.CAP_ANY, "AVFoundation")]
        if OS == "Darwin" else
        [(cv2.CAP_V4L2,"V4L2"),(cv2.CAP_ANY,"Auto")]
    )
    for backend, name in order:
        for idx in range(4):
            try:
                cap = cv2.VideoCapture(idx, backend)
                if not cap.isOpened(): cap.release(); continue
                ok, f = cap.read()
                if ok and f is not None and f.size > 0:
                    print(f"[Camera] Device {idx} via {name}")
                    return cap
                cap.release()
            except Exception:
                pass
    return None


# ─── Detection pipeline ────────────────────────────────────────────────────────
def detect(frame, p):
    """
    Two-channel approach:
      Channel A — Bottom-hat:  finds dark pores by morphological difference
      Channel B — Edge-close:  finds pore outlines via Canny then seals them

    The two masks are OR-combined, then strictly filtered.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # ── 1. CLAHE — mild local contrast enhancement ────────────────────────────
    clahe    = cv2.createCLAHE(clipLimit=p["clahe_clip"],
                                tileGridSize=(p["clahe_tile"], p["clahe_tile"]))
    enhanced = clahe.apply(gray)

    # ── 2. Gaussian blur — removes high-freq surface texture ──────────────────
    k       = p["blur_kernel"] | 1
    blurred = cv2.GaussianBlur(enhanced, (k, k), 0)

    # ── CHANNEL A: Morphological Bottom-Hat Transform ─────────────────────────
    # bottom_hat = morph_close(img) - img
    # Highlights regions that are DARKER than their local neighbourhood.
    # On a bright metallic surface, pores/voids are exactly that.
    bh_k      = cv2.getStructuringElement(
                    cv2.MORPH_ELLIPSE,
                    (p["bottomhat_ksize"], p["bottomhat_ksize"]))
    bottomhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, bh_k)

    # Threshold the bottom-hat result — only keep strong dark regions
    bh_mean, bh_std = cv2.meanStdDev(bottomhat)
    bh_thresh       = float(bh_mean[0][0]) + 1.5 * float(bh_std[0][0])
    bh_thresh       = max(bh_thresh, 12)         # hard floor — never too low
    _, mask_bh      = cv2.threshold(bottomhat, bh_thresh, 255, cv2.THRESH_BINARY)

    # ── CHANNEL B: Canny Edge + Morphological Close ───────────────────────────
    # Canny finds the boundaries of holes precisely.
    # Closing the edges seals them into filled regions.
    edges    = cv2.Canny(blurred, p["canny_low"], p["canny_high"])
    ck       = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                         (p["close_ksize"], p["close_ksize"]))
    closed   = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, ck)

    # Flood-fill from border to label background, invert = only interior regions
    flood = closed.copy()
    fill  = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, fill, (0, 0), 255)
    mask_edge = cv2.bitwise_not(flood)

    # ── Combine both channels ─────────────────────────────────────────────────
    combined = cv2.bitwise_or(mask_bh, mask_edge)

    # ── Final morphological cleanup ───────────────────────────────────────────
    # Open: remove tiny isolated pixels (noise)
    # Close: fill micro-gaps inside real pores
    open_k   = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    close_k  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    cleaned  = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  open_k)
    cleaned  = cv2.morphologyEx(cleaned,  cv2.MORPH_CLOSE, close_k)

    # ── Contour extraction + strict filtering ─────────────────────────────────
    cnts, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    pores = []
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if not (p["min_area"] <= area <= p["max_area"]):
            continue

        # Circularity
        peri = cv2.arcLength(cnt, True)
        circ = (4 * np.pi * area / peri ** 2) if peri > 0 else 0
        if circ < p["min_circularity"]:
            continue

        # Solidity (area / convex hull area) — rejects broken/jagged shapes
        hull     = cv2.convexHull(cnt)
        h_area   = cv2.contourArea(hull)
        solidity = (area / h_area) if h_area > 0 else 0
        if solidity < p["min_solidity"]:
            continue

        x, y, bw, bh2 = cv2.boundingRect(cnt)
        M  = cv2.moments(cnt)
        cx = int(M["m10"] / M["m00"]) if M["m00"] else x + bw // 2
        cy = int(M["m01"] / M["m00"]) if M["m00"] else y + bh2 // 2

        pores.append({
            "cnt": cnt, "area": area,
            "cx": cx,   "cy": cy,
            "bbox": (x, y, bw, bh2),
            "circ": round(circ, 3),
            "solidity": round(solidity, 3),
        })

    total_area = sum(pp["area"] for pp in pores)
    por_pct    = total_area / (h * w) * 100

    lo, med, hi = p["level_low"], p["level_medium"], p["level_high"]
    if   por_pct < lo:      sev = "OK"
    elif por_pct < med:     sev = "LOW"
    elif por_pct < hi:      sev = "MEDIUM"
    elif por_pct < hi * 2:  sev = "HIGH"
    else:                   sev = "CRITICAL"

    return pores, round(por_pct, 3), sev, cleaned, edges


# ─── Draw overlay ──────────────────────────────────────────────────────────────
def draw_overlay(frame, pores, por_pct, sev, p, fps, show_ids):
    out   = frame.copy()
    color = SEVERITY_COLORS[sev]

    for i, pp in enumerate(pores):
        x, y, bw, bh = pp["bbox"]

        # Filled contour tint
        overlay = out.copy()
        cv2.drawContours(overlay, [pp["cnt"]], -1, color, -1)
        cv2.addWeighted(overlay, 0.30, out, 0.70, 0, out)

        # Contour outline (2px)
        cv2.drawContours(out, [pp["cnt"]], -1, color, 2)

        # Bounding box
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 1)

        if show_ids:
            lbl = f"#{i+1}  {pp['area']:.0f}px"
            cv2.putText(out, lbl, (x, max(y - 5, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)

    # HUD
    ov = out.copy()
    cv2.rectangle(ov, (0, 0), (300, 155), (10, 10, 10), -1)
    cv2.addWeighted(ov, 0.65, out, 0.35, 0, out)

    rows = [
        (f"Porosity : {por_pct:.3f} %",             color,          0.56),
        (f"Pores    : {len(pores)}",                 (220,220,220),  0.52),
        (f"Severity : {sev}",                        color,          0.56),
        (f"Min area : {p['min_area']} px",           (150,150,150),  0.44),
        (f"Min circ : {p['min_circularity']:.2f}",   (140,140,140),  0.44),
        (f"FPS      : {fps:.1f}",                    (120,120,120),  0.42),
    ]
    for i, (txt, col, sc) in enumerate(rows):
        cv2.putText(out, txt, (8, 22 + i * 22),
                    cv2.FONT_HERSHEY_SIMPLEX, sc, col, 1, cv2.LINE_AA)

    # Severity badge
    (tw, th), _ = cv2.getTextSize(sev, cv2.FONT_HERSHEY_SIMPLEX, 0.72, 2)
    bx = out.shape[1] - tw - 24
    ov2 = out.copy()
    cv2.rectangle(ov2, (bx-10,6),(bx+tw+10,6+th+14),(10,10,10),-1)
    cv2.addWeighted(ov2, 0.70, out, 0.30, 0, out)
    cv2.putText(out, sev, (bx, 6+th+8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.72, color, 2, cv2.LINE_AA)

    # Bottom hint
    cv2.putText(out,
        "+/-=size  E=edges  B=mask  I=labels  S=save  Q=quit",
        (8, out.shape[0]-10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (130,130,130), 1, cv2.LINE_AA)

    return out


def make_binary_panel(binary, h, w):
    small = cv2.resize(binary, (w//2, h))
    b3    = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    b3[small > 0] = (0, 80, 255)   # detected regions in orange-red
    cv2.putText(b3, "Cleaned mask", (6, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,200,200), 1)
    return b3


def make_edge_panel(edges, h, w):
    small = cv2.resize(edges, (w//2, h))
    e3    = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
    e3[small > 0] = (80, 220, 80)   # edges in green
    cv2.putText(e3, "Canny edges", (6, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200,200,200), 1)
    return e3


# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n╔═══════════════════════════════════════════════════╗")
    print("║  Metal Pore Detector  —  LIVE                     ║")
    print("║  Bottom-Hat + Canny Edge Segmentation             ║")
    print("╚═══════════════════════════════════════════════════╝\n")

    cap = open_camera()
    if cap is None:
        print("[Error] No webcam found. Close other apps using camera.")
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
    print(f"[Camera] {cam_w}x{cam_h}")

    if platform.system() == "Linux":
        cv2.startWindowThread()

    WIN = "Metal Pore Detector — LIVE  [click here first]"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, min(cam_w, 1280), min(cam_h, 720))

    os.makedirs("pore_captures", exist_ok=True)

    p          = P.copy()
    show_bin   = False
    show_edges = False
    show_ids   = True
    fail_count = 0
    fps        = 0.0
    fps_t      = time.perf_counter()
    frame_cnt  = 0
    last_disp  = None

    sens_idx   = SENS_STEPS.index(min(SENS_STEPS,
                                      key=lambda v: abs(v - p["min_area"])))

    print("[App] CLICK the window, then use +/- to tune sensitivity.\n")

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

        # ── Detect ────────────────────────────────────────────────────────────
        pores, por_pct, sev, binary, edges = detect(frame, p)

        # ── FPS ───────────────────────────────────────────────────────────────
        frame_cnt += 1
        now = time.perf_counter()
        if now - fps_t >= 0.5:
            fps = frame_cnt / (now - fps_t)
            frame_cnt = 0; fps_t = now

        # ── Compose display ───────────────────────────────────────────────────
        annotated = draw_overlay(frame, pores, por_pct, sev, p, fps, show_ids)

        if show_edges and show_bin:
            ep = make_edge_panel(edges, cam_h, cam_w)
            bp = make_binary_panel(binary, cam_h, cam_w)
            side = np.vstack([ep, bp])
            side = cv2.resize(side, (cam_w//2, cam_h))
            display = np.hstack([annotated, side])
        elif show_edges:
            display = np.hstack([annotated, make_edge_panel(edges, cam_h, cam_w)])
        elif show_bin:
            display = np.hstack([annotated, make_binary_panel(binary, cam_h, cam_w)])
        else:
            display = annotated

        last_disp = display.copy()
        cv2.imshow(WIN, display)

        key = cv2.waitKey(1) & 0xFF

        if key in (ord('q'), 27):
            break

        elif key in (ord('+'), ord('=')):
            sens_idx = min(sens_idx + 1, len(SENS_STEPS) - 1)
            p["min_area"] = SENS_STEPS[sens_idx]
            print(f"[App] Min area → {p['min_area']} px²  (stricter)")

        elif key == ord('-'):
            sens_idx = max(sens_idx - 1, 0)
            p["min_area"] = SENS_STEPS[sens_idx]
            print(f"[App] Min area → {p['min_area']} px²  (looser)")

        elif key == ord('e'):
            show_edges = not show_edges
            nw = cam_w * (1 + int(show_edges) + int(show_bin))
            cv2.resizeWindow(WIN, min(nw, 1800), min(cam_h, 720))
            print(f"[App] Edge view {'ON' if show_edges else 'OFF'}")

        elif key == ord('b'):
            show_bin = not show_bin
            nw = cam_w * (1 + int(show_edges) + int(show_bin))
            cv2.resizeWindow(WIN, min(nw, 1800), min(cam_h, 720))
            print(f"[App] Binary mask {'ON' if show_bin else 'OFF'}")

        elif key == ord('i'):
            show_ids = not show_ids

        elif key == ord('s'):
            fname = f"pore_captures/pore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            cv2.imwrite(fname, last_disp)
            print(f"[App] Saved → {fname}")

    cap.release()
    cv2.destroyAllWindows()
    print("[App] Done.")


if __name__ == "__main__":
    main()
