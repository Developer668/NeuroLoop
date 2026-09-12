"use client";
import { useEffect, useState } from "react";
import { Panel, Badge, errorText } from "./UI";
import { LineChart } from "./Charts";
import { api, Evaluation } from "@/lib/types";
type Regions = {
  atlas: string;
  times: number[];
  regions: {
    id: string;
    hemisphere: string;
    name: string;
    vertices: number;
    mean: number[];
    rms: number;
  }[];
};
export function AnatomicalReadout({ evaluationId }: { evaluationId: string }) {
  const [data, setData] = useState<Regions | null>(null),
    [selected, setSelected] = useState(""),
    [error, setError] = useState(""),
    [query, setQuery] = useState("");
  useEffect(() => {
    let live = true;
    setData(null);
    setError("");
    api<Regions>("evaluations/" + evaluationId + "/regions")
      .then((d) => {
        if (live) {
          setData(d);
          setSelected(d.regions[0]?.id || "");
        }
      })
      .catch((e) => {
        if (live) setError(errorText(e));
      });
    return () => {
      live = false;
    };
  }, [evaluationId]);
  const region = data?.regions.find((r) => r.id === selected);
  const rows =
    data?.regions.filter((r) =>
      (r.hemisphere + " " + r.name).toLowerCase().includes(query.toLowerCase()),
    ) || [];
  return (
    <Panel
      title="Explore a cortical region"
      description="Destrieux anatomical parcels on fsaverage5. Select a region to inspect its recorded response."
    >
      {error ? (
        <div className="panel-body notice error">{error}</div>
      ) : (
        <div className="panel-body">
          <label className="field">
            <span>Anatomical region</span>
            <select
              aria-label="Anatomical region"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {data?.regions.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.hemisphere} · {r.name}
                </option>
              ))}
            </select>
          </label>
          <LineChart
            series={
              region
                ? [
                    {
                      name: region.hemisphere + " · " + region.name,
                      values: region.mean,
                      tone: "#277d91",
                    },
                  ]
                : []
            }
            labels={data?.times.map((t) => t.toFixed(1) + "s")}
            caption="Mean predicted response within the selected anatomical region"
          />
          <div className="button-row section-space">
            <input
              className="region-search"
              aria-label="Filter cortical regions"
              placeholder="Find a region…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <small>{rows.length} regions</small>
          </div>
          <div className="table-scroll region-table">
            <table>
              <thead>
                <tr>
                  <th>Region</th>
                  <th>Side</th>
                  <th>Vertices</th>
                  <th>RMS</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className={selected === r.id ? "region-selected" : ""}
                  >
                    <td>
                      <button
                        className="link-text"
                        onClick={() => setSelected(r.id)}
                      >
                        {r.name}
                      </button>
                    </td>
                    <td>{r.hemisphere}</td>
                    <td>{r.vertices}</td>
                    <td className="mono-cell">{r.rms.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="status-detail section-space">
            RMS describes signal magnitude in model-response units. Anatomy does
            not establish emotion or attention.
          </p>
        </div>
      )}
    </Panel>
  );
}
export function TSAMReadout({
  evidence,
}: {
  evidence: Evaluation["evidence"];
}) {
  const value = evidence.tsam;
  const [windowIndex, setWindowIndex] = useState(0);
  const windows = value?.windows || [];
  const chosen = windows[Math.min(windowIndex, windows.length - 1)];
  if (!value)
    return (
      <Panel title="Independent viewer-emotion readout">
        <div className="panel-body">
          <Badge value="not_requested" />
          <p className="status-detail section-space">
            Include the experimental TSAM readout when starting an audiovisual
            analysis. It runs on CPU and reads the creative independently of
            TRIBE.
          </p>
        </div>
      </Panel>
    );
  return (
    <Panel
      title="TSAM · audiovisual readout"
      action={<Badge value={value.status} />}
    >
      <div className="panel-body">
        {value.reason && <p className="status-detail">{value.reason}</p>}
        {chosen && (
          <>
            <label className="field">
              <span>Five-second window</span>
              <select
                aria-label="Five-second window"
                value={Math.min(windowIndex, windows.length - 1)}
                onChange={(e) => setWindowIndex(Number(e.target.value))}
              >
                {windows.map((w, i) => (
                  <option key={w.start} value={i}>
                    {w.start}s–{w.end}s
                  </option>
                ))}
              </select>
            </label>
            <EvidenceBars rows={(value.labels || []).map((label,i) => [label, chosen.logits[i]])} kind="logit" />
            <details className="raw-readout" open><summary>Original signed logits</summary>
            <div className="logit-list">
              {value.labels?.map((label, i) => (
                <div key={label}>
                  <span>{label}</span>
                  <div className="logit-track">
                    <i
                      style={{
                        width:
                          (Math.abs(chosen.logits[i]) /
                            Math.max(...chosen.logits.map(Math.abs), 0.001)) *
                            100 +
                          "%",
                        background:
                          chosen.logits[i] < 0 ? "#7a96b9" : "#288b8a",
                      }}
                    />
                  </div>
                  <strong>{chosen.logits[i].toFixed(3)}</strong>
                </div>
              ))}
            </div>
            </details>
            <p className="status-detail section-space">
              Uncalibrated logits; bars show absolute magnitude and numbers
              retain the sign. These are model outputs, not observed feelings or
              probabilities.
            </p>
            <small>
              CPU inference · {value.seconds?.toFixed(1)}s · experimental
              relative evidence
            </small>
          </>
        )}
      </div>
    </Panel>
  );
}

