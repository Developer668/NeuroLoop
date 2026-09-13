"use client";
import { useEffect, useState } from "react";
import styles from "./TelemetryPanel.module.css";

type Row = Record<string, unknown>;
type Snapshot = { metrics: Record<string, number | null>; generated_at: number; snapshot_sha256: string; notes: string[] } & Record<string, unknown>;
const tabs = ["Overview", "Execution logs", "Evidence & models", "Decision gates", "Workers & storage", "Run history"] as const;
type Tab = typeof tabs[number];
const label = (s: string) => s.replaceAll("_", " ");
const format = (v: unknown): string => v == null ? "Unavailable" : typeof v === "number" ? new Intl.NumberFormat("en", { maximumFractionDigits: 2 }).format(v) : typeof v === "object" ? JSON.stringify(v) : String(v);
const pct = (v: number | null | undefined) => v == null ? "Unavailable" : `${(v * 100).toFixed(1)}%`;
function save(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function cell(key: string, v: unknown) {
  if (v != null && (key.endsWith("_at") || key === "heartbeat_at") && typeof v === "number") return new Date(v * 1000).toLocaleString();
  if (key.endsWith("_url") && typeof v === "string" && v.startsWith("https://wandb.ai/")) return <a href={v} target="_blank" rel="noreferrer">Open evidence ↗</a>;
  if (key === "status" || key.endsWith("_status") || key === "delivery" || key === "applied_action") return <span className={styles.badge} data-failure={/FAIL|BLOCK|UNCERTAIN|UNAVAILABLE/.test(String(v))}>{format(v)}</span>;
  return format(v);
}
function DataTable({ title, rows, columns, query }: { title: string; rows: Row[]; columns: string[]; query: string }) {
  const [page, setPage] = useState(0), [sort, setSort] = useState<string | null>(null), [descending, setDescending] = useState(false);
  const matching = rows.filter(r => !query || JSON.stringify(r).toLowerCase().includes(query.toLowerCase()));
  const ordered = sort ? [...matching].sort((a, b) => {
    const av = a[sort], bv = b[sort]; const comparison = typeof av === "number" && typeof bv === "number" ? av - bv : format(av).localeCompare(format(bv));
    return descending ? -comparison : comparison;
  }) : matching;
  const pages = Math.max(1, Math.ceil(ordered.length / 20)), current = Math.min(page, pages - 1);
  const csv = () => save(`${title.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}.csv`, [columns, ...ordered.map(r => columns.map(k => r[k] == null ? "" : format(r[k])))].map(row => row.map(v => `"${String(v).replaceAll('"', '""')}"`).join(",")).join("\n"), "text/csv;charset=utf-8");
  return <section className={styles.panel}><div className={styles.sectionHeading}><div><h3>{title}</h3><span>{matching.length} of {rows.length} records</span></div><button onClick={csv} disabled={!matching.length}>Export CSV</button></div>
    {!matching.length ? <p className={styles.empty}>{query ? "No records match your search." : "No recorded evidence yet. This is not counted as a successful execution."}</p> : <>
      <div className={styles.tableScroll}><table><caption className={styles.srOnly}>{title}</caption><thead><tr>{columns.map(k => <th key={k} aria-sort={sort === k ? descending ? "descending" : "ascending" : "none"}><button onClick={() => { setDescending(sort === k ? !descending : false); setSort(k); }}>{label(k)} {sort === k ? descending ? "↓" : "↑" : "↕"}</button></th>)}</tr></thead><tbody>{ordered.slice(current * 20, current * 20 + 20).map((r, i) => <tr key={String(r.trace_id || r.event_id || r.evidence_id || r.backup_id || r.job_id || i)}>{columns.map(k => <td key={k}>{cell(k, r[k])}</td>)}</tr>)}</tbody></table></div>
      <div className={styles.pagination}><span>Page {current + 1} of {pages}</span><button disabled={current === 0} onClick={() => setPage(current - 1)}>Previous</button><button disabled={current + 1 >= pages} onClick={() => setPage(current + 1)}>Next</button></div></>}
  </section>;
}
function Bars({ title, rows, name, amount, unit = "" }: { title: string; rows: Row[]; name: string; amount: string; unit?: string }) {
  const max = Math.max(1, ...rows.map(r => typeof r[amount] === "number" ? Number(r[amount]) : 0));
  return <section className={styles.panel}><h3>{title}</h3><div className={styles.bars}>{rows.length ? rows.map((r, i) => <div key={i}><span>{label(String(r[name]))}</span><div className={styles.track}><i style={{ width: `${Math.max(0, Number(r[amount] || 0)) / max * 100}%` }} /></div><strong>{format(r[amount])}{r[amount] == null ? "" : unit}</strong></div>) : <p className={styles.empty}>No recorded samples.</p>}</div></section>;
}
export default function TelemetryPanel() {
  const [data, setData] = useState<Snapshot | null>(null), [error, setError] = useState(""), [tab, setTab] = useState<Tab>("Overview"), [query, setQuery] = useState(""), [paused, setPaused] = useState(false), [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try { const res = await fetch("/api/v2/telemetry", { signal: controller.signal, cache: "no-store" }); if (!res.ok) throw new Error(`Telemetry request failed (${res.status})`); setData(await res.json()); setError(""); }
      catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Telemetry unavailable"); }
      finally { if (!controller.signal.aborted && !paused) timer = setTimeout(poll, 10000); }
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, [paused, refresh]);
  const rows = (name: string): Row[] => Array.isArray(data?.[name]) ? data[name] as Row[] : [];
  const table = (title: string, source: string, columns: string[]) => <DataTable key={source + query} title={title} rows={rows(source)} columns={columns} query={query} />;
  const m = data?.metrics || {};
  return <div className={styles.root}>
    <header className={styles.header}><div><span className={styles.eyebrow}>OBSERVABILITY · NEUROLOOP V2</span><h1>Logs & Charts</h1><p>Follow execution, inspect decisions, and find the evidence behind every result.</p></div><div className={styles.actions}><button onClick={() => setRefresh(v => v + 1)}>Refresh now</button><button aria-pressed={paused} onClick={() => setPaused(v => !v)}>{paused ? "Resume updates" : "Pause updates"}</button><button disabled={!data} onClick={() => data && save("neuroloop-evidence.json", JSON.stringify(data, null, 2), "application/json")}>Download snapshot</button></div></header>
    <div className={styles.status} role="status"><span className={styles.dot} data-error={!!error} />{error ? `${error}${data ? " · showing last successful snapshot" : ""}` : data ? `${paused ? "Updates paused" : "Refreshes every 10 seconds"} · last received ${new Date(data.generated_at * 1000).toLocaleTimeString()}` : "Loading recorded evidence…"}<span>Backup exports are separate from campaign runs.</span></div>
    <nav className={styles.tabs} aria-label="Logs and charts sections">{tabs.map(t => <button key={t} aria-current={tab === t ? "page" : undefined} onClick={() => { setTab(t); setQuery(""); }}>{t}</button>)}</nav>
    {!data ? <section className={styles.panel}><p>{error || "Connecting to the telemetry API…"}</p></section> : <>
      {tab !== "Overview" && <label className={styles.search}>Search this section<input type="search" value={query} placeholder="Model, run ID, status, error code…" onChange={e => setQuery(e.target.value)} /></label>}
      {tab === "Overview" && <><div className={styles.cards}>{[
          ["Full-loop verified", pct(m.full_loop_verified_rate)],
          ["Plan → generation", pct(m.plan_to_generation_rate)],
          ["Required evidence complete", pct(m.required_evidence_completion_rate)],
          ["Decision → revision", pct(m.decision_to_child_generation_rate)],
          ["Accepted creatives / run", pct(m.human_acceptance_rate)],
          ["Median time to decision", m.median_time_to_decision_seconds == null ? "Unavailable" : `${format(m.median_time_to_decision_seconds)} s`],
          ["First-attempt success", pct(m.first_attempt_success_rate)],
          ["Attempt latency p95", m.p95_attempt_latency_seconds == null ? "Unavailable" : `${format(m.p95_attempt_latency_seconds)} s`],
          ["Quality gain / round", format(m.quality_gain_per_round)],
          ["Cost / accepted creative", m.cost_per_accepted_creative_usd == null ? "Unavailable" : `$${format(m.cost_per_accepted_creative_usd)}`],
          ["Human escalation", pct(m.decision_human_escalation_rate)],
          ["Blocked: missing evidence / capability", format(m.missing_evidence_or_capability_runs)]
        ].map(([name, v]) => <article key={name}><span>{name}</span><strong>{v}</strong></article>)}</div>
        <div className={styles.charts}><Bars title="Execution readiness" rows={rows("readiness_stages")} name="stage" amount="verified_runs" /><Bars title="Campaign funnel" rows={rows("funnel")} name="stage" amount="completed_runs" /><Bars title="Attempt latency by stage" rows={rows("stages")} name="stage" amount="p95_seconds" unit=" s" /><Bars title="Failures, including retries" rows={rows("failures")} name="error_code" amount="attempts" /></div>
        <section className={styles.panel}><h3>What these numbers mean</h3><p>Registered models are not counted as executed. Full-loop verification requires approved planning, evaluated eligible evidence, a recorded decision and a generated revision child.</p><p>{format(m.recorded_total_tokens)} tokens are recorded across {format(m.token_covered_attempts)} / {format(m.model_attempts)} attempts. {format(m.unknown_cost_attempts)} attempts lack dollar receipts. Unknown costs are unavailable, not zero.</p><p>Accepted creatives per started run: {pct(m.human_acceptance_rate)} · eligible candidates: {pct(m.eligible_candidate_rate)} · quality gain per round: {format(m.quality_gain_per_round)}.</p></section></>}
      {tab === "Execution logs" && <><section className={styles.panel}><h3>Reliability & cost coverage</h3><p>Eventual job success: {pct(m.eventual_job_success_rate)} · retry rate: {pct(m.retry_rate)} · uncertain jobs: {format(m.uncertain_jobs)} · dead letters: {format(m.dead_letter_jobs)} · cancellations: {format(m.cancelled_jobs)}.</p><p>Recorded cost: {m.known_attempt_cost_usd == null ? "Unavailable" : `$${format(m.known_attempt_cost_usd)}`} · attempts without dollar receipts: {format(m.unknown_cost_attempts)}. Known cost is a partial total when receipts are missing.</p></section>{table("Model attempts", "attempts", ["started_at", "run_id", "stage", "attempt", "status", "latency_seconds", "error_code", "model", "total_tokens", "cost_usd", "weave_url"])}{table("State transitions · latest 1,000", "events", ["created_at", "run_id", "event", "job_id", "attempt", "code", "action", "outcome"])}{table("Trace delivery & hierarchy", "trace_log", ["started_at", "stage", "trace_id", "parent_id", "status", "delivery", "weave_url"])}</>}
      {tab === "Evidence & models" && <><section className={styles.panel}><h3>Model evidence, kept in context</h3><p>Standalone notebook receipts are not campaign completions. GLM, TRIBE and TSAM estimates retain their separate model and comparison context. Open Brain & emotion or the campaign Media library for the media and detailed neural outputs.</p></section>{table("Model evaluation receipts", "model_receipts", ["created_at", "evaluator", "model", "status", "asset_id", "evidence_id", "comparison_key"])}{table("GLM quality cohorts", "quality_samples", ["created_at", "media_kind", "evaluator", "quality", "constraints", "cohort", "asset_id"])}{table("Campaign evidence eligibility", "candidate_evidence", ["creative_id", "eligible", "required_evidence_complete", "missing_evaluators", "constraints_pass", "constraints_fail", "constraints_unknown"])}</>}
      {tab === "Decision gates" && <>{table("Proposed versus applied action", "decision_gates", ["run_id", "stage", "proposed_action", "applied_action", "confidence", "confidence_floor", "engine_override"])}{table("Run stop reasons", "stop_reasons", ["reason", "runs"])}<section className={styles.panel}><p>Final-decision overrides: {pct(m.engine_override_rate)} · human escalations: {pct(m.decision_human_escalation_rate)}. No final decisions means no denominator, not a zero-percent success claim.</p></section></>}
      {tab === "Workers & storage" && <>{table("Worker registration versus campaign execution", "capabilities", ["worker_id", "provider", "capability", "model", "registered_status", "execution_status", "successful_jobs", "last_success_at", "heartbeat_at"])}<section className={styles.panel}><h3>Why W&B has so many runs</h3><p>Each asset or receipt backup has a stable export run. These preserve media and evidence; they do not represent separate advertisements or optimization loops. Outcome snapshots are another export category. The table below lists one record per backup identity.</p></section>{table("Artifact backup receipts", "artifact_delivery", ["category", "backup_id", "status", "updated_at", "content_sha256", "artifact_url"])}</>}
      {tab === "Run history" && <>{table("Campaign outcomes", "runs", ["created_at", "run_id", "state", "stop_reason", "generated_candidates", "decisions", "accepted_creatives", "time_to_decision_seconds"])}{table("Verification by run", "readiness", ["run_id", "control_plane_verified", "plan_review_verified", "plan_approved", "generation_verified", "vision_verified", "eligible_evidence_verified", "decision_verified", "child_generation_verified", "full_loop_verified"])}</>}
      <details className={styles.definitions}><summary>Data definitions & snapshot identity</summary><ul>{data.notes.map(n => <li key={n}>{n}</li>)}</ul><code>{data.snapshot_sha256}</code></details>
    </>}
  </div>;
}
