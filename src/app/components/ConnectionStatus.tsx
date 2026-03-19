"use client";

import { useQuery } from "convex/react";
import { useEffect, useState } from "react";
import { api } from "../../../convex/_generated/api";

export function ConnectionStatus() {
  const latest = useQuery(api.telemetry.getLatest);
  const [now, setNow] = useState<number>(0);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNow(new Date().getTime());
    }, 500);

    return () => {
      window.clearInterval(intervalId);
    };
  }, []);

  const isStale =
    latest === undefined ||
    latest === null ||
    now - latest.timestamp > 3000;

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-xs tracking-wider transition-all duration-500 ${
        isStale
          ? "border-red-500/40 bg-red-950/30 text-red-400"
          : "border-green-500/40 bg-green-950/30 text-green-400"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isStale ? "bg-red-400" : "bg-green-400 animate-pulse"
        }`}
      />
      {isStale ? "SIGNAL LOST" : "LIVE"}
    </div>
  );
}
