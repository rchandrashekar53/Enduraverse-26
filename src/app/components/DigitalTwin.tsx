"use client";

import { useQuery } from "convex/react";
import { useMemo, useState, useEffect } from "react";
import { api } from "../../../convex/_generated/api";

function getTempColor(temp: number, minTemp: number, maxTemp: number): string {
  const normalized = (temp - minTemp) / (maxTemp - minTemp + 0.1);
  const clamped = Math.max(0, Math.min(1, normalized));

  if (clamped < 0.2) return "#1e40af";
  if (clamped < 0.35) return "#0ea5e9";
  if (clamped < 0.5) return "#10b981";
  if (clamped < 0.65) return "#eab308";
  if (clamped < 0.8) return "#f97316";
  return "#dc2626";
}

function HeatmapGrid({ minTemp, maxTemp }: { minTemp: number; maxTemp: number }) {
  const GRID_SIZE = 12;
  const [time, setTime] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setTime((t) => t + 0.016);
    }, 16);
    return () => clearInterval(interval);
  }, []);

  const cells = useMemo(() => {
    const arr: number[] = [];
    for (let i = 0; i < GRID_SIZE * GRID_SIZE; i++) {
      const row = Math.floor(i / GRID_SIZE);
      const col = i % GRID_SIZE;

      const baseTemp = minTemp + ((maxTemp - minTemp) * col) / GRID_SIZE;
      const heightVariance = Math.sin(row * 0.4 + time * 1.2) * (maxTemp - minTemp) * 0.1;
      const waveVariance = Math.cos(col * 0.3 + time * 0.8) * (maxTemp - minTemp) * 0.08;
      const pulseVariance = Math.sin((row + col) * 0.2 + time * 1.5) * (maxTemp - minTemp) * 0.06;

      arr.push(baseTemp + heightVariance + waveVariance + pulseVariance);
    }
    return arr;
  }, [minTemp, maxTemp, time]);

  return (
    <div className="flex h-56 flex-col gap-0.5 rounded-lg bg-zinc-950 p-2">
      {Array.from({ length: GRID_SIZE }).map((_, row) => (
        <div key={row} className="flex flex-1 gap-0.5">
          {Array.from({ length: GRID_SIZE }).map((_, col) => {
            const idx = row * GRID_SIZE + col;
            const cellTemp = cells[idx];
            const color = getTempColor(cellTemp, minTemp, maxTemp);
            return (
              <div
                key={`${row}-${col}`}
                className="flex-1 rounded transition-all duration-100"
                style={{
                  backgroundColor: color,
                  opacity: 0.85,
                  boxShadow:
                    cellTemp === Math.max(...cells)
                      ? `0 0 8px ${color}`
                      : "none",
                }}
                title={`${cellTemp.toFixed(1)}°C`}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function DigitalTwin() {
  const latest = useQuery(api.telemetry.getLatest);

  if (latest === undefined) {
    return (
      <div className="h-72 animate-pulse rounded-xl border border-zinc-800 bg-zinc-900 p-5">
        <div className="mb-3 h-4 w-28 rounded bg-zinc-800" />
        <div className="h-56 rounded bg-zinc-800" />
      </div>
    );
  }

  const temp = latest?.temp ?? 25;
  const minTemp = latest?.minTemp ?? Math.max(0, temp - 15);
  const maxTemp = latest?.maxTemp ?? Math.min(100, temp + 15);
  const status = temp > 40 ? "CRITICAL" : temp > 35 ? "WARNING" : "NOMINAL";
  const statusColor =
    temp > 40
      ? "text-red-400"
      : temp > 35
        ? "text-yellow-400"
        : "text-green-400";

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-mono text-xs uppercase tracking-widest text-zinc-400">
          Thermal Heatmap
        </p>
        <div className="flex items-center gap-3">
          <span className={`font-mono text-xs font-bold ${statusColor}`}>{status}</span>
          <span className="font-mono text-sm font-bold text-orange-400">
            {temp.toFixed(1)}°C
          </span>
        </div>
      </div>

      <HeatmapGrid minTemp={minTemp} maxTemp={maxTemp} />

      <div className="mt-3 flex justify-between font-mono text-xs text-zinc-600">
        <span className="text-blue-600">Cold</span>
        <span className="text-yellow-600">Warm</span>
        <span className="text-red-600">Hot</span>
      </div>
    </div>
  );
}