export function KragelReadout({
  evidence,
}: {
  evidence: Evaluation["evidence"];
}) {
  const value = evidence.kragel;
  const [selected, setSelected] = useState("");
  useEffect(() => {
    if (value?.labels?.length && !selected) setSelected(value.labels[0]);
  }, [value?.labels, selected]);
  if (!value) {
    return (
      <Panel title="Kragel · TRIBE-derived emotion patterns">
        <div className="panel-body">
          <Badge value="not_requested" />
          <p className="status-detail section-space">
            Enable the experimental Kragel readout to compare TRIBE cortical
            predictions with the seven published Kragel 2015 emotion signatures.
          </p>
        </div>
      </Panel>
    );
  }
  if (value.status !== "experimental") {
    return (
      <Panel
        title="Kragel · TRIBE-derived emotion patterns"
        action={<Badge value={value.status} />}
      >
        <div className="panel-body">
          <p className="status-detail">
            {value.reason || "Kragel readout unavailable."}
          </p>
        </div>
      </Panel>
    );
  }
  const labels = value.labels || [];
  const active = selected || labels[0] || "";
  const trajectory = value.trajectories?.[active] || [];
  const aggregate = value.aggregate || {};
  return (
    <Panel
      title="Kragel · TRIBE-derived emotion patterns"
      action={<Badge value="experimental" />}
    >
      <div className="panel-body">
        <div className="response-evidence-grid">
          {labels.map((label) => (
            <button
              key={label}
              className={
                "response-evidence-card " + (active === label ? "active" : "")
              }
              onClick={() => setSelected(label)}
            >
              <span>{label}</span>
              <strong>{aggregate[label]?.toFixed(4) ?? "—"}</strong>
            </button>
          ))}
        </div>
        <EvidenceBars rows={labels.filter(label => Number.isFinite(aggregate[label])).map(label => [label,aggregate[label]])} kind="correlation" />
        {active && trajectory.length > 0 && (
          <LineChart
            series={[{ name: active, values: trajectory }]}
            labels={(value.times || []).map((t) => `${t.toFixed(1)}s`)}
            caption={`${active} Kragel pattern expression over TRIBE response time`}
          />
        )}
        <p className="status-detail section-space">{value.interpretation}</p>
        <small>
          Top pattern: {value.top_pattern || "—"}. Correlations are experimental
          model-to-model evidence, not probabilities or observed emotions.
        </small>
      </div>
    </Panel>
  );
}

