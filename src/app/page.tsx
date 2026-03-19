import { ConnectionStatus } from "./components/ConnectionStatus";
import { CameraStreamCard } from "./components/CameraStreamCard";
import { DigitalTwin } from "./components/DigitalTwin";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { GhostLineChart } from "./components/GhostLineChart";
import { XRayCards } from "./components/XRayCards";

export default function DashboardPage() {
  return (
    <main className="mx-auto min-h-screen max-w-7xl bg-zinc-950 p-6">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="font-mono text-2xl font-bold tracking-tight text-zinc-100">
            dream<span className="text-orange-400">Vision</span>
          </h1>
          <p className="mt-0.5 font-mono text-xs tracking-wider text-zinc-500">
            INDUSTRIAL DEFECT DETECTION SYSTEM
          </p>
        </div>
        <ConnectionStatus />
      </header>

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <GhostLineChart />
        </div>
        <ErrorBoundary
          fallback={
            <div className="flex h-64 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900 p-5 font-mono text-sm text-zinc-600">
              3D renderer unavailable
            </div>
          }
        >
          <DigitalTwin />
        </ErrorBoundary>
        <CameraStreamCard />
      </div>

      <XRayCards />
    </main>
  );
}
