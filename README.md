# DreamVision — Industrial IoT Thermal Monitoring Dashboard

**Team:** Team Omega  
**Project:** Real-time thermal anomaly detection & visualization for industrial equipment monitoring  
**Status:** MVP+ Production-Ready · Hackathon Winner-Grade Architecture  
**Repository:** https://github.com/rchandrashekar53/Enduraverse-26/  

---

## 🎯 Project Overview

**DreamVision** is an **advanced IoT dashboard** that bridges hardware sensors (ESP32-based thermal + camera) with a real-time web interface for instant anomaly detection and visual thermal analysis. Built for industrial operators who need split-second thermal insights without manual intervention.

### 🚀 Core Features

✅ **Live Thermal Heatmap** — 12×12 animated grid showing real-time temperature distribution with color-coded risk zones (blue→green→yellow→orange→red)  
✅ **Live Camera Stream** — MJPEG video feed from ESP32 OV3660 camera side-by-side with thermal  
✅ **Anomaly Detection** — Automatic high-temperature event logging with image capture  
✅ **Real-time Telemetry** — Convex backend with GraphQL queries + WebSocket live subscriptions  
✅ **Historical Charts** — Recharts time-series visualization of temperature trends + defect timeline  
✅ **Device Auto-Bridge** — One-command ingest pipeline polling ESP32 endpoints → Convex → Dashboard  
✅ **Responsive UI** — Tailwind CSS v4 + React 19 with mobile-first responsive grid layout  

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ ESP32-S3 Hardware Layer (10.94.151.79)                          │
├──────────────────────────────────────┬──────────────────────────┤
│ Port 80/81: MJPEG Camera Stream      │ Port 82: Thermal JSON     │
│ OV3660 Camera                        │ MLX90614 IR Sensor        │
│ + Servo Scanner (Hardware Scan)      │ /data endpoint            │
└──────────────────────────────────────┴──────────────────────────┘
                    │                              │
                    │ HTTP GET                     │ HTTP GET
                    ▼                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ Bridge Layer (Local Machine)                                     │
│ scripts/esp32-bridge.ts                                          │
├──────────────────────────────────────────────────────────────────┤
│ • Polls thermal endpoint every 1000ms                            │
│ • Parses JSON (with nan/inf resilience)                          │
│ • Captures image on anomaly (NOK, temp ≥ 42°C)                  │
│ • Posts {temp, minTemp, maxTemp, avgTemp, status, image} to     │
│   Convex ingest @ http://127.0.0.1:3211/ingest                  │
└──────────────────────────────────────────────────────────────────┘
                    │
                    │ HTTP POST + Device Secret Header
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ Backend: Convex (Local Dev → Cloud Deploy)                      │
├──────────────────────────────────────────────────────────────────┤
│ • HTTP Action: convex/http.ts (ingest endpoint)                 │
│ • Mutations: convex/telemetry.ts (insertReading)                │
│ • Queries: convex/telemetry.ts (getLatest, getLast20)           │
│ • Storage: Blob storage for defect images (High-temp captures)  │
│ • Schema: telemetry + defects tables (auto-pruning)             │
└──────────────────────────────────────────────────────────────────┘
                    │
                    │ GraphQL (Convex React hooks)
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ Frontend: Next.js 16.1.7 (React 19, TypeScript 5)               │
├──────────────────────────────────────────────────────────────────┤
│ • Pages:                                                          │
│   - src/app/page.tsx (Main Dashboard)                            │
│ • Components:                                                     │
│   - DigitalTwin.tsx → Animated 12×12 thermal heatmap (LIVE)     │
│   - CameraStreamCard.tsx → MJPEG stream player + fallback        │
│   - GhostLineChart.tsx → Recharts time-series (tail of 20 pts)  │
│   - XRayCards.tsx → Defect history grid (anomaly snapshots)     │
│   - ConnectionStatus.tsx → Device connection health indicator   │
│ • Layout: 3-column responsive grid (chart 2-col, heatmap 1-col, │
│   camera 1-col on desktop; 1-col stack on mobile)               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📦 Tech Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Frontend** | Next.js | 16.1.7 | SSR + client components, Turbopack |
| | React | 19.2.3 | UI framework |
| | TypeScript | 5 | Type-safe development |
| | Tailwind CSS | v4 | Responsive styling |
| **Backend** | Convex | 1.33.1 | Realtime database + HTTP actions |
| | GraphQL | Built-in | Type-safe API |
| **3D/Charts** | Three.js | 0.183.2 | 3D rendering (fallback) |
| | @react-three/fiber | 9.5.0 | React bindings for Three.js |
| | Recharts | 3.8.0 | Time-series charts |
| **Hardware Bridge** | Node.js/TypeScript | 24.14.0 | ESP32 ingest pipeline |
| | Convex SDK | 1.33.1 | Backend integration |
| **Hardware** | ESP32-S3 | — | Main controller |
| | OV3660 Camera | — | MJPEG video capture |
| | MLX90614 IR Sensor | — | Contactless temperature |
| **Build Tools** | Turbopack | — | Next.js bundler |
| | ESLint | 9 | Static analysis |
| | tsx | 4.21.0 | TypeScript execution (scripts) |