export function ResponseEnsembleReadout({
  evidence,
}: {
  evidence: Evaluation["evidence"];
}) {
  const value = evidence.response_ensemble;
  if (!value) return null;
  const rows = Object.entries(value.values).filter(
    ([, score]) => typeof score === "number",
  ) as [string, number][];
  return (
    <Panel
      title="Combined response evidence"
      action={<Badge value="experimental" />}
    >
      <div className="panel-body">
        <div className="response-evidence-grid">
          {rows.map(([name, score]) => (
            <div className="response-evidence-card" key={name}>
              <span>{name}</span>
              <strong>{score.toFixed(3)}</strong>
            </div>
          ))}
        </div>
        <EvidenceBars rows={rows} kind="relative" />
        <dl className="metrics-list section-space">
          <div>
            <dt>Agreement heuristic</dt>
            <dd>{value.confidence} (not calibrated confidence)</dd>
          </div>
          <div>
            <dt>Sources</dt>
            <dd>{value.active_sources.join(" + ") || "none"}</dd>
          </div>
          <div>
            <dt>TSAM weight</dt>
            <dd>{(value.source_weights.tsam || 0).toFixed(2)}</dd>
          </div>
          <div>
            <dt>Kragel weight</dt>
            <dd>{(value.source_weights.kragel || 0).toFixed(2)}</dd>
          </div>
          <div>
            <dt>Mean disagreement</dt>
            <dd>
              {value.mean_disagreement == null
                ? "—"
                : value.mean_disagreement.toFixed(3)}
            </dd>
          </div>
        </dl>
        <p className="status-detail">{value.interpretation}</p>
      </div>
    </Panel>
  );
}

function EvidenceBars({rows,kind}:{rows:[string,number][];kind:"relative"|"logit"|"correlation"}) {
  const finite = rows.filter(([,value]) => Number.isFinite(value));
  if (!finite.length) return null;
  const peak = Math.max(...finite.map(([,value]) => value));
  const total = finite.reduce((sum,[,value]) => sum+Math.exp(value-peak),0);
  const signed = kind === "correlation";
  const values = finite.map(([name,value]) => ({name,raw:value,value:kind === "logit" ? Math.exp(value-peak)/total : value}));
  return <div className="evidence-bars">
    <p className="evidence-bars-label">{signed ? "Pattern alignment · opposite ← 0 → similar" : "Relative evidence · lower to higher"}</p>
    {values.map(({name,value,raw}) => <div className="evidence-bar-row" key={name}>
      <span>{name}</span>
      <div className={"evidence-bar-track"+(signed ? " signed" : "")} role="meter" aria-label={name+" "+(signed ? "pattern correlation" : "relative model evidence")} aria-valuemin={signed ? -1 : 0} aria-valuemax={1} aria-valuenow={value} aria-valuetext={signed ? raw.toFixed(4)+" pattern correlation" : (value*100).toFixed(1)+" out of 100 relative evidence points; not probability"}>
        <i style={{left:signed ? (value < 0 ? 50+Math.max(-1,value)*50 : 50)+"%" : 0,width:(signed ? Math.min(1,Math.abs(value))*50 : Math.min(1,Math.max(0,value))*100)+"%"}} />
      </div>
      <strong>{signed ? raw.toFixed(3) : (value*100).toFixed(1)+" / 100"}</strong>
    </div>)}
    <p className="status-detail">{kind === "logit" ? "Softmax of the displayed logits, with temperature 1. This compares classes within this window; it is not calibrated emotion probability." : signed ? "Signed spatial correlations on a fixed −1 to +1 scale. Negative means opposite pattern alignment, not absence of an emotion." : "The same recorded values above, multiplied by 100 for readability. These are relative model evidence points, not percentages of viewers or measured emotion intensity."}</p>
  </div>;
}
