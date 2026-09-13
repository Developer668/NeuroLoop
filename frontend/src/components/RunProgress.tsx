"use client";
import { useEffect, useState } from "react";
import styles from "./RunProgress.module.css";

type Job = { id: string; kind: string; status: string; capability: string; started_at?: number | null; completed_at?: number | null; created_at?: number; progress: Record<string, unknown>; error: Record<string, unknown> | null };
const stepNames: Record<string, string> = { PLAN: "Planning your ad", REVIEW_PLAN: "Reviewing the plan", GENERATE: "Creating media", EVALUATE: "Checking the result", DECIDE: "Choosing the next step", SUMMARY: "Writing your results summary" };
const statusNames: Record<string, string> = { PENDING: "Waiting to start", RETRY: "Waiting to retry", LEASED: "Working", SUCCEEDED: "Complete", FAILED: "Failed", UNCERTAIN: "Result needs checking", CANCELLED: "Cancelled" };
const stepName = (kind: string) => stepNames[kind] || kind.replaceAll("_", " ").toLowerCase();
export default function RunProgress({ runId, state, stopReason, jobs, online, updatedAt, open }: {
  runId: string; state: string; stopReason: string | null; jobs: Job[];
  online: boolean; updatedAt?: number; open: () => void;
}) {
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const active = jobs.find(j => j.status === "LEASED");
  const queued = jobs.find(j => ["PENDING", "RETRY"].includes(j.status));
  const failed = jobs.find(j => ["FAILED", "UNCERTAIN"].includes(j.status));
  const finished = jobs.filter(j => j.status === "SUCCEEDED").length;
  const waiting = !active && !!queued;
  const generated = jobs.filter(j => j.kind === "GENERATE" && j.status === "SUCCEEDED").length;
  const planBlocked = !!stopReason?.startsWith("TYPESAFE_PLAN");
  const title = planBlocked ? generated ? "Revision planning stopped — previous outputs are saved" : "Planning stopped — no ad was generated" : stopReason ? "This run has stopped" : active ? stepName(active.kind) : waiting ? `${stepName(queued.kind)} is queued` : `Run status: ${state.replaceAll("_", " ").toLowerCase()}`;
  const heartbeat = typeof active?.progress.updated_at === "number" ? active.progress.updated_at : undefined;
  const elapsed = active?.started_at ? Math.max(0, clock / 1000 - active.started_at) : 0;
  const durations = active ? jobs.filter(j => j.status === "SUCCEEDED" && j.kind === active.kind && j.capability === active.capability && j.started_at && j.completed_at && j.completed_at > j.started_at).map(j => j.completed_at! - j.started_at!).sort((a, b) => a - b) : [];
  const typical = durations.length >= 3 ? durations[Math.floor(durations.length / 2)] : null;
  const stale = !!updatedAt && clock - updatedAt > 10000;
  return <section className={styles.panel} aria-label="Creative loop progress">
    <div className={styles.heading}><div><span>CREATIVE LOOP · {runId.slice(0, 8)}</span><h2 role="status">{title}</h2></div><button onClick={open}>View run & outputs</button></div>
    <progress aria-label="Completed jobs currently scheduled, not total loop completion" value={finished} max={Math.max(jobs.length, 1)} />
    {(active || waiting) && <div className={styles.activity} role="status"><span className={stale ? undefined : styles.spinner} aria-hidden="true" />{stale ? "Connection delayed — reconnecting automatically" : active ? "Processing · waiting for the model’s next update" : "Queued · waiting for a worker"}</div>}
    <p>{finished} of {jobs.length} scheduled steps complete. More steps may be added as the ad improves.</p>
    <p><strong>{generated} generated media outputs.</strong> Uploaded references are separate from generated results.</p>
    {planBlocked && <p role="alert">{generated ? "The revision plan did not pass review, so no new generation was started. Earlier outputs and their evaluations remain available below." : "The plan review did not meet the requirements for starting generation. The notebook has no generation job to run."} Review the recorded plan and confidence in View run &amp; outputs.</p>}
    {waiting && <p className={styles.notice}>{online ? `${stepName(queued.kind)} is queued. Connected workers may be finishing another campaign before accepting this step.` : "The notebook is offline. Your request is saved. Open Connections & settings and start the notebook worker to continue."}</p>}
    {active?.started_at && <p>Time in this step: {Math.floor(elapsed / 60)}m {Math.floor(elapsed % 60)}s. {typical === null ? "Estimating time: not enough completed jobs of this type yet." : elapsed < typical ? `Rough estimate: about ${Math.max(1, Math.ceil((typical - elapsed) / 60))} min remaining, based on ${durations.length} completed ${active.capability} jobs in this run. Workload and model loading can change this.` : "Taking longer than previous jobs of this type. Still waiting for the model result."}</p>}
    {waiting && queued.created_at && <p>Waiting for {Math.max(0, Math.floor(clock / 1000 - queued.created_at))} seconds.</p>}
    {active && <p>{String(active.progress.message || "The notebook has started this step. Waiting for its next update.")}{typeof active.progress.elapsed_seconds === "number" && ` · Reported execution time: ${Math.floor(active.progress.elapsed_seconds)}s`}</p>}
    {failed && <p role="alert">{failed.kind}: {failed.status} · {String(failed.error?.code || "Inspect the job details for the recorded error.")}</p>}
    {stopReason && <p>Recorded stop reason: {stopReason.replaceAll("_", " ").toLowerCase()}. Open the run to review the details.</p>}
    <p><a href="/workspace?view=docs#guide-help">What does this status mean?</a></p>
    <ol className={styles.jobs}>{jobs.map(j => <li key={j.id}><strong>{stepName(j.kind)}</strong><span>{statusNames[j.status] || j.status}</span></li>)}</ol>
    <small>{updatedAt ? `Last successful sync ${Math.max(0, Math.floor((clock - updatedAt) / 1000))}s ago` : "Waiting for the first sync"}{heartbeat ? ` · Worker heartbeat ${Math.max(0, Math.floor(clock / 1000 - heartbeat))}s ago` : ""}</small>
  </section>;
}
