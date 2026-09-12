"use client";
import { useEffect, useState } from "react";
import { PixelLoading } from "./ReleaseMotion";
import { api } from "@/lib/types";
import { Badge, Panel, dateText, errorText } from "./UI";
export default function ConnectionChecks() {
  const [receipts,setReceipts]=useState<{id:string;name:string;status:string;url:string|null;attempts:number;error:string|null}[]>([]);
  const loadReceipts=()=>api<{receipts:typeof receipts}>("connections/receipts").then(value=>setReceipts(value.receipts));
  useEffect(()=>{void loadReceipts().catch(()=>{});},[]);
  const [result, setResult] = useState<{
    checked_at: string;
    connections: { name: string; status: string; detail: string }[];
  } | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function check() {
    setBusy(true);
    setError("");
    try {
      setResult(await api("connections/check", { method: "POST" }));
      await loadReceipts();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title="Services & sponsor connections"
      description="See what this installation actually uses and what still needs configuration."
      action={
        <button className="button" disabled={busy} onClick={() => void check()}>
          {busy ? "Checking services…" : "Check service connections"}
        </button>
      }
    >
      {busy&&<PixelLoading label="Checking connected services"/>}
      <div className="panel-body"><a href="https://wandb.ai/jerry-wen0616-santa-clara-university/neuroloop/weave/traces" target="_blank" rel="noreferrer">Open NeuroLoop in Weave ↗</a><p>Remote trace receipts are confirmed by reading the completed call back from W&B.</p>{receipts.length>0?<div className="table-scroll"><table><thead><tr><th>Operation</th><th>Delivery</th><th>Attempts</th><th>Receipt</th></tr></thead><tbody>{receipts.slice(0,12).map(row=><tr key={row.id}><td>{row.name.replace('neuroloop.','')}</td><td>{row.status}{row.error?` · ${row.error}`:''}</td><td>{row.attempts}</td><td>{row.url?<a href={row.url} target="_blank" rel="noreferrer">View trace ↗</a>:'Awaiting remote confirmation'}</td></tr>)}</tbody></table></div>:<p>No recorded remote deliveries yet.</p>}</div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {result ? (
        <>
          <div className="sponsor-status">
            {result.connections.map((c) => (
              <article key={c.name}>
                <strong>{c.name}</strong>
                <div>
                  <Badge value={c.status} />
                </div>
                <p>{c.detail}</p>
              </article>
            ))}
          </div>
          <div className="panel-footer">
            Checked {dateText(result.checked_at)}. Configuration alone does not
            establish a successful trace export or research job.
          </div>
        </>
      ) : (
        <div className="panel-body status-detail">
          marimo provides the local research notebook. Weave records traces when
          credentials are configured. ARIA uses the restricted local Launch queue.
          W&B Inference, CoreWeave cloud and TypeSafe are deferred.
          Run the check for this computer’s current state.
        </div>
      )}
    </Panel>
  );
}
