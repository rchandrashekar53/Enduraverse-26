import { execFile } from "node:child_process";
import { promisify } from "node:util";

type JsonRecord = Record<string, unknown>;

const execFileAsync = promisify(execFile);

const ESP_HOST = process.env.ESP_HOST ?? "10.141.17.79";
const THERMAL_URL = process.env.THERMAL_URL ?? `http://${ESP_HOST}:82/data`;
const CAMERA_CAPTURE_URL = process.env.CAMERA_CAPTURE_URL ?? `http://${ESP_HOST}/capture`;
const INGEST_URL = process.env.INGEST_URL ?? "http://127.0.0.1:3211/ingest";
const DEVICE_SECRET = process.env.DEVICE_SECRET ?? "";
const POLL_MS = Number(process.env.POLL_MS ?? "4000");
const NOK_THRESHOLD = Number(process.env.NOK_THRESHOLD ?? "42");
const REQUEST_TIMEOUT_MS = Number(process.env.REQUEST_TIMEOUT_MS ?? "8000");
const RUN_ONCE = process.env.RUN_ONCE === "1";

if (!DEVICE_SECRET) {
  console.error("DEVICE_SECRET is required. Export it before running the bridge.");
  process.exit(1);
}

if (Number.isNaN(POLL_MS) || POLL_MS < 100) {
  console.error("POLL_MS must be a number >= 100.");
  process.exit(1);
}

function withTimeoutSignal(timeoutMs: number): AbortSignal {
  return AbortSignal.timeout(timeoutMs);
}

function extractTemperature(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string") {
    const numeric = Number.parseFloat(value.trim());
    return Number.isFinite(numeric) ? numeric : null;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const parsed = extractTemperature(item);
      if (parsed !== null) {
        return parsed;
      }
    }
    return null;
  }

  if (value && typeof value === "object") {
    const obj = value as JsonRecord;

    const preferredKeys = [
      "maxTemp",
      "avgTemp",
      "minTemp",
      "temp",
      "temperature",
      "objectTemp",
      "object_temp",
      "mlxTemp",
      "mlx_temperature",
      "ambientTemp",
      "ambient_temp",
      "value",
      "reading",
      "current",
      "data",
    ];

    for (const key of preferredKeys) {
      if (key in obj) {
        const parsed = extractTemperature(obj[key]);
        if (parsed !== null) {
          return parsed;
        }
      }
    }

    for (const nestedValue of Object.values(obj)) {
      if (nestedValue && (Array.isArray(nestedValue) || typeof nestedValue === "object")) {
        const parsed = extractTemperature(nestedValue);
        if (parsed !== null) {
          return parsed;
        }
      }
    }
  }

  return null;
}

