"use client";
import "../app/brain-lab.css";
import styles from "./WorkspaceNavigation.module.css";
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { LineChart } from "./Charts";
import { AnatomicalReadout } from "./BrainReadouts";
const BrainCanvas = dynamic(() => import("./BrainCanvas"), { ssr: false });
type Data = Record<string, unknown>;
type MediaAsset = {
  id: string;
  name: string;
  kind: string;
  sha256: string;
  details: Data;
};
type Receipt = {
  id: string;
  title: string;
  source_kind: string;
  source_receipt: string;
  created_at: number;
  evaluator: string;
  input_asset_id: string;
  input_asset: MediaAsset;
  artifacts: MediaAsset[];
  result: {
    status: string;
    observations: Data;
    provenance: Data;
    limitations: string[];
    scores: Data;
  };
};
type Backups = {
  enabled: boolean;
  project: string;
  items: {
    id: string;
    status: string;
    url: string | null;
    error: string | null;
  }[];
};
const obj = (v: unknown): Data =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Data) : {};
const nums = (v: unknown): number[] =>
  Array.isArray(v)
    ? v.filter((n): n is number => typeof n === "number" && Number.isFinite(n))
    : [];
const text = (v: unknown) =>
  v == null ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);
const mediaUrl = (id: string) =>
  `/api/v2/assets/${encodeURIComponent(id)}/content`;

