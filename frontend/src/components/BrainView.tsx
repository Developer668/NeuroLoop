"use client";
import { useState, useEffect, useRef } from "react";
import { Download, ChevronRight, Layers, Info } from "lucide-react";
import dynamic from "next/dynamic";
import "../app/brain-lab.css";
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
  const audio = useRef<HTMLAudioElement>(null);
  const pendingSeek = useRef<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const identity = selected || evaluations[0]?.id || "";
  useEffect(() => {
    setFrame(0);
    setPlaying(false);
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
  useEffect(() => {
    const media = video.current || audio.current;
    if (media) media.playbackRate = speed;
  }, [speed, asset?.id]);
  useEffect(() => {
    if (!playing || !ev || asset?.kind === "video" || asset?.kind === "audio") return;
    const next = frame + 1;
    if (next >= ev.times.length) { setPlaying(false); return; }
    const timer = window.setTimeout(() => setFrame(next),
      Math.max(20, (ev.times[next] - ev.times[frame]) * 1000 / speed));
    return () => window.clearTimeout(timer);
  }, [playing, frame, speed, ev, asset?.kind]);
  async function togglePlayback() {
    const media = video.current || audio.current;
    if (playing) { media?.pause(); setPlaying(false); return; }
    if (frame >= (ev?.times.length || 1) - 1) selectFrame(0);
    try {
      if (media) { media.playbackRate = speed; await media.play(); }
      setPlaying(true);
    } catch (e) { setError(errorText(e)); }
  }
  function selectFrame(index: number) {
    setFrame(index);
    const media = video.current || audio.current;
    if (media && ev?.times[index] !== undefined) {
      const target = Number.isFinite(media.duration)
        ? Math.min(ev.times[index], media.duration)
        : ev.times[index];
      pendingSeek.current = target;
      if (media.readyState >= 1) media.currentTime = target;
    }
  }
  function seekWhenReady() {
    const media = video.current || audio.current;
    if (media && pendingSeek.current !== null) {
      const target = Math.min(pendingSeek.current, media.duration);
      if (Number.isFinite(target)) {
        pendingSeek.current = target;
        media.currentTime = target;
      }
    }
  }
  function syncMediaTime() {
    const media = video.current || audio.current;
    if (!media || !ev?.times.length) return;
    if (pendingSeek.current !== null) {
      if (Math.abs(media.currentTime - pendingSeek.current) > 0.15) return;
      pendingSeek.current = null;
    }
    let nearest = 0;
    for (let i = 1; i < ev.times.length; i++) {
      if (
        Math.abs(ev.times[i] - media.currentTime) <
        Math.abs(ev.times[nearest] - media.currentTime)
      )
        nearest = i;
    }
    setFrame(nearest);
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
            <div className="brain-selection-row">
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
      <div className="neural-layout">
        <div className="stack">
          <Panel
            title="Cortical surface"
            action={
              <Badge value={detail ? "model_prediction" : "anatomy_only"} />
            }
          >
            <BrainCanvas
              key={identity || "anatomy"}
              evaluationId={identity || undefined}
              frame={frame}
              comparisonId={reference || undefined}
            />
            {ev && (
              <div className="brain-controls">
                <div className="playback-transport">
                  <button className="button primary" onClick={togglePlayback} disabled={!asset}>
                    {playing ? "Pause stimulus & brain" : "Play stimulus & brain"}
                  </button>
                  <label className="field"><span>Playback speed</span>
                    <select aria-label="Playback speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}>
                      <option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option>
                    </select>
                  </label>
                </div>
                <label className="field">
                  <span>
                    Stimulus time: {ev.times[frame]?.toFixed(1)} seconds
                  </span>
                  <input
                    aria-label="Neural response time"
                    type="range"
                    min={0}
                    max={Math.max(0, ev.times.length - 1)}
                    disabled={ev.times.length < 2}
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
                      preload="metadata"
                      src={`/api/assets/${asset.id}/content`}
                      style={{
                        width: "100%",
                        borderRadius: 6,
                        background: "#151b1c",
                      }}
                      onLoadedMetadata={seekWhenReady}
                      onPointerDown={() => {
                        pendingSeek.current = null;
                      }}
                      onKeyDown={() => {
                        pendingSeek.current = null;
                      }}
                      onTimeUpdate={syncMediaTime}
                      onEnded={() => setPlaying(false)}
                      onPause={() => setPlaying(false)}
                      onPlay={() => setPlaying(true)}
                    />
                  ) : asset.kind === "audio" ? (
                    <audio
                      ref={audio}
                      preload="metadata"
                      src={`/api/assets/${asset.id}/content`}
                      onLoadedMetadata={seekWhenReady}
                      onTimeUpdate={syncMediaTime}
                      onEnded={() => setPlaying(false)}
                      onPause={() => setPlaying(false)}
                      onPlay={() => setPlaying(true)}
                      onPointerDown={() => {
                        pendingSeek.current = null;
                      }}
                      onKeyDown={() => {
                        pendingSeek.current = null;
                      }}
                    />
                  ) : asset.kind === "image" ? (
                    <img
                      src={`/api/assets/${asset.id}/content`}
                      alt={asset.name}
                      style={{ width: "100%", height: "auto", display: "block", objectFit: "contain", borderRadius: 6 }}
                    />
                  ) : (
                    <AssetVisual asset={asset} play />
                  )}
                  <div style={{ marginTop: 14, fontWeight: 600, fontSize: 12 }}>
                    {asset.name}
                  </div>
                  <small>
                    Playback follows the shared Brain Lab transport. {asset.kind} · {size(asset.size)}
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
                  <dt>Feature plan</dt>
                  <dd>
                    {ev?.model_selection?.models_loaded
                      ?.filter((model) => model.role !== "brain_readout")
                      .map((model) => model.name)
                      .join(", ") || "—"}
                  </dd>
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