function parseCelsius(text: string): number | null {
  const normalized = text.replace(/&nbsp;/g, " ").trim();
  const match = normalized.match(/-?\d+(?:\.\d+)?/);
  if (!match) {
    return null;
  }

  const parsed = Number.parseFloat(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function parseJsonLenient(raw: string): unknown | null {
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    // Some firmware emits non-standard JSON tokens (e.g. avgTemp:nan).
    const normalized = raw
      .replace(/:\s*nan\b/gi, ":null")
      .replace(/:\s*\+?inf(inity)?\b/gi, ":null")
      .replace(/:\s*-inf(inity)?\b/gi, ":null");

    try {
      return JSON.parse(normalized) as unknown;
    } catch {
      return null;
    }
  }
}

function extractTemperatureFromThermalHtml(html: string): number | null {
  const statMatches = [
    ...html.matchAll(
      /<span class='sv'[^>]*>([^<]+)<\/span><span class='sl'>([^<]+)<\/span>/g,
    ),
  ];

  const stats: Record<string, number> = {};

  for (const match of statMatches) {
    const valueRaw = match[1] ?? "";
    const labelRaw = (match[2] ?? "").toUpperCase();
    const value = parseCelsius(valueRaw);
    if (value === null || Number.isNaN(value)) {
      continue;
    }

    stats[labelRaw] = value;
  }

  // Prefer hottest meaningful signal for defect monitoring.
  const preferredLabels = ["MAX", "AVG OBJ", "AMBIENT"];
  for (const label of preferredLabels) {
    if (label in stats) {
      return stats[label];
    }
  }

  // Fallback: derive max object temp from grid cell titles.
  const objectTemps = [
    ...html.matchAll(/\|\s*(-?\d+(?:\.\d+)?)°C obj\s*\|/g),
  ]
    .map((match) => Number.parseFloat(match[1]))
    .filter((value) => Number.isFinite(value));

  if (objectTemps.length > 0) {
    return Math.max(...objectTemps);
  }

  return null;
}

async function readThermal(): Promise<{
  temp: number;
  minTemp?: number;
  maxTemp?: number;
  avgTemp?: number;
  ambientTemp?: number;
} | null> {
  let contentType = "";
  let raw = "";

  try {
    const response = await fetch(THERMAL_URL, {
      method: "GET",
      signal: withTimeoutSignal(REQUEST_TIMEOUT_MS),
    });

    if (!response.ok) {
      throw new Error(`Thermal endpoint returned ${response.status}`);
    }

    contentType = response.headers.get("content-type") ?? "";

    raw = (await response.text()).trim();

    if (contentType.includes("application/json")) {
      const json = parseJsonLenient(raw);
      if (json !== null && typeof json === "object") {
        const obj = json as Record<string, unknown>;
        const temp = extractTemperature(obj);
        if (temp !== null) {
          return {
            temp,
            minTemp: typeof obj.minTemp === "number" ? obj.minTemp : undefined,
            maxTemp: typeof obj.maxTemp === "number" ? obj.maxTemp : undefined,
            avgTemp: typeof obj.avgTemp === "number" && Number.isFinite(obj.avgTemp) ? obj.avgTemp : undefined,
            ambientTemp: typeof obj.ambientTemp === "number" ? obj.ambientTemp : undefined,
          };
        }
      }
    }
  } catch (fetchError) {
    // Fallback to curl because it can return partial payloads even on timeout.
    try {
      const { stdout } = await execFileAsync("curl", [
        "-sS",
        "--connect-timeout",
        String(Math.max(1, Math.floor(REQUEST_TIMEOUT_MS / 1000))),
        "--max-time",
        String(Math.max(2, Math.floor(REQUEST_TIMEOUT_MS / 1000))),
        THERMAL_URL,
      ]);
      raw = stdout.trim();
      contentType = raw.startsWith("{") || raw.startsWith("[") ? "application/json" : "text/html";
    } catch (curlError) {
      const errorWithStdout = curlError as { stdout?: string };
      if (errorWithStdout.stdout && errorWithStdout.stdout.trim().length > 0) {
        raw = errorWithStdout.stdout.trim();
        contentType = raw.startsWith("{") || raw.startsWith("[") ? "application/json" : "text/html";
      } else {
        throw fetchError;
      }
    }
  }

  if (raw.length === 0) {
    return null;
  }

  if (contentType.includes("text/html") || raw.startsWith("<!DOCTYPE html")) {
    const fromHtml = extractTemperatureFromThermalHtml(raw);
    if (fromHtml !== null) {
      return { temp: fromHtml };
    }
  }

  const maybeJson = parseJsonLenient(raw);
  if (maybeJson !== null && typeof maybeJson === "object") {
    const obj = maybeJson as Record<string, unknown>;
    const parsed = extractTemperature(obj);
    if (parsed !== null) {
      return {
        temp: parsed,
        minTemp: typeof obj.minTemp === "number" ? obj.minTemp : undefined,
        maxTemp: typeof obj.maxTemp === "number" ? obj.maxTemp : undefined,
        avgTemp: typeof obj.avgTemp === "number" && Number.isFinite(obj.avgTemp) ? obj.avgTemp : undefined,
        ambientTemp: typeof obj.ambientTemp === "number" ? obj.ambientTemp : undefined,
      };
    }
  }

  const asNumber = Number.parseFloat(raw);
  return Number.isFinite(asNumber) ? { temp: asNumber } : null;
}

async function captureImageBase64(): Promise<string | null> {
  const response = await fetch(CAMERA_CAPTURE_URL, {
    method: "GET",
    signal: withTimeoutSignal(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(`Capture endpoint returned ${response.status}`);
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("image/")) {
    throw new Error(`Capture endpoint did not return an image (${contentType || "unknown"})`);
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  return buffer.toString("base64");
}

async function postToConvex(
  temp: number,
  status: "OK" | "NOK",
  imageBase64?: string,
  minTemp?: number,
  maxTemp?: number,
  avgTemp?: number,
  ambientTemp?: number,
): Promise<void> {
  const payload: {
    temp: number;
    status: "OK" | "NOK";
    imageBase64?: string;
    minTemp?: number;
    maxTemp?: number;
    avgTemp?: number;
    ambientTemp?: number;
  } = {
    temp,
    status,
  };

  if (imageBase64) {
    payload.imageBase64 = imageBase64;
  }
  if (minTemp !== undefined) {
    payload.minTemp = minTemp;
  }
  if (maxTemp !== undefined) {
    payload.maxTemp = maxTemp;
  }
  if (avgTemp !== undefined) {
    payload.avgTemp = avgTemp;
  }
  if (ambientTemp !== undefined) {
    payload.ambientTemp = ambientTemp;
  }

  const response = await fetch(INGEST_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-device-secret": DEVICE_SECRET,
    },
    body: JSON.stringify(payload),
    signal: withTimeoutSignal(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Ingest failed (${response.status}): ${body}`);
  }
}

async function tick(): Promise<void> {
  const thermalData = await readThermal();

  if (thermalData === null || thermalData.temp === null) {
    throw new Error("Could not parse temperature from thermal response");
  }

  const status: "OK" | "NOK" = thermalData.temp >= NOK_THRESHOLD ? "NOK" : "OK";
  let imageBase64: string | undefined;

  if (status === "NOK") {
    try {
      imageBase64 = (await captureImageBase64()) ?? undefined;
    } catch (error) {
      console.warn(`[bridge] Image capture failed: ${(error as Error).message}`);
    }
  }

  await postToConvex(
    thermalData.temp,
    status,
    imageBase64,
    thermalData.minTemp,
    thermalData.maxTemp,
    thermalData.avgTemp,
    thermalData.ambientTemp,
  );
  console.log(
    `[bridge] posted temp=${thermalData.temp.toFixed(2)} status=${status}${imageBase64 ? " +image" : ""}`,
  );
}

console.log("[bridge] starting ESP32 -> Convex bridge");
console.log(`[bridge] thermal=${THERMAL_URL}`);
console.log(`[bridge] capture=${CAMERA_CAPTURE_URL}`);
console.log(`[bridge] ingest=${INGEST_URL}`);
console.log(`[bridge] pollMs=${POLL_MS} nokThreshold=${NOK_THRESHOLD}`);
console.log(`[bridge] timeoutMs=${REQUEST_TIMEOUT_MS} runOnce=${RUN_ONCE}`);

if (RUN_ONCE) {
  void tick()
    .catch((error) => {
      console.error(`[bridge] one-shot failed: ${(error as Error).message}`);
      process.exitCode = 1;
    })
    .finally(() => {
      process.exit();
    });
}

let busy = false;
setInterval(() => {
  if (busy) {
    return;
  }

  busy = true;
  void tick()
    .catch((error) => {
      console.error(`[bridge] tick failed: ${(error as Error).message}`);
    })
    .finally(() => {
      busy = false;
    });
}, POLL_MS);