function SignedTable({
  labels,
  values,
  label,
}: {
  labels: string[];
  values: number[];
  label: string;
}) {
  const limit = Math.max(...values.map(Math.abs), 0.0001);
  return (
    <div className="ev-table-wrap">
      <table className="ev-table">
        <caption>{label}</caption>
        <thead>
          <tr>
            <th>Output</th>
            <th>Signed magnitude</th>
            <th>Raw value</th>
          </tr>
        </thead>
        <tbody>
          {labels.map((name, i) => (
            <tr key={name}>
              <td>{name}</td>
              <td>
                <div className="ev-bar">
                  <i
                    style={{
                      width: `${(Math.abs(values[i] || 0) / limit) * 50}%`,
                      left:
                        values[i] < 0
                          ? `${50 - (Math.abs(values[i]) / limit) * 50}%`
                          : "50%",
                      background: values[i] < 0 ? "#7e9bcc" : "#38bcb1",
                    }}
                  />
                </div>
              </td>
              <td>{Number.isFinite(values[i]) ? values[i].toFixed(5) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EvidenceStudio({ campaignId = "" }: { campaignId?: string }) {
  const [receipts, setReceipts] = useState<Receipt[]>([]),
    [selected, setSelected] = useState("");
  const [error, setError] = useState(""),
    [loaded, setLoaded] = useState(false),
    [frame, setFrame] = useState(0),
    [playing, setPlaying] = useState(false);
  const [backups, setBackups] = useState<Backups | null>(null);
  const [windowSelection, setWindowSelection] = useState("auto");
  const [mediaTime, setMediaTime] = useState(0);
  const [pattern, setPattern] = useState("all");
  const video = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const [response, backupResponse] = await Promise.all([
          fetch(`/api/v2/evidence${campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : ""}`, {
            cache: "no-store",
            signal: controller.signal,
          }),
          fetch("/api/v2/backups", {
            cache: "no-store",
            signal: controller.signal,
          }),
        ]);
        if (!response.ok)
          throw new Error(`Evidence connection failed (${response.status})`);
        const data: Receipt[] = await response.json();
        if (backupResponse.ok && !controller.signal.aborted)
          setBackups(await backupResponse.json());
        if (!controller.signal.aborted) {
          setReceipts(data);
          setError("");
          setLoaded(true);
        }
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "Evidence unavailable");
      }
      if (!controller.signal.aborted) timer = setTimeout(refresh, 5000);
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [campaignId]);
  const media = Array.from(
    new Map(receipts.map((r) => [r.input_asset_id, r.input_asset])).values(),
  );
  const assetId = media.some((a) => a.id === selected)
    ? selected
    : receipts.find(
        (r) =>
          r.evaluator === "tribe" &&
          r.source_kind === "generated_ad_evaluation",
      )?.input_asset_id ||
      media[0]?.id ||
      "";
  const group = receipts.filter((r) => r.input_asset_id === assetId);
  const tribe = group.find(
    (r) => r.evaluator === "tribe" && r.result.status === "SUCCEEDED",
  );
  const tsam = group.find((r) => r.evaluator === "tsam");
  const asset = media.find((a) => a.id === assetId);
  const brain = tribe?.result.observations || {},
    affect = tsam?.result.observations || {};
  const times = nums(brain.times),
    kragel = obj(brain.kragel);
  const frameIndex = Math.min(frame, Math.max(times.length - 1, 0));
  const windows = Array.isArray(affect.windows) ? affect.windows.map(obj) : [];
  const currentWindow = windowSelection !== "auto" ? windows[Number(windowSelection)] :
    windows.find(
      (w) =>
        Number(w.start) <= (asset?.kind === "video" || asset?.kind === "audio" ? mediaTime : times[frameIndex] || 0) &&
        Number(w.end) > (asset?.kind === "video" || asset?.kind === "audio" ? mediaTime : times[frameIndex] || 0),
    );
  const labels = Array.isArray(affect.labels) ? affect.labels.map(String) : [];
  const aggregate = obj(kragel.aggregate);
  const selection = obj(brain.model_selection);
  const loadedModels = Array.isArray(selection.models_loaded)
    ? selection.models_loaded.map(obj)
    : [];
  const summary = group.find((r) => r.evaluator === "summary");
  const vision = group.find((r) => r.evaluator === "vision");
  const inventory = group.find((r) => r.evaluator === "inventory");
  useEffect(() => {
    setFrame(0);
    setPlaying(false);
    setMediaTime(0);
    setWindowSelection("auto");
    setPattern("all");
  }, [assetId]);
  useEffect(() => {
    if (!playing || asset?.kind === "video" || !times.length) return;
    const timer = setInterval(
      () => setFrame((f) => (f + 1) % times.length),
      1000,
    );
    return () => clearInterval(timer);
  }, [playing, asset?.kind, times.length]);
  function seek(index: number) {
    setFrame(index);
    setMediaTime(times[index] || 0);
    if (video.current) video.current.currentTime = times[index] || 0;
  }
  function downloadReceipt() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(group, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `neuroloop-evidence-${assetId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="ev-studio">
      <section className="nl-panel">
        <div className="ev-heading">
          <div>
            <span className="ev-kicker">
              LIVE EVIDENCE LIBRARY · REFRESHES EVERY 5 SECONDS
            </span>
            <h2>Brain & emotion</h2>
            <p>
              Real notebook receipts, linked to the exact input checksum.
              Cortical colors are model predictions, not a recording of a
              viewer’s brain.
            </p>
          </div>
          <span className="nl-status">{receipts.length} receipts</span>
        </div>
        {error && (
          <p role="alert" className="nl-notice">
            {error}
          </p>
        )}
        <label className="ev-select">
          Media under evaluation
          <select
            aria-label="Evidence media"
            value={assetId}
            onChange={(e) => setSelected(e.target.value)}
          >
            {media.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} · {a.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        {!receipts.length && (
          <p className="nl-notice">
            {loaded
              ? "No notebook receipts have arrived. Completed campaign evaluations and verified notebook imports appear here automatically."
              : "Loading persisted evidence…"}
          </p>
        )}
      </section>
      <nav className={styles.sections} aria-label="Evidence sections">
        <a href="#evidence-media">Generated media</a>
        {asset && <>
          <a href="#evidence-playback">Stimulus & brain</a>
          {tribe && <a href="#evidence-cortex">Cortical timeline</a>}
          <a href="#evidence-emotion">Emotion & affect</a>
          {tribe && <a href="#evidence-regions">Brain regions</a>}
          <a href="#evidence-models">Models & receipts</a>
        </>}
      </nav>
      <section id="evidence-media" className={`nl-panel ${styles.target}`}>
        <h3>Generated media & revision history</h3>
        <p>
          Select an output to inspect its own evidence. Revision links cite the
          parent’s recorded model review.
        </p>
        <div className="ev-history">
          {media
            .filter((a) =>
              receipts.some(
                (r) =>
                  r.input_asset_id === a.id && r.evaluator === "generation",
              ),
            )
            .map((a) => {
              const generation = receipts.find(
                (r) =>
                  r.input_asset_id === a.id && r.evaluator === "generation",
              );
              const parent = text(
                generation?.result.observations.parent_asset_id,
              );
              return (
                <button
                  key={a.id}
                  className={
                    assetId === a.id
                      ? "ev-history-card selected"
                      : "ev-history-card"
                  }
                  onClick={() => setSelected(a.id)}
                >
                  {a.kind === "image" ? (
                    <img src={mediaUrl(a.id)} alt={a.name} />
                  ) : (
                    <video src={mediaUrl(a.id)} muted preload="metadata" />
                  )}
                  <strong>{a.name}</strong>
                  <span>
                    {parent !== "—"
                      ? `Revision of ${parent.slice(0, 8)} → ${a.id.slice(0, 8)}`
                      : `Original output · ${a.id.slice(0, 8)}`}
                  </span>
                  <small>{text(generation?.result.provenance.model)}</small>
                </button>
              );
            })}
        </div>
        <div className="ev-table-wrap"><table className="ev-table"><caption>Actual GLM evaluations · relative model scores, not measured ad performance</caption><thead><tr><th>Output</th><th>Visual quality (0–1)</th><th>Model explanation</th></tr></thead><tbody>{receipts.filter(r=>r.evaluator==="vision" && r.source_kind!=="reference_evaluation").map(r=>{const score=obj(r.result.scores.creative_quality);return <tr key={r.id}><td><button className="nl-button" onClick={()=>setSelected(r.input_asset_id)}>{r.input_asset.name}</button></td><td>{typeof score.value==="number"?score.value.toFixed(2):"—"}</td><td>{text(score.meaning)}</td></tr>;})}</tbody></table></div>
      </section>
      {asset && (
        <>
          <div className="ev-pipeline" aria-label="Recorded pipeline stages">
            {["generation", "vision", "tsam", "tribe", "summary"].map(
              (stage) => {
                const receipt = group.find((r) => r.evaluator === stage);
                return (
                  <div key={stage}>
                    <strong>
                      {stage === "summary"
                        ? "GLM summary"
                        : stage.toUpperCase()}
                    </strong>
                    <span>{receipt?.result.status || "NO RECEIPT"}</span>
                  </div>
                );
              },
            )}
          </div>
          <section id="evidence-playback" className={`ev-pair ${styles.target}`}>
            <div className="nl-panel ev-media">
              <span className="ev-kicker">
                {group[0]?.source_kind.replaceAll("_", " ")}
              </span>
              <h3>{asset.name}</h3>
              {asset.kind === "video" ? (
                <video
                  ref={video}
                  src={mediaUrl(asset.id)}
                  controls
                  preload="metadata"
                  onTimeUpdate={(e) => {
                    const t = e.currentTarget.currentTime;
                    setMediaTime(t);
                    let i = 0;
                    times.forEach((v, j) => {
                      if (v <= t) i = j;
                    });
                    setFrame(i);
                  }}
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                />
              ) : asset.kind === "image" ? (
                <img src={mediaUrl(asset.id)} alt={asset.name} />
              ) : (
                <audio src={mediaUrl(asset.id)} controls onTimeUpdate={(e) => setMediaTime(e.currentTarget.currentTime)} />
              )}
              <a
                className="nl-button"
                href={mediaUrl(asset.id)}
                download={asset.name}
              >
                Download original media
              </a>
              <small>
                SHA-256 <code>{asset.sha256}</code>
              </small>
            </div>
            <div className="nl-panel">
              <span className="ev-kicker">
                {tribe
                  ? "TRIBE V2 · PREDICTED AVERAGE CORTICAL RESPONSE"
                  : "MODEL EVIDENCE FOR THIS OUTPUT"}
              </span>
              {tribe && (
                <BrainCanvas
                  publicMesh
                  evaluationId={tribe?.id}
                  frame={frameIndex}
                />
              )}
              {tribe && times.length ? (
                <>
                  <div className="ev-heading">
                    <strong>
                      {(times[frameIndex] || 0).toFixed(2)} seconds
                    </strong>
                    <span>
                      Frame {frameIndex + 1} / {times.length}
                    </span>
                  </div>
                  <input
                    aria-label="Cortical playback time"
                    type="range"
                    min={0}
                    max={times.length - 1}
                    value={frameIndex}
                    onChange={(e) => seek(Number(e.target.value))}
                  />
                  {asset.kind !== "video" && (
                    <button
                      className="nl-button"
                      onClick={() => setPlaying(!playing)}
                    >
                      {playing ? "Pause" : "Play response"}
                    </button>
                  )}
                  <p>
                    Video playback and the scrubber select the corresponding
                    stored prediction frame.
                  </p>
                </>
              ) : (
                <div>
                  <h3>
                    {asset.kind === "image"
                      ? "Image evaluation"
                      : "Cortical evaluation pending"}
                  </h3>
                  {vision && (
                    <p>{text(vision.result.observations.visual_summary)}</p>
                  )}
                  <p className="nl-notice">
                    {asset.kind === "image"
                      ? "GLM reviews the actual image. The current TRIBE adapter requires video; no cortical response is fabricated for this still image."
                      : "No successful cortical artifact has been returned for this media yet."}
                  </p>
                </div>
              )}
            </div>
          </section>
          {summary && (
            <section className="nl-panel">
              <span className="ev-kicker">
                {text(summary.result.provenance.model)} · EXECUTION SUMMARY
              </span>
              <h3>What happened in this creative loop</h3>
              <p>{text(summary.result.observations.summary)}</p>
              {["findings", "limitations", "next_steps"].map((key) => {
                const items = summary.result.observations[key];
                return Array.isArray(items) && items.length ? (
                  <div key={key}>
                    <h4>{key.replaceAll("_", " ")}</h4>
                    <ul>
                      {items.map((v, i) => (
                        <li key={i}>{text(v)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null;
              })}
            </section>
          )}
          {vision && (
            <section className="nl-panel">
              <span className="ev-kicker">
                {text(vision.result.provenance.model)} · VISION REVIEW
              </span>
              <h3>Visual understanding</h3>
              <p>{text(vision.result.observations.visual_summary)}</p>
              {Array.isArray(vision.result.observations.frame_evidence) && (
                <table className="ev-table">
                  <thead>
                    <tr>
                      <th>Sample time</th>
                      <th>Observed evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vision.result.observations.frame_evidence.map((v, i) => {
                      const f = obj(v);
                      return (
                        <tr key={i}>
                          <td>{typeof f.timestamp_seconds === "number" ? `${f.timestamp_seconds.toFixed(3)} s` : "Image"}</td>
                          <td>{text(f.description)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <p>{vision.result.limitations.join(" ")}</p>
            </section>
          )}
          {tribe && (
            <section id="evidence-cortex" className={`nl-panel ${styles.target}`}>
              <h3>Cortical response over time</h3>
              <div className="ev-table-wrap">
                <table className="ev-table">
                  <caption>Models actually invoked for this media</caption>
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Model</th>
                      <th>Checkpoint location in notebook</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loadedModels.map((m, i) => (
                      <tr key={i}>
                        <td>{text(m.role)}</td>
                        <td>{text(m.name)}</td>
                        <td>
                          <code>{text(m.asset)}</code>
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td>Speech preprocessing</td>
                      <td colSpan={2}>{text(brain.transcript_source)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="ev-metrics">
                {[
                  ["Shape", text(brain.shape)],
                  ["Units", text(brain.units)],
                  ["Inference", `${text(brain.seconds)} s`],
                  ["Modalities", text(brain.modalities)],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <LineChart
                series={[
                  {
                    name: "Left hemisphere mean",
                    values: nums(brain.left_mean),
                  },
                  {
                    name: "Right hemisphere mean",
                    values: nums(brain.right_mean),
                  },
                  { name: "RMS", values: nums(brain.rms) },
                ].filter((s) => s.values.length > 0)}
                labels={times.map((t) => `${t.toFixed(1)}s`)}
                caption="Stored TRIBE response values · native model units"
              />
              <div className="ev-table-wrap">
                <table className="ev-table">
                  <thead>
                    <tr>
                      <th>Time (s)</th>
                      <th>Left mean</th>
                      <th>Right mean</th>
                      <th>RMS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {times.map((t, i) => (
                      <tr key={i}>
                        <td>{t.toFixed(2)}</td>
                        {[brain.left_mean, brain.right_mean, brain.rms].map(
                          (v, j) => (
                            <td key={j}>{nums(v)[i]?.toFixed(6) ?? "—"}</td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <section id="evidence-emotion" className={`ev-pair ${styles.target}`}>
            <div className="nl-panel">
              <h3>TSAM · audiovisual affect</h3>
              <p>
                {tsam?.result.status || "NOT RUN"} · raw uncalibrated logits,
                not probabilities or measured feelings.
              </p>
              {windows.length > 0 && (
                <label className="ev-select">
                  TSAM time window
                  <select value={windowSelection} onChange={(e) => setWindowSelection(e.target.value)}>
                    <option value="auto">Follow playback</option>
                    {windows.map((w, index) => <option key={index} value={String(index)}>{text(w.start)}–{text(w.end)} seconds</option>)}
                  </select>
                </label>
              )}
              {currentWindow ? (
                <>
                  <p>
                    Window {text(currentWindow.start)}–{text(currentWindow.end)}{" "}
                    seconds
                  </p>
                  <SignedTable
                    labels={labels}
                    values={nums(currentWindow.logits)}
                    label="All TSAM class outputs"
                  />
                  <p>
                    Omitted tail:{" "}
                    {Number(affect.omitted_tail_seconds || 0).toFixed(3)}{" "}
                    seconds · {text(affect.device)}
                  </p>
                </>
              ) : (
                <p>No recorded TSAM window covers this playback time. Select a recorded window above, if available.</p>
              )}
            </div>
            <div className="nl-panel">
              <h3>Kragel · cortical pattern expression</h3>
              <p className="nl-notice">
                {kragel.registration_verified === true
                  ? "Registration verified"
                  : "Registration unverified"}{" "}
                ·{" "}
                {kragel.decision_eligible === true
                  ? "Decision eligible"
                  : "Cannot be used for decisions"}
              </p>
              <SignedTable
                labels={Object.keys(aggregate)}
                values={Object.values(aggregate).map(Number)}
                label="Experimental pattern correlations"
              />
              {Object.keys(obj(kragel.trajectories)).length > 0 && <label className="ev-select">
                Emotion pattern trajectory
                <select value={pattern} onChange={(e) => setPattern(e.target.value)}>
                  <option value="all">All recorded patterns</option>
                  {Object.keys(obj(kragel.trajectories)).map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>}
              {Object.keys(obj(kragel.trajectories)).length > 0 && (
                <LineChart
                  series={Object.entries(obj(kragel.trajectories)).filter(([name]) => pattern === "all" || name === pattern).map(
                    ([name, values]) => ({ name, values: nums(values) }),
                  )}
                  labels={nums(kragel.times).map((t) => `${t}s`)}
                  caption="Kragel pattern expression over time"
                />
              )}
            </div>
          </section>
          {tribe && (
            <div id="evidence-regions" className={styles.target}><AnatomicalReadout key={tribe.id} evaluationId={tribe.id} /></div>
          )}
          <section id="evidence-models" className={`nl-panel ${styles.target}`}>
            <div className="ev-heading">
              <h3>Models, receipts & downloads</h3>
              <button className="nl-button" onClick={downloadReceipt}>
                Download all receipts
              </button>
            </div>
            {inventory &&
              Array.isArray(inventory.result.observations.models) && (
                <div className="ev-table-wrap">
                  <table className="ev-table">
                    <caption>
                      Hosted model inventory — installed files and actual usage
                      are distinct
                    </caption>
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Files</th>
                        <th>Stored size</th>
                        <th>Usage on selected media</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inventory.result.observations.models.map((value, i) => {
                        const model = obj(value);
                        return (
                          <tr key={i}>
                            <td>
                              {text(model.name)}
                              <small style={{ display: "block" }}>
                                {text(model.path)}
                              </small>
                            </td>
                            <td>{text(model.files)}</td>
                            <td>
                              {(Number(model.bytes || 0) / 1e9).toFixed(2)} GB
                            </td>
                            <td>{text(model.status)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            {group.map((r) => (
              <article className="ev-receipt" key={r.id}>
                <div className="ev-heading">
                  <strong>
                    {r.result.provenance.model
                      ? text(r.result.provenance.model)
                      : r.evaluator}
                  </strong>
                  <span className="nl-status">{r.result.status}</span>
                </div>
                <p>
                  {r.title} · {new Date(r.created_at * 1000).toLocaleString()}
                </p>
                <code>{r.source_receipt}</code>
                <p>{r.result.limitations?.join(" ")}</p>
                {Array.isArray(r.result.observations.log_assets) &&
                  r.result.observations.log_assets.map((value, i) => {
                    const log = obj(value);
                    return typeof log.id === "string" ? (
                      <a
                        key={i}
                        className="nl-button"
                        href={mediaUrl(log.id)}
                        download
                      >
                        {text(log.name)}
                      </a>
                    ) : null;
                  })}
                {r.artifacts.map((a) => (
                  <a
                    key={a.id}
                    className="nl-button"
                    href={mediaUrl(a.id)}
                    download={a.name}
                  >
                    Download {a.name}
                  </a>
                ))}
                <details>
                  <summary>
                    Full model output, configuration, checkpoints and provenance
                  </summary>
                  <pre className="nl-json">
                    {JSON.stringify(r.result, null, 2)}
                  </pre>
                </details>
              </article>
            ))}
            <h3>W&B storage</h3>
            <p>
              {backups?.enabled
                ? "Media and evidence are backed up as versioned W&B artifacts. VERIFIED means the service confirmed the content manifest."
                : "Artifact backups are not enabled."}
            </p>
            <div className="ev-table-wrap">
              <table className="ev-table">
                <thead>
                  <tr>
                    <th>Object</th>
                    <th>Delivery</th>
                    <th>Stored artifact</th>
                  </tr>
                </thead>
                <tbody>
                  {backups?.items
                    .filter(
                      (b) =>
                        b.id === `asset-${assetId}` ||
                        group.some(
                          (r) =>
                            b.id === `evidence-${r.id}` ||
                            r.artifacts.some((a) => b.id === `asset-${a.id}`),
                        ),
                    )
                    .map((b) => (
                      <tr key={b.id}>
                        <td>
                          <code>{b.id}</code>
                        </td>
                        <td>
                          {b.status}
                          {b.error && <small>{b.error}</small>}
                        </td>
                        <td>
                          {b.url ? (
                            <a href={b.url} target="_blank" rel="noreferrer">
                              Open W&B artifact
                            </a>
                          ) : (
                            "Awaiting upload confirmation"
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
