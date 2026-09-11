"use client";
import { useState, useEffect, useRef } from "react";
import { Download, ChevronRight, Layers, Info } from "lucide-react";
import dynamic from "next/dynamic";
const BrainCanvas = dynamic(() => import("./BrainCanvas"), { ssr: false });
import { Panel, Empty, AssetVisual, Badge, errorText, dateText } from "./UI";
import { AnatomicalReadout, TSAMReadout, KragelReadout, ResponseEnsembleReadout } from "./BrainReadouts";
import { LineChart } from "./Charts";
import { api, Asset, Evaluation, seconds, size } from "@/lib/types";

export default function BrainView({
  evaluations,
  assets,
  selected,
  onSelect,
}: {
  evaluations: Evaluation[];
  assets: Asset[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [reference, setReference] = useState("");
  const [archivedAsset, setArchivedAsset] = useState<Asset | null>(null);
  const [reload, setReload] = useState(0);
  const [frame, setFrame] = useState(0),
    [detail, setDetail] = useState<Evaluation | null>(null),
    [error, setError] = useState("");
  const video = useRef<HTMLVideoElement>(null);
  const pendingSeek = useRef<number | null>(null);
  const identity = selected || evaluations[0]?.id || "";
  useEffect(() => {
    setFrame(0);
    setDetail(null);
    setError("");
    setReference("");
    pendingSeek.current = null;
    if (!identity) return;
    let alive = true;
    api<Evaluation>("evaluations/" + identity)
      .then((x) => {
        if (alive) {
          setDetail(x);
          setError("");
        }
      })
      .catch((e) => {
        if (alive) setError(errorText(e));
      });
    return () => {
      alive = false;
    };
  }, [identity, reload]);
  const knownAsset = assets.find((a) => a.id === detail?.asset_id);
  useEffect(() => {
    setArchivedAsset(null);
    if (!detail?.asset_id || knownAsset) return;
    const controller = new AbortController();
    api<Asset>("assets/" + detail.asset_id, { signal: controller.signal })
      .then(setArchivedAsset)
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorText(e));
      });
    return () => controller.abort();
  }, [detail?.asset_id, knownAsset?.id]);
  const asset = knownAsset || archivedAsset;
  const ev = detail?.evidence;
  function selectFrame(index: number) {
    setFrame(index);
    if (video.current && ev?.times[index] !== undefined) {
      pendingSeek.current = ev.times[index];
      if (video.current.readyState >= 1)
        video.current.currentTime = ev.times[index];
    }
  }
  function exportEvidence() {
    if (!detail) return;
    const blob = new Blob([JSON.stringify(detail, null, 2)], {
        type: "application/json",
      }),
      url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `neuroloop-${detail.id}-evidence.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <div className="page-title">
        <div>
          <span className="eyebrow">Neural evidence / surface & time</span>
          <h1>The cortical observatory.</h1>
          <p>
            A predicted average cortical response, tied to its source, model
            profile, and original segment timestamps.
          </p>
        </div>
        {detail && (
          <button className="button" onClick={exportEvidence}>
            <Download size={14} />
            Evidence JSON
          </button>
        )}
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
          <button className="button" onClick={() => setReload((n) => n + 1)}>
            Retry loading result
          </button>
        </div>
      )}
      <div className="neural-layout">
        <div className="stack">
          <Panel
            title="Cortical surface"
            action={
              <Badge value={detail ? "model_prediction" : "anatomy_only"} />
            }
          >
            <div className="panel-body" style={{ paddingBottom: 0 }}>
              <label className="field">
                <span>Saved evaluation</span>
                <select
                  aria-label="Saved evaluation"
                  value={identity}
                  onChange={(e) => onSelect(e.target.value)}
                >
                  <option value="">Select an evaluation</option>
                  {detail && !evaluations.some((e) => e.id === detail.id) && (
                    <option value={detail.id}>
                      {asset?.name || "Archived evaluation"} · archived history
                    </option>
                  )}
                  {evaluations.map((e) => (
                    <option value={e.id} key={e.id}>
                      {assets.find((a) => a.id === e.asset_id)?.name ||
                        e.asset_id.slice(0, 8)}{" "}
                      · {dateText(e.created_at)}
                    </option>
                  ))}
                </select>
              </label>
              {detail && (
                <label className="field">
                  <span>Surface comparison</span>
                  <select
                    aria-label="Surface comparison"
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                  >
                    <option value="">Show the selected response</option>
                    {evaluations
                      .filter(
                        (e) =>
                          e.id !== identity &&
                          e.profile === detail.profile &&
                          JSON.stringify(e.evidence.times) ===
                            JSON.stringify(detail.evidence.times),
                      )
                      .map((e) => (
                        <option key={e.id} value={e.id}>
                          Difference from{" "}
                          {assets.find((a) => a.id === e.asset_id)?.name ||
                            e.id.slice(0, 8)}
                        </option>
                      ))}
                  </select>
                  <small>
                    Difference overlays require matching model profiles and
                    recorded timestamps.
                  </small>
                </label>
              )}
            </div>
            <BrainCanvas
              key={identity || "anatomy"}
              evaluationId={identity || undefined}
              frame={frame}
              comparisonId={reference || undefined}
            />
            {ev && (
              <div className="brain-controls">
                <label className="field">
                  <span>
                    Response time: {ev.times[frame]?.toFixed(1)} seconds
                  </span>
                  <input
                    aria-label="Neural response time"
                    type="range"
                    min={0}
                    max={ev.times.length - 1}
                    step={1}
                    value={frame}
                    onChange={(e) => selectFrame(Number(e.target.value))}
                  />
                </label>
                <div className="time-labels">
                  <span>{ev.times[0]?.toFixed(1)}s</span>
                  <span>{ev.times.length} recorded segments</span>
                  <span>{ev.times.at(-1)?.toFixed(1)}s</span>
                </div>
              </div>
            )}
          </Panel>
          <Panel
            title="Cortical response over time"
            description="Hemisphere means in model-response units; not emotion, attention, or confidence."
          >
            <div className="panel-body">
              <LineChart
                series={
                  ev
                    ? [
                        { name: "Left hemisphere", values: ev.left_mean },
                        { name: "Right hemisphere", values: ev.right_mean },
                      ]
                    : []
                }
                labels={ev?.times.map((t) => `${t.toFixed(0)}s`) || []}
                caption="Left and right cortical response means over time"
              />
            </div>
          </Panel>
          {identity && <AnatomicalReadout evaluationId={identity} />}
        </div>
        <aside className="stack">
          <Panel title="The stimulus">
            {asset ? (
              <>
                <div className="panel-body">
                  {asset.kind === "video" ? (
                    <video
                      ref={video}
                      controls
                      preload="metadata"
                      src={`/api/assets/${asset.id}/content`}
                      style={{
                        width: "100%",
                        borderRadius: 6,
                        background: "#151b1c",
                      }}
                      onLoadedMetadata={() => {
                        if (video.current && pendingSeek.current !== null)
                          video.current.currentTime = pendingSeek.current;
                      }}
                      onPointerDown={() => {
                        pendingSeek.current = null;
                      }}
                      onKeyDown={() => {
                        pendingSeek.current = null;
                      }}
                      onTimeUpdate={() => {
                        if (!ev || !video.current) return;
                        const time = video.current.currentTime;
                        // Ignore the previous media time while a cortical-slider seek is pending.
                        if (pendingSeek.current !== null) {
                          if (Math.abs(time - pendingSeek.current) > 0.15)
                            return;
                          pendingSeek.current = null;
                        }
                        let nearest = 0;
                        for (let i = 0; i < ev.times.length; i++)
                          if (
                            Math.abs(ev.times[i] - time) <
                            Math.abs(ev.times[nearest] - time)
                          )
                            nearest = i;
                        setFrame(nearest);
                      }}
                    />
                  ) : (
                    <AssetVisual asset={asset} play />
                  )}
                  <div style={{ marginTop: 14, fontWeight: 600, fontSize: 12 }}>
                    {asset.name}
                  </div>
                  <small>
                    {asset.kind} · {size(asset.size)}
                  </small>
                </div>
              </>
            ) : (
              <Empty
                title="Anatomy, not activity"
                text="Run a real evaluation to display predicted cortical values on this surface."
                icon={<Layers size={22} />}
              />
            )}
          </Panel>
          <Panel title="Provenance">
            <div className="panel-body">
              <dl className="metrics-list">
                <div>
                  <dt>Surface</dt>
                  <dd>fsaverage5</dd>
                </div>
                <div>
                  <dt>Vertices</dt>
                  <dd>20,484</dd>
                </div>
                <div>
                  <dt>Response source</dt>
                  <dd>{detail ? "TRIBE v2 prediction" : "Not evaluated"}</dd>
                </div>
                <div>
                  <dt>Runtime</dt>
                  <dd>{detail ? seconds(detail.duration_seconds) : "—"}</dd>
                </div>
                <div>
                  <dt>Profile</dt>
                  <dd className="mono">{detail?.profile || "—"}</dd>
                </div>
                <div>
                  <dt>Modalities</dt>
                  <dd>{ev?.modalities?.join(", ") || "—"}</dd>
                </div>
                <div>
                  <dt>Transcript</dt>
                  <dd>{ev?.transcript_source || "—"}</dd>
                </div>
                <div>
                  <dt>Output shape</dt>
                  <dd>{ev?.shape.join(" × ") || "—"}</dd>
                </div>
              </dl>
            </div>
          </Panel>
          <div className="notice info">
            <Info size={16} />
            <div>
              These colors show predicted cortical values. They do not identify
              a viewer’s thoughts or buying intent.
              {ev?.input_adaptation && (
                <p style={{ marginTop: 8 }}>{ev.input_adaptation}</p>
              )}
            </div>
          </div>
          {ev && <ResponseEnsembleReadout evidence={ev} />}
          {ev && <TSAMReadout evidence={ev} />}
          {ev && <KragelReadout evidence={ev} />}
        </aside>
      </div>
    </>
  );
}
