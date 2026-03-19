#!/usr/bin/env node

/**
 * One-command script to wire thermal JSON endpoint + bridge ingest together
 * Sets up all env vars and spawns the esp32-bridge subprocess
 * 
 * Usage: npm run ingest:start
 * Or: POLL_MS=2000 npm run ingest:start (override polling)
 */

import { spawn } from "child_process";
import path from "path";

const ESP_HOST = process.env.ESP_HOST || "10.141.17.79";
const DEVICE_SECRET = process.env.DEVICE_SECRET || "dv_secret_2026";
const THERMAL_URL = process.env.THERMAL_URL || `http://${ESP_HOST}:82/data`;
const CAMERA_CAPTURE_URL =
  process.env.CAMERA_CAPTURE_URL || `http://${ESP_HOST}/capture`;
const INGEST_URL = process.env.INGEST_URL || "http://127.0.0.1:3211/ingest";
const POLL_MS = process.env.POLL_MS || "1000";
const NOK_THRESHOLD = process.env.NOK_THRESHOLD || "42";

console.log("🌡️  Starting thermal + camera ingest pipeline...");
console.log(`   ESP32 host: ${ESP_HOST}`);
console.log(`   Thermal endpoint: ${THERMAL_URL}`);
console.log(`   Camera capture: ${CAMERA_CAPTURE_URL}`);
console.log(`   Ingest endpoint: ${INGEST_URL}`);
console.log(`   Poll interval: ${POLL_MS}ms`);
console.log(`   NOK threshold: ${NOK_THRESHOLD}°C\n`);

const bridgeProcess = spawn(
  "npx",
  ["tsx", path.join(__dirname, "esp32-bridge.ts")],
  {
    env: {
      ...process.env,
      DEVICE_SECRET,
      ESP_HOST,
      THERMAL_URL,
      CAMERA_CAPTURE_URL,
      INGEST_URL,
      POLL_MS,
      NOK_THRESHOLD,
    },
    stdio: "inherit",
    shell: true,
  }
);

bridgeProcess.on("error", (err) => {
  console.error("❌ Bridge process error:", err);
  process.exit(1);
});

bridgeProcess.on("exit", (code) => {
  console.log(`\n🛑 Bridge stopped with exit code ${code}`);
  process.exit(code);
});

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("\n🛑 Terminating ingest pipeline...");
  bridgeProcess.kill("SIGTERM");
});
