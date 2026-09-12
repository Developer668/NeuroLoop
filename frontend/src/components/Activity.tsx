"use client";
import { useEffect, useState } from "react";
import { api, Dashboard } from "@/lib/types";
import { Panel, errorText } from "./UI";
import { LineChart } from "./Charts";
export function Activity({ data }: { data: Dashboard }) {
  const days = Array.from({ length: 14 }, (_, i) => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - 13 + i);
    return d;
  });
  const values = days.map(
    (d) =>
      data.runs.filter((r) => {
        const x = new Date(r.created_at);
        return x >= d && x.getTime() < d.getTime() + 86400000;
      }).length,
  );
  const done = data.runs.filter((r) => r.status === "completed").length,
    failed = data.runs.filter((r) => r.status === "failed").length,
    active = data.runs.filter((r) =>
      ["queued", "running"].includes(r.status),
    ).length;
  return (
    <Panel
      title="Your experiment activity"
      description="Last 14 days · counts from the runs currently loaded in this workspace."
    >
      <div className="activity-layout">
        <div>
          <LineChart
            series={
              data.runs.length
                ? [{ name: "Runs started", values, tone: "#247e92" }]
                : []
            }
            labels={days.map((d) =>
              d.toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              }),
            )}
            height={175}
            caption="Actual experiment runs started per day"
          />
        </div>
        <div className="activity-summary">
          <div>
            <span>Completed</span>
            <strong>{done}</strong>
          </div>
          <div>
            <span>In progress</span>
            <strong>{active}</strong>
          </div>
          <div>
            <span>Failed</span>
            <strong>{failed}</strong>
          </div>
          <small>
            {data.runs.length} loaded runs. Failures remain in the record.
          </small>
        </div>
      </div>
    </Panel>
  );
}
type Hardware = {
  ram_total_bytes: number;
  ram_available_bytes: number;
  gpu: {
    name: string;
    driver: string;
    total_mib: number;
    free_mib: number;
    temperature_c: number;
  } | null;
};
export function HardwarePanel() {
  const [state, setState] = useState<Hardware | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    async function read() {
      try {
        const s = await api<Hardware>("system");
        if (live) {
          setState(s);
          setError("");
        }
      } catch (e) {
        if (live) setError(errorText(e));
      }
    }
    void read();
    const timer = setInterval(() => void read(), 15000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  const gpu = state?.gpu;
  return (
    <Panel
      title="Device health"
      description="Live telemetry · refreshed every 15 seconds"
    >
      <div className="panel-body">
        {error && <p className="notice error">{error}</p>}
        {state && (
          <>
            <div className="device-name">
              {gpu?.name || "GPU telemetry unavailable"}
            </div>
            <dl className="metrics-list">
              <div>
                <dt>GPU temperature</dt>
                <dd>{gpu ? gpu.temperature_c + "°C" : "Unavailable"}</dd>
              </div>
              <div>
                <dt>Available GPU memory</dt>
                <dd>
                  {gpu
                    ? (gpu.free_mib / 1024).toFixed(1) +
                      " / " +
                      (gpu.total_mib / 1024).toFixed(1) +
                      " GiB"
                    : "Unavailable"}
                </dd>
              </div>
              <div>
                <dt>Available system memory</dt>
                <dd>
                  {(state.ram_available_bytes / 1024 ** 3).toFixed(1)} GiB
                </dd>
              </div>
              <div>
                <dt>NVIDIA driver</dt>
                <dd>{gpu?.driver || "Unavailable"}</dd>
              </div>
            </dl>
            <div className="system-block">
              One inference job at a time. New evaluations require at least 4
              GiB GPU headroom and a starting temperature below 82°C. These
              checks do not repair a graphics driver fault.
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}
