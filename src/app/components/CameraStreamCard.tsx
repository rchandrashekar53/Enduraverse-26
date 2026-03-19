"use client";

import { useMemo, useState } from "react";

const DEFAULT_STREAM_URL = "http://10.141.17.79:81/stream";
const DEFAULT_CAMERA_URL = "http://10.141.17.79";

export function CameraStreamCard() {
  const streamUrl = process.env.NEXT_PUBLIC_ESP32_STREAM_URL ?? DEFAULT_STREAM_URL;
  const cameraUrl = process.env.NEXT_PUBLIC_ESP32_CAMERA_URL ?? DEFAULT_CAMERA_URL;
  const [hasError, setHasError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const source = useMemo(() => {
    const separator = streamUrl.includes("?") ? "&" : "?";
    return `${streamUrl}${separator}r=${reloadKey}`;
  }, [reloadKey, streamUrl]);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-mono text-xs uppercase tracking-widest text-zinc-400">
          Live Camera Feed
        </p>
        <button
          type="button"
          onClick={() => {
            setHasError(false);
            setReloadKey((prev) => prev + 1);
          }}
          className="rounded border border-zinc-700 px-2 py-1 font-mono text-[10px] tracking-wider text-zinc-300 transition-colors hover:border-zinc-500 hover:text-zinc-100"
        >
          RELOAD
        </button>
      </div>

      <div className="relative h-56 overflow-hidden rounded-lg bg-zinc-950">
        {hasError ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="font-mono text-xs text-red-400">Stream unavailable</p>
            <a
              href={cameraUrl}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-[11px] text-zinc-400 underline decoration-zinc-700 underline-offset-2 hover:text-zinc-200"
            >
              Open camera control panel
            </a>
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={source}
            alt="ESP32 live stream"
            className="h-full w-full object-cover"
            onError={() => setHasError(true)}
          />
        )}
      </div>

      <p className="mt-3 font-mono text-xs text-zinc-600">Source: {streamUrl}</p>
    </div>
  );
}