---

## 📁 Project Structure

```
dreamvision/
├── convex/                          # Backend (Convex Functions)
│   ├── http.ts                      # HTTP ingest endpoint (@POST /ingest)
│   ├── telemetry.ts                 # Telemetry queries + mutations
│   ├── defects.ts                   # Defect logging (anomalies)
│   ├── schema.ts                    # Database schema
│   └── _generated/                  # Convex generated API types
│
├── src/
│   └── app/
│       ├── layout.tsx               # Root layout + Convex provider
│       ├── page.tsx                 # Main dashboard (3-col grid)
│       ├── globals.css              # Base Tailwind styles
│       └── components/
│           ├── DigitalTwin.tsx      # Thermal heatmap (12×12 animated grid)
│           ├── CameraStreamCard.tsx # MJPEG viewer + fallback
│           ├── GhostLineChart.tsx   # Time-series temperature chart
│           ├── XRayCards.tsx        # Defect grid (image snapshots)
│           ├── ConnectionStatus.tsx # Device health indicator
│           └── ErrorBoundary.tsx    # React error catching
│
├── scripts/
│   ├── esp32-bridge.ts              # Main ingest bridge (polling + parsing)
│   ├── start-ingest.ts              # Wrapper to wire env vars + spawn bridge
│   └── generate-gear.ts             # GLTF model generation (fallback asset)
│
├── public/
│   └── models/
│       └── gear.gltf                # 3D fallback model (453KB)
│
├── arduino/
│   ├── CameraWebServer.ino          # Main firmware
│   ├── app_httpd.cpp                # HTTP server internals
│   └── board_config.h               # Board-specific config
│
├── package.json                     # Dependencies + npm scripts
├── tsconfig.json                    # TypeScript config
├── eslint.config.mjs                # ESLint rules
├── next.config.ts                   # Next.js config
├── postcss.config.mjs               # Tailwind build config
├── .env.local                       # Local env (Convex URLs, device IPs)
└── README.md                        # This file
```

---

## 🔧 Installation & Setup

### Prerequisites

- **Node.js** 18+ (tested with v24.14.0)
- **npm** 9+
- **ESP32-S3 hardware** (pre-flashed with thermal + camera firmware)
- **Local WiFi network** for ESP32 connectivity

### Step 1: Clone & Install Dependencies

```bash
git clone https://github.com/rchandrashekar53/Enduraverse-26.git
cd dreamvision
npm install
```

### Step 2: Configure Environment

Create/update `.env.local`:

```bash
# Convex deployment (auto-generated during `npx convex dev`)
CONVEX_DEPLOYMENT=anonymous:anonymous-dreamvision
NEXT_PUBLIC_CONVEX_URL=http://127.0.0.1:3210
NEXT_PUBLIC_CONVEX_SITE_URL=http://127.0.0.1:3211

# Device credentials
DEVICE_SECRET=dv_secret_2026

# Frontend camera URLs (customize for your ESP32 IP)
NEXT_PUBLIC_ESP32_CAMERA_URL=http://10.94.151.79
NEXT_PUBLIC_ESP32_STREAM_URL=http://10.94.151.79:81/stream
```

### Step 3: Start Services (3 Parallel Terminals)

**Terminal 1 — Convex Backend:**
```bash
npx convex dev
# Runs on :3210 (API) + :3211 (ingest)
```

**Terminal 2 — Next.js Frontend:**
```bash
npm run dev
# Runs on http://localhost:3000
```

**Terminal 3 — ESP32 Ingest Bridge:**
```bash
# Customize for your ESP32 IP if not 10.94.151.79
ESP_HOST=10.94.151.79 \
  THERMAL_URL=http://10.94.151.79:82/data \
  CAMERA_CAPTURE_URL=http://10.94.151.79/capture \
  POLL_MS=1000 \
  NOK_THRESHOLD=42 \
  npm run ingest:start
```

