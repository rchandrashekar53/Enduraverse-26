"use client";

import { useQuery } from "convex/react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../../../convex/_generated/api";
import { projectTemperature } from "@/lib/forecast";

const DANGER_THRESHOLD = 45;
const FORECAST_STEPS = 10;

type ChartDataPoint = {
  x: number;
  temp?: number;
  ghost?: number;
};

export function GhostLineChart() {
  const rawReadings = useQuery(api.telemetry.getLast20);

  if (rawReadings === undefined) {
    return (
      <div className="h-64 animate-pulse rounded-xl border border-zinc-800 bg-zinc-900 p-5">
        <div className="mb-4 h-4 w-32 rounded bg-zinc-800" />
        <div className="h-48 rounded bg-zinc-800" />
      </div>
    );
  }

  const readings = [...rawReadings].reverse();

  const actualData: ChartDataPoint[] = readings.map((reading, i) => ({
    x: i,
    temp: reading.temp,
  }));

  const temps = readings.map((reading) => reading.temp);
  const projected = projectTemperature(temps, FORECAST_STEPS);

  const ghostData: ChartDataPoint[] = projected.map((value, i) => ({
    x: readings.length + i,
    ghost: Number(value.toFixed(2)),
  }));

  const mergedData: ChartDataPoint[] = [...actualData, ...ghostData];
  const willOverheat = projected.some((value) => value >= DANGER_THRESHOLD);

  return (
    <div
      className={`rounded-xl border p-5 transition-all duration-700 ${
        willOverheat
          ? "animate-pulse-slow border-red-500/50 bg-red-950/20"
          : "border-zinc-800 bg-zinc-900"
      }`}
    >
      <div className="mb-4 flex items-center justify-between">
        <p className="font-mono text-xs uppercase tracking-widest text-zinc-400">
          Thermal Trajectory
        </p>
        {willOverheat ? (
          <span className="rounded-full border border-red-500/40 px-2 py-0.5 font-mono text-xs text-red-400">
            CRITICAL FORECAST
          </span>
        ) : null}
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart
          data={mergedData}
          margin={{ top: 5, right: 10, left: -20, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="x" hide />
          <YAxis
            domain={[20, 65]}
            tick={{ fill: "#71717a", fontSize: 10, fontFamily: "monospace" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: "8px",
              fontSize: "11px",
              fontFamily: "monospace",
            }}
            labelFormatter={() => ""}
          />
          <ReferenceLine
            y={DANGER_THRESHOLD}
            stroke="#ef4444"
            strokeDasharray="4 4"
            strokeOpacity={0.7}
            label={{
              value: `${DANGER_THRESHOLD}°C`,
              fill: "#ef4444",
              fontSize: 9,
              fontFamily: "monospace",
            }}
          />
          <Line
            type="monotone"
            dataKey="temp"
            stroke="#f97316"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: "#f97316" }}
            connectNulls={false}
            name="temp"
          />
          <Line
            type="monotone"
            dataKey="ghost"
            stroke="#f97316"
            strokeWidth={1.5}
            strokeDasharray="5 4"
            strokeOpacity={0.35}
            dot={false}
            connectNulls={false}
            name="ghost"
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-3 flex gap-4">
        <div className="flex items-center gap-1.5">
          <div className="h-0.5 w-4 bg-orange-500" />
          <span className="font-mono text-xs text-zinc-500">Actual</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div
            className="h-0.5 w-4 border-t border-dashed border-orange-500 opacity-40"
            aria-hidden
          />
          <span className="font-mono text-xs text-zinc-500">Forecast</span>
        </div>
      </div>
    </div>
  );
}
