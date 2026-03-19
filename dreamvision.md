# dreamVision — Complete Technical Master Plan

> **Project Type:** Industrial IoT Dashboard  
> **Hardware:** ESP32-S3 + GY-906 (IR Temp) + OV3660 (Camera)  
> **Backend:** Convex (Local Dev → Cloud Deploy)  
> **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind CSS  
> **Status:** Planning Phase — Pre-Code  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Tech Stack](#2-tech-stack)
3. [Data Flow Architecture](#3-data-flow-architecture)
4. [Project Structure](#4-project-structure)
5. [Phase 1 — Convex Backend](#5-phase-1--convex-backend)
6. [Phase 2 — Next.js Frontend](#6-phase-2--nextjs-frontend)
7. [Phase 3 — ESP32 Firmware](#7-phase-3--esp32-firmware)
8. [Environment Variables](#8-environment-variables)
9. [Build Order & Session Map](#9-build-order--session-map)
10. [Testing Strategy](#10-testing-strategy)
11. [Known Risks & Mitigations](#11-known-risks--mitigations)
12. [Demo Day Checklist](#12-demo-day-checklist)

---

## 1. System Overview

dreamVision is a real-time industrial defect detection and thermal monitoring system. An ESP32-S3 edge node reads temperature from a GY-906 IR sensor and captures defect frames from an OV3660 camera. Data is pushed to a Convex backend every 500ms via HTTP POST and rendered live on a Next.js dashboard — no Pi 5, no intermediary server.

### Three "Wow" Features

| Feature | What Judges See |
|---|---|
| **Predictive Ghost Line** | Live temp chart with a dashed forecasted trajectory. Pulses red if it crosses 45°C |
| **Digital Twin** | 3D machine part that glows yellow → red based on live temperature |
| **X-Ray Incident Cards** | CSS-filtered grayscale+invert snapshot cards logged when a defect is detected |

---

## 2. Tech Stack

### Backend

| Layer | Technology | Reason |
|---|---|---|
| Realtime DB + API | Convex | Built-in WebSocket sync, HTTP Actions, File Storage |
| Language | TypeScript | Type safety across convex/ and frontend |
| Auth (device) | Shared secret header | Sufficient for hackathon, easy to implement |

### Frontend

| Layer | Technology | Reason |
|---|---|---|
| Framework | Next.js 14 (App Router) | Modern, Server Components, easy Vercel deploy |
| Styling | Tailwind CSS | Rapid utility styling, animation classes built-in |
| Charts | Recharts | Composable, works well with React state |
| 3D Rendering | @react-three/fiber + @react-three/drei | React-idiomatic Three.js wrapper |
| Real-time | Convex `useQuery` | WebSocket push — no polling needed |

### Hardware

| Component | Role |
|---|---|
| ESP32-S3 | Edge node — reads sensors, sends HTTP POST |
| GY-906 (MLX90614) | Non-contact IR temperature sensor |
| OV3660 | Camera module for defect frame capture |

---

## 3. Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ESP32-S3 Edge Node                       │
│                                                                 │
│  GY-906 ──► temp (float)  ─┐                                   │
│                             ├──► JSON payload ──► HTTP POST    │
│  OV3660 ──► status (string)┘         every 500ms              │
│             + Base64 frame (on NOK only)                        │
└────────────────────────────────┬────────────────────────────────┘
                                 │ POST /ingest
                                 │ Header: x-device-secret
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Convex HTTP Action                         │
│                                                                 │
│  1. Validate secret header                                      │
│  2. Parse + validate JSON body                                  │
│  3. Stamp server-side timestamp                                 │
│  4. Call insertReading mutation                                  │
│  5. If status == NOK: store image → logDefect mutation         │
└────────────────────────────────┬────────────────────────────────┘
                                 │ ctx.db.insert()
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Convex Database                         │
│                                                                 │
│   telemetry table (rolling 100 rows)                           │
│   defects table (permanent, storageId refs)                    │
│   _storage (Convex File Storage for images)                    │
└────────────────────────────────┬────────────────────────────────┘
                                 │ WebSocket push (automatic)
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Next.js Dashboard (Browser)                  │
│                                                                 │
│  useQuery("telemetry:getLatest")    → ConnectionStatus         │
│                                     → DigitalTwin (3D glow)   │
│  useQuery("telemetry:getLast20")    → GhostLineChart           │
│  useQuery("defects:getAll")         → XRayCard list           │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Server-side timestamp:** ESP32 clocks drift. Timestamp is always applied on Convex ingestion, not at the device.
- **Convex Storage for images:** Documents have ~1MB limit. Base64 images would overflow. `storageId` reference is the correct pattern.
- **Rolling 100-row window:** Prevents unbounded telemetry growth. Auto-pruned on every insert mutation.
- **Single HTTP endpoint:** ESP32 sends one POST. Convex decides internally whether to also log a defect (if status == "NOK").

---

## 4. Project Structure

```
dreamvision/
│
├── convex/                        ← Convex backend (auto-deployed by CLI)
│   ├── schema.ts                  ← Table definitions
│   ├── http.ts                    ← HTTP Action: POST /ingest
│   ├── telemetry.ts               ← insertReading mutation, getLast20/getLatest queries
│   ├── defects.ts                 ← logDefect mutation, getAll query (with URLs)
│   └── _generated/                ← Auto-generated by Convex CLI (never edit)
│
├── app/                           ← Next.js App Router
│   ├── layout.tsx                 ← ConvexClientProvider wraps everything here
│   ├── page.tsx                   ← Main dashboard — composes all components
│   └── components/
│       ├── GhostLineChart.tsx     ← Recharts + linear regression forecast
│       ├── DigitalTwin.tsx        ← react-three/fiber 3D model
│       ├── XRayCard.tsx           ← Defect incident card with CSS filters
│       └── ConnectionStatus.tsx   ← Stale data warning indicator
│
├── lib/
│   └── forecast.ts                ← Linear regression helper (pure function)
│
├── public/
│   └── models/
│       └── gear.gltf              ← 3D model for Digital Twin
│
├── .env.local                     ← DEVICE_SECRET + NEXT_PUBLIC_CONVEX_URL
├── convex.json                    ← Auto-generated by Convex CLI
└── package.json
```

---

## 5. Phase 1 — Convex Backend

### 5.1 `convex/schema.ts`

Two tables. `telemetry` is a rolling window of live sensor data. `defects` is a permanent audit log with references to stored images — never base64 strings.

```typescript
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  telemetry: defineTable({
    temp: v.number(),
    status: v.string(),    // "OK" | "NOK"
    timestamp: v.number(), // Unix ms — set server-side
  }),

  defects: defineTable({
    storageId: v.id("_storage"), // Convex File Storage reference
    heatSignature: v.number(),
    timeDetected: v.string(),    // ISO 8601 string
  }),
});
```

### 5.2 `convex/telemetry.ts`

Three exports: one mutation, two queries.

```typescript
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Called by HTTP Action on every ESP32 POST
export const insertReading = mutation({
  args: {
    temp: v.number(),
    status: v.string(),
    timestamp: v.number(),
  },
  handler: async (ctx, args) => {
    await ctx.db.insert("telemetry", {
      temp: args.temp,
      status: args.status,
      timestamp: args.timestamp,
    });

    // Auto-prune: keep only latest 100 rows
    const all = await ctx.db
      .query("telemetry")
      .order("desc")
      .collect();

    if (all.length > 100) {
      const toDelete = all.slice(100);
      for (const row of toDelete) {
        await ctx.db.delete(row._id);
      }
    }
  },
});

// For GhostLineChart — returns newest-first, reverse on frontend
export const getLast20 = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("telemetry")
      .order("desc")
      .take(20);
  },
});

// For DigitalTwin + ConnectionStatus
export const getLatest = query({
  args: {},
  handler: async (ctx) => {
    return await ctx.db
      .query("telemetry")
      .order("desc")
      .first(); // null if table is empty
  },
});
```

### 5.3 `convex/defects.ts`

Stores defect events with image URLs resolved server-side.

```typescript
import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

export const logDefect = mutation({
  args: {
    storageId: v.id("_storage"),
    heatSignature: v.number(),
    timeDetected: v.string(),
  },
  handler: async (ctx, args) => {
    await ctx.db.insert("defects", {
      storageId: args.storageId,
      heatSignature: args.heatSignature,
      timeDetected: args.timeDetected,
    });
  },
});

// Returns defects with resolved image URLs for <img src>
export const getAll = query({
  args: {},
  handler: async (ctx) => {
    const defects = await ctx.db
      .query("defects")
      .order("desc")
      .collect();

    return await Promise.all(
      defects.map(async (defect) => {
        const imageUrl = await ctx.storage.getUrl(defect.storageId);
        return { ...defect, imageUrl }; // imageUrl is string | null
      })
    );
  },
});
```

### 5.4 `convex/http.ts`

The single public endpoint. ESP32 POSTs here. Handles auth, validation, and routing to mutations.

```typescript
import { httpRouter } from "convex/server";
import { httpAction } from "./_generated/server";
import { api } from "./_generated/api";

const http = httpRouter();

http.route({
  path: "/ingest",
  method: "POST",
  handler: httpAction(async (ctx, request) => {

    // ── 1. Auth check ─────────────────────────────────────────
    const secret = request.headers.get("x-device-secret");
    if (secret !== process.env.DEVICE_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    // ── 2. Parse body ─────────────────────────────────────────
    let body: { temp: unknown; status: unknown; imageBase64?: unknown };
    try {
      body = await request.json();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    // ── 3. Validate ───────────────────────────────────────────
    if (typeof body.temp !== "number") {
      return new Response("temp must be a number", { status: 422 });
    }
    if (body.status !== "OK" && body.status !== "NOK") {
      return new Response("status must be 'OK' or 'NOK'", { status: 422 });
    }

    // ── 4. Write telemetry ────────────────────────────────────
    const serverTimestamp = Date.now(); // Always stamp server-side

    await ctx.runMutation(api.telemetry.insertReading, {
      temp: body.temp as number,
      status: body.status as string,
      timestamp: serverTimestamp,
    });

    // ── 5. If NOK + image provided → store image + log defect ─
    if (body.status === "NOK" && typeof body.imageBase64 === "string") {
      const imageBytes = Buffer.from(body.imageBase64, "base64");
      const blob = new Blob([imageBytes], { type: "image/jpeg" });
      const storageId = await ctx.storage.store(blob);

      await ctx.runMutation(api.defects.logDefect, {
        storageId,
        heatSignature: body.temp as number,
        timeDetected: new Date(serverTimestamp).toISOString(),
      });
    }

    return new Response(JSON.stringify({ success: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
});

export default http;
```

---

## 6. Phase 2 — Next.js Frontend

### 6.1 `app/layout.tsx` — Provider Setup

```typescript
import { ConvexClientProvider } from "./ConvexClientProvider";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ConvexClientProvider>{children}</ConvexClientProvider>
      </body>
    </html>
  );
}
```

```typescript
// app/ConvexClientProvider.tsx
"use client";
import { ConvexProvider, ConvexReactClient } from "convex/react";

const convex = new ConvexReactClient(process.env.NEXT_PUBLIC_CONVEX_URL!);

export function ConvexClientProvider({ children }: { children: React.ReactNode }) {
  return <ConvexProvider client={convex}>{children}</ConvexProvider>;
}
```

### 6.2 `lib/forecast.ts` — Linear Regression

Pure function. No dependencies. Returns projected temperature values for the ghost line.

```typescript
/**
 * Projects future temperature values using least-squares linear regression.
 * @param readings  Array of temperature numbers (chronological order)
 * @param stepsAhead  How many future data points to project
 * @returns Array of projected temperatures
 */
export function projectTemperature(readings: number[], stepsAhead = 10): number[] {
  const n = readings.length;
  if (n < 2) return [];

  const xMean = (n - 1) / 2;
  const yMean = readings.reduce((a, b) => a + b, 0) / n;

  const numerator = readings.reduce((acc, y, x) => acc + (x - xMean) * (y - yMean), 0);
  const denominator = readings.reduce((acc, _, x) => acc + (x - xMean) ** 2, 0);
  const slope = denominator === 0 ? 0 : numerator / denominator;

  return Array.from({ length: stepsAhead }, (_, i) =>
    yMean + slope * (n + i - xMean)
  );
}
```

### 6.3 `app/components/ConnectionStatus.tsx`

```typescript
"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

export function ConnectionStatus() {
  const latest = useQuery(api.telemetry.getLatest);
  const isStale = !latest || Date.now() - latest.timestamp > 3000;

  return (
    <div className={`flex items-center gap-2 text-sm font-mono ${isStale ? "text-red-400" : "text-green-400"}`}>
      <span className={`w-2 h-2 rounded-full ${isStale ? "bg-red-400" : "bg-green-400 animate-pulse"}`} />
      {isStale ? "⚠ Signal Lost" : "● Live"}
    </div>
  );
}
```

### 6.4 `app/components/GhostLineChart.tsx`

```typescript
"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { ComposedChart, Line, XAxis, YAxis, ReferenceLine, Tooltip, ResponsiveContainer } from "recharts";
import { projectTemperature } from "@/lib/forecast";

const DANGER_THRESHOLD = 45;

export function GhostLineChart() {
  const raw = useQuery(api.telemetry.getLast20) ?? [];
  const readings = [...raw].reverse(); // oldest first for chart

  const actualData = readings.map((r, i) => ({ x: i, temp: r.temp }));

  const temps = readings.map((r) => r.temp);
  const projected = projectTemperature(temps, 10);
  const ghostData = projected.map((temp, i) => ({ x: readings.length + i, ghost: temp }));

  const allData = actualData.map((d, i) => ({ ...d, ghost: ghostData[i]?.ghost }));
  const fullData = [...allData, ...ghostData.slice(actualData.length)];

  const willOverheat = projected.some((t) => t >= DANGER_THRESHOLD);

  return (
    <div className={`rounded-xl p-4 transition-all duration-700 ${willOverheat ? "animate-pulse bg-red-900/20 border border-red-500/40" : "bg-zinc-900 border border-zinc-700"}`}>
      <p className="text-xs text-zinc-400 mb-2 font-mono uppercase tracking-widest">
        Thermal Trajectory {willOverheat && "⚠ CRITICAL FORECAST"}
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={fullData}>
          <XAxis dataKey="x" hide />
          <YAxis domain={[20, 60]} tick={{ fill: "#71717a", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
            labelFormatter={() => ""}
          />
          <ReferenceLine y={DANGER_THRESHOLD} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "45°C", fill: "#ef4444", fontSize: 10 }} />
          <Line type="monotone" dataKey="temp" stroke="#f97316" strokeWidth={2} dot={false} name="Actual" />
          <Line type="monotone" dataKey="ghost" stroke="#f97316" strokeWidth={1.5} strokeDasharray="5 5" strokeOpacity={0.4} dot={false} name="Forecast" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### 6.5 `app/components/DigitalTwin.tsx`

```typescript
"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, useGLTF } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";

function resolveGlowColor(temp: number): THREE.Color {
  if (temp > 40) return new THREE.Color("#ef4444"); // red
  if (temp > 35) return new THREE.Color("#eab308"); // yellow
  return new THREE.Color("#374151");                 // gray
}

function resolveGlowIntensity(temp: number): number {
  if (temp > 40) return 1.5;
  if (temp > 35) return 0.6;
  return 0;
}

function Model({ temp }: { temp: number }) {
  const { scene } = useGLTF("/models/gear.gltf");
  const color = useMemo(() => resolveGlowColor(temp), [temp]);
  const intensity = useMemo(() => resolveGlowIntensity(temp), [temp]);

  scene.traverse((child) => {
    if ((child as THREE.Mesh).isMesh) {
      const mesh = child as THREE.Mesh;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.emissive = color;
      mat.emissiveIntensity = intensity;
      mat.needsUpdate = true;
    }
  });

  return <primitive object={scene} />;
}

export function DigitalTwin() {
  const latest = useQuery(api.telemetry.getLatest);
  const temp = latest?.temp ?? 25;

  return (
    <div className="rounded-xl bg-zinc-900 border border-zinc-700 p-4 h-72">
      <p className="text-xs text-zinc-400 mb-2 font-mono uppercase tracking-widest">
        Digital Twin — {temp.toFixed(1)}°C
      </p>
      <Canvas camera={{ position: [0, 0, 3] }}>
        <ambientLight intensity={0.3} />
        <pointLight position={[10, 10, 10]} />
        <Model temp={temp} />
        <OrbitControls enableZoom={false} autoRotate autoRotateSpeed={1.5} />
      </Canvas>
    </div>
  );
}
```

### 6.6 `app/components/XRayCard.tsx`

```typescript
"use client";
import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";

export function XRayCards() {
  const defects = useQuery(api.defects.getAll) ?? [];

  if (defects.length === 0) {
    return (
      <div className="rounded-xl bg-zinc-900 border border-zinc-700 p-6 text-center text-zinc-500 font-mono text-sm">
        No defects logged. System nominal.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {defects.map((defect) => (
        <div key={defect._id} className="rounded-xl bg-zinc-900 border border-red-900/40 p-4">
          <div className="flex justify-between items-start mb-3">
            <span className="text-red-400 text-xs font-mono font-bold uppercase tracking-widest">
              ⚠ Defect Detected
            </span>
            <span className="text-zinc-500 text-xs font-mono">
              {new Date(defect.timeDetected).toLocaleTimeString()}
            </span>
          </div>

          {defect.imageUrl && (
            <img
              src={defect.imageUrl}
              alt="Defect X-Ray frame"
              className="w-full rounded-lg mb-3"
              style={{
                filter: "invert(1) contrast(1.5) grayscale(1) sepia(1) hue-rotate(180deg)",
              }}
            />
          )}

          <p className="text-zinc-300 text-sm font-mono">
            Heat Signature: <span className="text-orange-400">{defect.heatSignature.toFixed(1)}°C</span>
          </p>
        </div>
      ))}
    </div>
  );
}
```

---

## 7. Phase 3 — ESP32 Firmware

### Payload Shape — Normal Reading (Status OK)

```json
{
  "temp": 37.4,
  "status": "OK"
}
```

### Payload Shape — Defect Detected (Status NOK)

```json
{
  "temp": 42.1,
  "status": "NOK",
  "imageBase64": "/9j/4AAQSkZJRgABAQAA..."
}
```

### Arduino Pseudocode

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* SSID        = "YOUR_WIFI_SSID";
const char* PASSWORD    = "YOUR_WIFI_PASSWORD";
const char* SERVER_URL  = "http://192.168.1.10:3210/ingest"; // Your machine's LAN IP
const char* DEVICE_SECRET = "dv_secret_2026";

void setup() {
  Serial.begin(115200);
  WiFi.begin(SSID, PASSWORD);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println("WiFi connected");
}

void loop() {
  float temp = readGY906();               // Your MLX90614 read function
  bool defectDetected = checkOV3660();    // Your OV3660 anomaly detection

  StaticJsonDocument<8192> doc;
  doc["temp"]   = temp;
  doc["status"] = defectDetected ? "NOK" : "OK";

  if (defectDetected) {
    String b64 = captureFrameAsBase64(); // Your capture + encode function
    doc["imageBase64"] = b64;
  }

  String payload;
  serializeJson(doc, payload);

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("x-device-secret", DEVICE_SECRET);

  int code = http.POST(payload);
  Serial.printf("Response: %d\n", code);
  http.end();

  delay(500); // 500ms interval
}
```

### Local IP Discovery (Run on your laptop)

```bash
# macOS / Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig
```

---

## 8. Environment Variables

### `.env.local` (project root)

```bash
NEXT_PUBLIC_CONVEX_URL=http://127.0.0.1:3210
DEVICE_SECRET=dv_secret_2026
```

### Rules

| Variable | Prefix | Accessible In |
|---|---|---|
| `NEXT_PUBLIC_CONVEX_URL` | `NEXT_PUBLIC_` | Browser (ConvexClientProvider) |
| `DEVICE_SECRET` | none | Convex backend only (never exposed to browser) |

> **Never put DEVICE_SECRET in a variable starting with NEXT_PUBLIC_.**  
> Convex HTTP Actions read it via `process.env.DEVICE_SECRET` — it stays server-side.

---

## 9. Build Order & Session Map

### Session 1 — Backend Foundation (Current)

- [x] Scaffold Next.js + install Convex
- [ ] `convex/schema.ts`
- [ ] `convex/telemetry.ts`
- [ ] `convex/defects.ts`
- [ ] `convex/http.ts`
- [ ] `.env.local`
- [ ] Verify with curl

### Session 2 — Frontend Foundation

- [ ] `app/ConvexClientProvider.tsx`
- [ ] `app/layout.tsx` (wrap with provider)
- [ ] `app/components/ConnectionStatus.tsx`
- [ ] `app/page.tsx` (layout scaffold only)

### Session 3 — Ghost Line Chart

- [ ] `lib/forecast.ts`
- [ ] `app/components/GhostLineChart.tsx`
- [ ] Wire to `page.tsx`
- [ ] Test pulse animation at 45°C

### Session 4 — Digital Twin

- [ ] Install `@react-three/fiber` `@react-three/drei`
- [ ] Source or create `gear.gltf` model
- [ ] `app/components/DigitalTwin.tsx`
- [ ] Test glow color transitions

### Session 5 — X-Ray Cards

- [ ] `app/components/XRayCard.tsx`
- [ ] Test CSS filter stack
- [ ] End-to-end: curl with `imageBase64` → defect appears on dashboard

### Session 6 — Polish + ESP32 Integration

- [ ] Flash ESP32 firmware
- [ ] Replace mock curl with live hardware
- [ ] Final layout pass + responsiveness
- [ ] Connection status tested with device off

---

## 10. Testing Strategy

### Backend — curl Tests

```bash
# ✅ Valid telemetry POST
curl -X POST http://127.0.0.1:3210/ingest \
  -H "Content-Type: application/json" \
  -H "x-device-secret: dv_secret_2026" \
  -d '{"temp": 38.5, "status": "OK"}'
# Expected: {"success":true}

# ❌ Wrong secret
curl -X POST http://127.0.0.1:3210/ingest \
  -H "Content-Type: application/json" \
  -H "x-device-secret: wrong" \
  -d '{"temp": 38.5, "status": "OK"}'
# Expected: 401 Unauthorized

# ❌ Invalid status value
curl -X POST http://127.0.0.1:3210/ingest \
  -H "Content-Type: application/json" \
  -H "x-device-secret: dv_secret_2026" \
  -d '{"temp": 38.5, "status": "MAYBE"}'
# Expected: 422 status must be 'OK' or 'NOK'

# ❌ Non-number temperature
curl -X POST http://127.0.0.1:3210/ingest \
  -H "Content-Type: application/json" \
  -H "x-device-secret: dv_secret_2026" \
  -d '{"temp": "hot", "status": "OK"}'
# Expected: 422 temp must be a number

# ✅ Defect POST with image (simulate NOK)
curl -X POST http://127.0.0.1:3210/ingest \
  -H "Content-Type: application/json" \
  -H "x-device-secret: dv_secret_2026" \
  -d '{"temp": 43.2, "status": "NOK", "imageBase64": "/9j/4AAQ..."}'
# Expected: {"success":true} + row in defects table
```

### Frontend Smoke Tests

| Test | Expected Result |
|---|---|
| Open dashboard with no data | ConnectionStatus shows "⚠ Signal Lost" |
| Send valid curl POST | Telemetry row appears in Convex dashboard instantly |
| Watch `getLast20` | Chart updates without page refresh |
| Temp > 35 | Digital Twin glows yellow |
| Temp > 40 | Digital Twin pulses red |
| Ghost line crosses 45°C | Dashboard container pulses red |
| Send NOK POST | XRayCard appears with filtered image |

---

## 11. Known Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ESP32 loses WiFi during demo | High | High | ConnectionStatus indicator + `animate-pulse` makes it look intentional |
| OV3660 base64 frame too large | Medium | High | Compress frame to QVGA (320×240) on device before encoding |
| `convex dev` crashes locally | Low | High | Keep cloud Convex project as fallback, switch `CONVEX_URL` |
| 3D model `.gltf` not loading | Medium | Medium | Have a pure CSS fallback (animated div with radial gradient glow) |
| Demo machine has no internet | Low | Medium | Local Convex = no internet needed for backend |
| Telemetry table query slow | Low | Low | Rolling 100-row window prevents this entirely |

---

## 12. Demo Day Checklist

### 30 Minutes Before

- [ ] `npx convex dev` running in Terminal 1
- [ ] `npm run dev` running in Terminal 2
- [ ] Dashboard open at `http://localhost:3000`
- [ ] ESP32 powered and on same WiFi as laptop
- [ ] One manual curl POST sent — confirm telemetry row appears

### During Demo

- [ ] Show live temperature updating in real-time (no page refresh)
- [ ] Point at the ghost line — explain "least-squares thermal trajectory forecasting"
- [ ] Let the 3D twin rotate — it's the most visually striking moment
- [ ] Trigger a NOK reading (either from device or curl) — show the X-Ray card appear live

### Killer Demo Line

> *"Every 500ms, edge telemetry hits our Convex backend — no polling, no intermediary server. The moment the database changes, WebSocket sync pushes it to every client. What you're seeing is true real-time, not refresh intervals."*

---

*Generated: March 2026 | dreamVision Technical Plan v1.0*