"use client";

import Image from "next/image";
import { useState } from "react";
import { useQuery } from "convex/react";
import { api } from "../../../convex/_generated/api";

const XRAY_FILTER =
  "invert(1) contrast(1.5) grayscale(1) sepia(1) hue-rotate(180deg) brightness(1.1)";

export function XRayCards() {
  const defects = useQuery(api.defects.getAll);
  const [tinyImageIds, setTinyImageIds] = useState<Record<string, boolean>>({});

  if (defects === undefined) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-8 animate-pulse">
        <div className="mb-2 h-4 w-44 rounded bg-zinc-800" />
        <div className="h-28 rounded bg-zinc-800" />
      </div>
    );
  }

  if (defects.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-8 text-center">
        <div className="mb-1 font-mono text-sm text-zinc-600">NO INCIDENTS LOGGED</div>
        <div className="font-mono text-xs text-zinc-700">
          System nominal, monitoring active
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="font-mono text-xs uppercase tracking-widest text-zinc-400">
        Defect Audit Trail - {defects.length} Incident{defects.length !== 1 ? "s" : ""}
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {defects.map((defect) => (
          <div
            key={defect._id}
            className="rounded-xl border border-red-900/50 bg-zinc-900 p-4 transition-all hover:border-red-500/50"
          >
            <div className="mb-3 flex items-start justify-between">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                <span className="font-mono text-xs font-bold uppercase tracking-wider text-red-400">
                  Defect Detected
                </span>
              </div>
              <span className="font-mono text-xs text-zinc-600">
                {new Date(defect.timeDetected).toLocaleTimeString("en-US", {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </span>
            </div>

            {defect.imageUrl ? (
              <div className="relative mb-3 overflow-hidden rounded-lg bg-zinc-950">
                <Image
                  src={defect.imageUrl}
                  alt={`Defect frame ${defect.timeDetected}`}
                  fill
                  className="object-cover"
                  style={{ filter: XRAY_FILTER }}
                  unoptimized
                  onLoad={(event) => {
                    const image = event.currentTarget;
                    if (image.naturalWidth <= 2 || image.naturalHeight <= 2) {
                      setTinyImageIds((prev) => ({ ...prev, [defect._id]: true }));
                    }
                  }}
                />
                {tinyImageIds[defect._id] ? (
                  <div className="absolute inset-x-0 bottom-0 bg-zinc-950/90 px-2 py-1 font-mono text-[10px] text-amber-300">
                    Tiny test image detected (1x1-like). Send a real camera frame for full X-ray preview.
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="mb-3 flex h-32 items-center justify-center rounded-lg bg-zinc-950">
                <span className="font-mono text-xs text-zinc-700">Image unavailable</span>
              </div>
            )}

            <div className="space-y-1">
              <div className="flex justify-between">
                <span className="font-mono text-xs text-zinc-500">Heat Signature</span>
                <span className="font-mono text-xs font-bold text-orange-400">
                  {defect.heatSignature.toFixed(1)}°C
                </span>
              </div>
              <div className="flex justify-between">
                <span className="font-mono text-xs text-zinc-500">Timestamp</span>
                <span className="font-mono text-xs text-zinc-400">
                  {new Date(defect.timeDetected).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