### Step 4: Verify

- **Dashboard:** http://localhost:3000
  - Thermal heatmap should animate
  - Camera stream should display (or error fallback)
  - Chart should populate as data arrives

---

## 🌡️ Hardware Setup

### ESP32-S3 Pinout

| Component | Pin | Protocol |
|-----------|-----|----------|
| OV3660 Camera | SDA/SCL | I2C |
| MLX90614 Thermal | SDA/SCL (shared) | I2C |
| Servo Scanner | GPIO 33 | PWM |

### Firmware Flashing

1. **Install Arduino IDE** + ESP32 board package
2. **Open** `arduino/CameraWebServer.ino`
3. **Select** board: `ESP32-S3-DevKitC-1`
4. **Upload** to device
5. **Verify endpoints:**
   ```bash
   curl http://<ESP32_IP>:81/stream          # MJPEG stream
   curl http://<ESP32_IP>/capture            # Still image
   curl http://<ESP32_IP>:82/data            # Thermal JSON
   ```

### Endpoints (Firmware)

| Endpoint | Port | Method | Response | Purpose |
|----------|------|--------|----------|---------|
| `/stream` | 81 | GET | MJPEG | Live video feed |
| `/capture` | 80 | GET | JPEG | Still frame snapshot |
| `/data` | 82 | GET | JSON | Thermal telemetry (minTemp, maxTemp, ambientTemp, status) |
| `/health` | 82 | GET | JSON | Device health check |

---

## 📊 API Reference

### Convex HTTP Ingest (`POST /ingest`)

**Request:**
```json
{
  "temp": 42.5,
  "status": "NOK",
  "minTemp": 20.1,
  "maxTemp": 45.8,
  "avgTemp": 35.2,
  "ambientTemp": 22.0,
  "imageBase64": "..."
}
```

**Response:**
```json
{
  "success": true
}
```

**Headers Required:**
```
x-device-secret: dv_secret_2026
Content-Type: application/json
```

---

## 🔌 Data Flow

1. **ESP32 Polls:** Every 1000ms, sensor array scans thermal grid + captures frame
2. **Bridge Fetches:** TypeScript bridge on local machine GETs `/data` from port 82
3. **Parse & Enrich:** Extracts minTemp/maxTemp/avgTemp; if temp ≥ 42°C, captures image
4. **POST to Convex:** Sends {temp, status, meta, image} to HTTP ingest with device secret
5. **Store:** Convex inserts reading into `telemetry` table; stores image blob if anomaly
6. **Frontend Subscribe:** React components use Convex hooks to listen for updates
7. **Render:** Dashboard re-renders heatmap colors, chart appends point, defect card appears

---

## 🚀 Deployment

### Production (Convex Cloud + Vercel)

```bash
# Deploy Convex backend
npx convex deploy

# Deploy Next.js frontend to Vercel
npm run build
vercel deploy --prod
```

Update `.env.production`:
```bash
NEXT_PUBLIC_CONVEX_URL=https://your-convex-url.convex.cloud
NEXT_PUBLIC_CONVEX_SITE_URL=https://your-convex-url.convex.cloud/ingest
```

---

## 🛠️ Development Commands

```bash
# Development
npm run dev              # Start Next.js dev server (3000)
npm run lint             # Run ESLint
npm run build            # Production build

# Backend
npx convex dev          # Start Convex local backend (3210, 3211)

# Hardware Bridge
npm run bridge:esp32    # Run ingest bridge (one-shot)
npm run ingest:start    # Run ingest wrapper (persistent)

# Asset Generation
npm run generate:gear   # Build GLTF fallback model
```

---

## 📝 Git Workflow

```bash
# View changes
git status

# Stage & commit
git add .
git commit -m "humanized one-liner message"

# Push to branch
git push origin feature-branch

# Create PR (on GitHub UI to Omega branch)
```

---

## 👥 Team & Credits

**Team Omega**  
Industrial IoT Monitoring · Hackathon Project · March 2026

### Contributors

- **Arjun (Lead Developer)** — Backend + Frontend Integration, Hardware Bridge
- **Team Omega** — Full Stack Architecture, Firmware Development

---

## 📄 License

MIT License — Feel free to fork, modify, and deploy.

---

**Built with ❤️ by Team Omega**  
*Turning sensor chaos into thermal clarity.*
