"use client";
import { useState, useEffect, useCallback } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Download,
  Square,
  Activity,
  Check,
  CornerUpLeft,
  AlertCircle,
} from "lucide-react";
import { api, Run, Asset, Project, score, seconds } from "@/lib/types";
import { Panel, Badge, Empty, AssetVisual, errorText, dateText } from "./UI";
import { LineChart, BudgetBar } from "./Charts";

export default function RunDetail({
  id,
  assets,
  projects,
  onBack,
  onBrain,
  onUpdate,
}: {
  id: string;
  assets: Asset[];
  projects: Project[];
  onBack: () => void;
  onBrain: (id: string) => void;
  onUpdate: () => void;
}) {
  const [run, setRun] = useState<Run | null>(null),
    [error, setError] = useState(""),
    [cancelling, setCancelling] = useState(false);
  const load = useCallback(async () => {
    try {
      setRun(await api<Run>("runs/" + id));
      setError("");
    } catch (e) {
      setError(errorText(e));
    }
  }, [id]);
  useEffect(() => {
    setRun(null);
    void load();
    const events = new EventSource(`/api/runs/${id}/events/stream`);
    let debounce: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => void load(), 200);
    };
    events.addEventListener("progress", refresh);
    events.addEventListener("done", () => {
      void load();
      onUpdate();
      events.close();
    });
    const fallback = setInterval(() => void load(), 5000);
    return () => {
      events.close();
      clearInterval(fallback);
      clearTimeout(debounce);
    };
  }, [id, load, onUpdate]);
  async function cancel() {
    setCancelling(true);
    try {
      await api("runs/" + id + "/cancel", { method: "POST" });
      await load();
      onUpdate();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setCancelling(false);
    }
  }
  if (!run)
    return (
      <Panel title="Opening experiment record">
        <Empty
          title="Reading the evidence"
          text={error || "Fetching the saved run from your workspace."}
        />
      </Panel>
    );
  const project = projects.find((p) => p.id === run.project_id),
    active = ["queued", "running"].includes(run.status);
  const original = assets.find((a) => a.id === run.result.baseline_asset_id),
    best = assets.find((a) => a.id === run.result.best_asset_id);
  const experiments = run.experiments || [],
    measured = experiments.filter((e) => typeof e.candidate_score === "number");
  const baseline = run.result.baseline_metric?.value;
  const values =
    typeof baseline === "number"
      ? [baseline, ...measured.map((e) => e.candidate_score!)]
      : [];
  let retained = baseline ?? 0;
  const bestValues =
    typeof baseline === "number"
      ? [
          baseline,
          ...measured.map((e) => {
            if (e.decision === "kept") retained = e.candidate_score!;
            return retained;
          }),
        ]
      : [];
  return (
    <>
      <button className="link-text" onClick={onBack}>
        <ArrowLeft size={14} />
        All experiments
      </button>
      <div className="page-title section-space">
        <div>
          <span className="eyebrow">
            {run.mode} / {id.slice(0, 8)}
          </span>
          <h1>{project?.name || "Experiment record"}</h1>
          <p>{run.stage}</p>
        </div>
        <div className="button-row">
          <Badge value={run.status} />
          {active ? (
            <button
              className="button danger"
              disabled={cancelling}
              onClick={() => void cancel()}
            >
              <Square size={13} />
              {cancelling ? "Requesting…" : "Stop run"}
            </button>
          ) : (
            run.result.best_asset_id && (
              <a className="button primary" href={`/api/runs/${id}/export`}>
                <Download size={14} />
                Export result
              </a>
            )
          )}
        </div>
      </div>
      {error && (
        <div className="notice error" role="alert">
          <AlertCircle size={15} />
          {error}
        </div>
      )}
      {run.error && (
        <div className="notice error" role="alert">
          <AlertCircle size={15} />
          {run.error}
        </div>
      )}
      <div className="run-layout">
        <div className="stack">
          <Panel
            title="The creative, before and after"
            description="Only completed, measured artifacts appear here."
          >
            {run.result.baseline_evaluation_id ? (
              <>
                <div className="evidence-pair">
                  <div>
                    <h3>Original</h3>
                    <AssetVisual asset={original} play />
                    <span className="big-number">{score(baseline)}</span>
                    <span className="label-help">
                      {baseline === undefined
                        ? "No reference selected"
                        : "Reference similarity"}
                    </span>
                    <p>{original?.name}</p>
                  </div>
                  <div>
                    <h3>Retained candidate</h3>
                    <AssetVisual asset={best} play />
                    <span className="big-number accent">
                      {score(run.result.best_metric?.value)}
                    </span>
                    <span className="label-help">
                      {baseline === undefined
                        ? "Analysis only"
                        : "Reference similarity"}
                    </span>
                    <p>{best?.name}</p>
                  </div>
                </div>
                <div className="evidence-footer">
                  <Check size={15} />
                  <span>
                    {run.result.best_asset_id === run.result.baseline_asset_id
                      ? "The original remains the selected artifact."
                      : "Selected under the fixed acceptance rule, with reference trade-offs checked."}
                  </span>
                  <button
                    className="link-text"
                    style={{ marginLeft: "auto" }}
                    onClick={() => onBrain(run.result.best_evaluation_id!)}
                  >
                    Brain view
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </>
            ) : (
              <Empty
                title={
                  active
                    ? "An experiment is in motion."
                    : "No completed prediction"
                }
                text={
                  active
                    ? "The worker is processing this run. Results appear only after a real model evaluation has been saved."
                    : "This run did not produce a complete evaluation. Review the event log for the cause."
                }
                icon={<Activity size={24} />}
              />
            )}
          </Panel>
          <Panel
            title="Search progression"
            description="Candidate measurements and the retained result; not a human approval rate."
          >
            <div className="panel-body">
              <LineChart
                series={[
                  { name: "Candidate score", values },
                  {
                    name: "Retained score",
                    values: bestValues,
                    tone: "var(--copper)",
                  },
                ]}
                labels={["Original", ...measured.map((e) => "E" + e.sequence)]}
                caption="Measured reference similarity by experiment"
              />
            </div>
          </Panel>
          <Panel
            title="Experiment ledger"
            description="Every hypothesis keeps its outcome, including rejection."
          >
            {experiments.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Test</th>
                      <th>Hypothesis</th>
                      <th>Measured gain</th>
                      <th>Decision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {experiments.map((e) => (
                      <tr key={e.id}>
                        <td className="mono-cell">
                          E{String(e.sequence).padStart(2, "0")}
                        </td>
                        <td>
                          <span className="cell-title">
                            {e.operator.replaceAll("_", " ")}
                          </span>
                          <span
                            style={{
                              fontSize: 11,
                              color: "var(--muted)",
                              display: "block",
                              maxWidth: 430,
                            }}
                          >
                            {e.hypothesis}
                          </span>
                          {e.evidence.reason && (
                            <small>{e.evidence.reason}</small>
                          )}
                        </td>
                        <td className="mono-cell">
                          {typeof e.evidence.gain === "number"
                            ? `${e.evidence.gain >= 0 ? "+" : ""}${e.evidence.gain.toFixed(4)}`
                            : "—"}
                        </td>
                        <td>
                          <Badge value={e.decision} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                title="No edits recorded"
                text="Analysis and comparison do not require generation. An optimization run records each proposed edit here."
              />
            )}
          </Panel>
        </div>
        <aside className="run-side stack">
          <Panel title="Run boundary">
            <div className="panel-body">
              <BudgetBar
                used={run.evaluations_used}
                total={run.max_evaluations}
                label="Neural evaluations"
              />
              <dl className="metrics-list">
                <div>
                  <dt>Recorded compute</dt>
                  <dd>{seconds(run.compute_seconds)}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{dateText(run.created_at)}</dd>
                </div>
                <div>
                  <dt>Search policy</dt>
                  <dd>{run.result.policy || "Not started"}</dd>
                </div>
                <div>
                  <dt>Language-model planner</dt>
                  <dd>{run.result.planner || "Not used"}</dd>
                </div>
                <div>
                  <dt>Mode</dt>
                  <dd>{run.mode}</dd>
                </div>
              </dl>
            </div>
            {run.stop_reason && (
              <div className="panel-footer">
                <strong>Stopping reason</strong>
                <br />
                {run.stop_reason}
              </div>
            )}
          </Panel>
          <Panel title="Live evidence" action={<Activity size={14} />}>
            <div className="event-list">
              {(run.events || [])
                .slice(-40)
                .reverse()
                .map((e) => (
                  <div className="event" key={e.id}>
                    <div className="event-meta">
                      <span>{e.kind.replaceAll("_", " ").toUpperCase()}</span>
                      <span>{new Date(e.created_at).toLocaleTimeString()}</span>
                    </div>
                    <p>{e.message}</p>
                    {e.details.error != null && (
                      <p className="event-details">{String(e.details.error)}</p>
                    )}
                  </div>
                ))}
            </div>
          </Panel>
          <div className="notice info">
            <CornerUpLeft size={15} />
            <span>
              A rejected edit is evidence—not a failed product. The last valid
              artifact remains available.
            </span>
          </div>
        </aside>
      </div>
    </>
  );
}
