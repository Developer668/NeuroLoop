"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Evaluation, Experiment, Run, seconds, score } from "@/lib/types";
import { Panel, Badge, errorText, dateText } from "./UI";
import { TSAMReadout, KragelReadout } from "./BrainReadouts";
import { LineChart } from "./Charts";

type Ledger = {
  runs: (Run & { project_name: string; archived: boolean })[];
  evaluations: (Evaluation & { asset_name: string; archived: boolean })[];
  experiments: Experiment[];
  coverage: string;
};
export default function ResearchEvidence() {
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api<Ledger>("research", { signal: controller.signal })
      .then(setLedger)
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorText(e));
      });
    return () => controller.abort();
  }, []);
  if (error)
    return (
      <div className="notice error" role="alert">
        {error}
      </div>
    );
  if (!ledger)
    return (
      <div className="notice info" role="status">
        Loading the recorded research ledger…
      </div>
    );
  const evaluations = ledger.evaluations.filter((e) => history || !e.archived);
  const runs = ledger.runs.filter((r) => history || !r.archived);
  const runIds = new Set(runs.map((r) => r.id));
  const interventions = ledger.experiments.filter((e) =>
    runIds.has((e as Experiment & { run_id: string }).run_id),
  );
  const evaluation =
    evaluations.find((e) => e.id === selected) || evaluations[0];
  const measured = interventions.filter(e => e.candidate_score != null && e.baseline_score != null);
  const completed = runs
    .filter((r) => r.status === "completed")
    .slice(0, 12)
    .reverse();
  return (
    <div className="stack">
      <div className="comparison-guide">
        <strong>Your research ledger</strong>
        <span>Saved numerical evidence, directly in your workspace.</span>
        <label className="check">
          <input
            type="checkbox"
            checked={history}
            onChange={(e) => setHistory(e.target.checked)}
          />{" "}
          Include archived history
        </label>
      </div>
      <div className="grid-two">
        <Panel
          title="Recorded cortical timeline"
          description="Left and right hemisphere means in model-response units."
        >
          <div className="panel-body">
            <label className="field">
              <span>Research evaluation</span>
              <select
                aria-label="Research evaluation"
                value={evaluation?.id || ""}
                onChange={(e) => setSelected(e.target.value)}
              >
                {evaluations.length ? (
                  evaluations.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.asset_name} · {dateText(e.created_at)}
                    </option>
                  ))
                ) : (
                  <option value="">No saved evaluations</option>
                )}
              </select>
            </label>
          </div>
          <LineChart
            series={
              evaluation
                ? [
                    {
                      name: "Left hemisphere",
                      values: evaluation.evidence.left_mean,
                    },
                    {
                      name: "Right hemisphere",
                      values: evaluation.evidence.right_mean,
                    },
                  ]
                : []
            }
            labels={evaluation?.evidence.times.map((t) => t + "s")}
            caption="Recorded cortical response by hemisphere"
          />
          {evaluation && (
            <div className="panel-footer">
              <Link href={"/workspace?view=brain&evaluation=" + evaluation.id}>
                Inspect this result in Brain Lab ↗
              </Link>
            </div>
          )}
        </Panel>
        <Panel
          title="Compute per completed run"
          description="Recorded wall time in seconds. Different inputs and caches affect cost."
        >
          <LineChart
            series={[
              {
                name: "Compute seconds",
                values: completed.map((r) => r.compute_seconds),
              },
            ]}
            labels={completed.map((_, i) => String(i + 1))}
            caption="Actual compute seconds for the latest completed runs"
          />
          <div className="panel-body">
            <p className="status-detail">
              {completed.length} completed runs in this view. The horizontal
              axis follows their chronological order.
            </p>
          </div>
        </Panel>
      </div>
      <div className="grid-two">
        <Panel title="Run reliability" description="Recorded outcomes, including deliberate cancellations; not a hardware reliability estimate.">
          <div className="panel-body">{Array.from(new Set(runs.map(r => r.status))).map(status => {
            const count = runs.filter(r => r.status === status).length;
            return <div className="analytics-bar" key={status}><span>{status}</span><meter min={0} max={Math.max(1,runs.length)} value={count} /><strong>{count}</strong></div>;
          })}</div>
        </Panel>
        <Panel title="Measured change" description="Candidate minus baseline for recorded interventions; not audience preference.">
          <LineChart series={[{name:"Score change", values:measured.map(e => e.candidate_score! - e.baseline_score!)}]} labels={measured.map(e => e.operator)} caption="Recorded intervention score differences" />
        </Panel>
        <Panel title="Operator outcomes" description="Counts from this view; unequal attempts do not establish the best operator.">
          <div className="panel-body">{Array.from(new Set(interventions.map(e => e.operator))).map(operator => <div className="analytics-bar" key={operator}><span>{operator.replaceAll("_"," ")}</span><strong>{interventions.filter(e => e.operator === operator && e.decision === "kept").length} kept / {interventions.filter(e => e.operator === operator).length} attempts</strong></div>)}{!interventions.length && <p>No interventions in this view.</p>}</div>
        </Panel>
        <Panel title="Hemisphere heatmap" description="Signed means across the same recording. Hover a cell for its original value.">
          <div className="panel-body">{evaluation && [evaluation.evidence.left_mean,evaluation.evidence.right_mean].map((values,side) => {
            const limit = Math.max(.0001,...evaluation.evidence.left_mean.map(Math.abs),...evaluation.evidence.right_mean.map(Math.abs));
            return <div key={side} className="hemisphere-strip"><span>{side ? "Right" : "Left"}</span><div>{values.map((v,i) => <span key={i} title={`${evaluation.evidence.times[i]}s: ${v}`} style={{background:v < 0 ? `rgba(42,110,202,${.12+.88*Math.abs(v)/limit})` : `rgba(233,95,35,${.12+.88*Math.abs(v)/limit})`}} />)}</div></div>;
          })}</div>
        </Panel>
      </div>
      {evaluation && <div className="grid-two"><TSAMReadout evidence={evaluation.evidence} /><KragelReadout evidence={evaluation.evidence} /></div>}
      <RunLogTable runs={runs} />
      <Panel
        title="Intervention ledger"
        description="Hypotheses, measured scores and decisions from the same experiment controller."
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Change</th>
                <th>Hypothesis</th>
                <th>Baseline</th>
                <th>Candidate</th>
                <th>Decision</th>
              </tr>
            </thead>
            <tbody>
              {interventions.map((e) => (
                <tr key={e.id}>
                  <td>{e.operator.replaceAll("_", " ")}</td>
                  <td>{e.hypothesis}</td>
                  <td>{score(e.baseline_score)}</td>
                  <td>{score(e.candidate_score)}</td>
                  <td>
                    <Badge value={e.decision} />
                  </td>
                </tr>
              ))}
              {!interventions.length && (
                <tr>
                  <td colSpan={5}>
                    No interventions in this view. Run a controlled experiment
                    or include archived history.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel title="Evaluation register" description={ledger.coverage}>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Creative</th>
                <th>Recorded</th>
                <th>Cortical samples</th>
                <th>Time</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {evaluations.map((e) => (
                <tr key={e.id}>
                  <td>{e.asset_name}</td>
                  <td>{dateText(e.created_at)}</td>
                  <td>{e.evidence.shape.join(" × ")}</td>
                  <td>{seconds(e.duration_seconds)}</td>
                  <td>
                    <Link
                      className="link-text"
                      href={"/workspace?view=brain&evaluation=" + e.id}
                    >
                      Open result ↗
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function RunLogTable({runs}:{runs:Run[]}) {
  const [selected,setSelected] = useState("");
  const [run,setRun] = useState<Run|null>(null);
  const [error,setError] = useState("");
  const id = selected || runs[0]?.id;
  useEffect(() => {
    setRun(null); setError("");
    if (!id) return;
    const controller = new AbortController();
    api<Run>("runs/"+id,{signal:controller.signal}).then(setRun).catch(e => {if (!controller.signal.aborted) setError(errorText(e));});
    return () => controller.abort();
  },[id]);
  return <Panel title="Execution log" description="Persisted events from the selected run, including errors and stopping reasons.">
    <div className="panel-body"><label className="field"><span>Run</span><select aria-label="Execution log run" value={id || ""} onChange={e=>setSelected(e.target.value)}>{runs.map(r=><option key={r.id} value={r.id}>{dateText(r.created_at)} · {r.status} · {r.id.slice(0,8)}</option>)}</select></label>{error && <p role="alert">{error}</p>}{run?.stop_reason && <p>{run.stop_reason}</p>}</div>
    <div className="table-scroll"><table><thead><tr><th>Time</th><th>Event</th><th>Message</th></tr></thead><tbody>{run?.events?.map(e=><tr key={e.id}><td>{dateText(e.created_at)}</td><td>{e.kind}</td><td>{e.message}{e.details.error != null && <pre>{String(e.details.error)}</pre>}</td></tr>)}{run && !run.events?.length && <tr><td colSpan={3}>No recorded events.</td></tr>}</tbody></table></div>
  </Panel>;
}
