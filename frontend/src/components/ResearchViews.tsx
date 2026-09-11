"use client";
import { useState, useEffect } from "react";
import {
  ArrowUpRight,
  Copy,
  Check,
  FlaskConical,
  GitBranch,
  ChartNoAxesCombined,
  ShieldCheck,
  Plug,
  Layers,
} from "lucide-react";
import { api, Dashboard, PolicyStat, score } from "@/lib/types";
import { Panel, Badge, Empty, errorText, dateText, External } from "./UI";
import ProfileSettings from "./ProfileSettings";
import { HardwarePanel } from "./Activity";
import { LineChart } from "./Charts";
import ResearchEvidence from "./ResearchEvidence";
import ConnectionChecks from "./ConnectionChecks";

export function CompareView({ data }: { data: Dashboard }) {
  const [selected, setSelected] = useState<string[]>([]),
    [result, setResult] = useState<{
      matrix: number[][];
      evaluation_ids: string[];
      metric: string;
      meaning: string;
    } | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const chosenProfile = data.evaluations.find(
    (e) => e.id === selected[0],
  )?.profile;
  async function compare() {
    setBusy(true);
    setError("");
    try {
      setResult(
        await api("compare", {
          method: "POST",
          body: JSON.stringify({ evaluation_ids: selected }),
        }),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack">
      <Panel
        title="How similar are these creative responses?"
        description="Choose two or more saved analyses. Compare measures how closely their predicted cortical patterns agree; it does not rank their advertising effectiveness."
      >
        <div className="panel-body">
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          {data.evaluations.length ? (
            <>
              <div className="comparison-guide">
                <strong>{selected.length} selected</strong>
                <span>
                  {chosenProfile
                    ? "Showing compatibility with your first selection. Clear it to choose another model version."
                    : "Choose your first analysis. Compatible results will remain available."}
                </span>
                {selected.length > 0 && (
                  <button
                    className="button"
                    onClick={() => {
                      setSelected([]);
                      setResult(null);
                      setError("");
                    }}
                  >
                    Clear selection
                  </button>
                )}
              </div>
              <div className="record-select">
                {data.evaluations.map((e) => (
                  <label
                    className={
                      "check-card " +
                      (chosenProfile && chosenProfile !== e.profile
                        ? "incompatible"
                        : "")
                    }
                    key={e.id}
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(e.id)}
                      disabled={
                        (!selected.includes(e.id) && selected.length >= 12) ||
                        Boolean(chosenProfile && chosenProfile !== e.profile)
                      }
                      onChange={(event) => {
                        setSelected((old) =>
                          event.target.checked
                            ? [...old, e.id]
                            : old.filter((x) => x !== e.id),
                        );
                        setResult(null);
                        setError("");
                      }}
                    />
                    <span>
                      <strong>
                        {data.assets.find((a) => a.id === e.asset_id)?.name ||
                          e.asset_id}
                      </strong>
                      <small>
                        {dateText(e.created_at)} ·{" "}
                        {e.evidence.shape.join(" × ")}
                      </small>
                      {chosenProfile && chosenProfile !== e.profile && (
                        <small>Different model version · cannot compare</small>
                      )}
                    </span>
                  </label>
                ))}
              </div>
              <button
                className="button primary"
                onClick={() => void compare()}
                disabled={busy || selected.length < 2}
              >
                {busy ? "Comparing…" : "Compare selected"}
                <ArrowUpRight size={14} />
              </button>
            </>
          ) : (
            <Empty
              title="Start with a measurement"
              text="Analyze two creatives first. Their saved cortical arrays can then be compared without another model call."
            />
          )}
        </div>
      </Panel>
      {result && (
        <Panel
          title="Cortical-pattern similarity"
          description="Spatially centered cosine, averaged over normalized time bins."
          footer={result.meaning}
        >
          <div className="table-scroll">
            <table className="matrix">
              <thead>
                <tr>
                  <th>Evaluation</th>
                  {result.evaluation_ids.map((id, i) => (
                    <th key={id}>#{i + 1}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.matrix.map((row, i) => (
                  <tr key={i}>
                    <td>
                      <strong>#{i + 1}</strong>{" "}
                      {data.assets.find(
                        (a) =>
                          a.id ===
                          data.evaluations.find(
                            (e) => e.id === result.evaluation_ids[i],
                          )?.asset_id,
                      )?.name || result.evaluation_ids[i].slice(0, 8)}
                    </td>
                    {row.map((v, j) => (
                      <td
                        className={i !== j && v > 0.7 ? "cell-match" : ""}
                        key={j}
                      >
                        {score(v)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <div className="notice info">
        A higher reference score means greater similarity under this declared
        comparison. It is not a measured human preference, emotion probability,
        or conversion forecast.
      </div>
    </div>
  );
}

const TOOLS = [
  [
    "list_evaluations",
    "Find compatible saved analysis IDs and model versions.",
  ],
  ["get_system_status", "Read actual GPU and system memory headroom."],
  [
    "get_research_ledger",
    "Inspect recorded experiments, costs and archived history.",
  ],
  ["get_capabilities", "Inspect actual model and integration readiness."],
  ["list_workspace", "Find saved projects, assets, and run IDs."],
  ["create_project", "Bind an original, references, and a brief."],
  ["evaluate_creative", "Queue a real cortical analysis."],
  ["optimize_creative", "Run permitted edits under a fixed budget."],
  ["get_run", "Read progress, experiments, and stopping reason."],
  ["cancel_run", "Stop new work at a safe checkpoint."],
  ["get_evidence", "Read the saved numerical result and provenance."],
  ["export_result", "Get authorized asset and evidence paths."],
];
export function ConnectionsView() {
  const [codeTab, setCodeTab] = useState<"codex" | "json">("codex");
  const [copied, setCopied] = useState(false),
    [error, setError] = useState(""),
    [testing, setTesting] = useState(false),
    [connection, setConnection] = useState<{
      status: string;
      server: string;
      tools: string[];
      schemas?: {
        name: string;
        description: string;
        inputSchema: Record<string, unknown>;
      }[];
    } | null>(null);
  async function test() {
    setTesting(true);
    setError("");
    try {
      setConnection(await api("connections/mcp/test", { method: "POST" }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setTesting(false);
    }
  }
  const endpoint = "http://127.0.0.1:8010/mcp/";
  const config = JSON.stringify(
    {
      mcpServers: {
        neuroloop: {
          url: endpoint,
          headers: { Authorization: "Bearer <NEUROLOOP_AUTH_TOKEN>" },
        },
      },
    },
    null,
    2,
  );
  const command =
    'codex mcp add neuroloop -- "D:\\NeuroLoop\\.runtimes\\app\\Scripts\\python.exe" "D:\\NeuroLoop\\scripts\\mcp_stdio.py"';
  const code = codeTab === "codex" ? command : config;
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      setError(
        "Clipboard access was denied. Select the configuration text to copy it manually.",
      );
    }
  }
  return (
    <div className="stack">
      <div className="grid-main">
        <Panel title="One engine. Your agent’s tools.">
          <div className="panel-body">
            <span className="eyebrow">Streamable HTTP / authenticated</span>
            <p style={{ margin: "14px 0 22px", fontSize: 13, lineHeight: 1.9 }}>
              Your agent uses the same saved assets, experiment controller, and
              numerical readout as this workspace. Long operations return a run
              ID; the model stays on the server.
            </p>
            <div className="connection-endpoint">
              <Plug size={16} />
              {endpoint}
            </div>
            <div className="button-row section-space">
              <button
                className="button primary"
                disabled={testing}
                onClick={() => void test()}
              >
                {testing ? "Testing handshake…" : "Test MCP connection"}
              </button>
              <a
                className="button"
                href="/api/connections/mcp/config"
                download="neuroloop-mcp.json"
              >
                Download client config
              </a>
            </div>
            {connection && (
              <div className="notice info section-space">
                Connected to {connection.server}. {connection.tools.length}{" "}
                tools discovered through a real MCP handshake.
              </div>
            )}
            <p className="status-detail section-space">
              The downloaded configuration includes an 8-hour access token.
              Import it into a compatible desktop client on this computer. Keep
              the file private and download a fresh one when it expires.
            </p>
            <div className="system-block">
              This deployment listens on loopback. Desktop clients on this
              computer can connect. A cloud agent needs a separately secured
              HTTPS deployment; no public tunnel is opened automatically.
            </div>
          </div>
        </Panel>
        <div className="connection-code">
          <div className="code-window-head">
            <span>
              {codeTab === "codex"
                ? "PowerShell / Codex CLI"
                : "neuroloop-mcp.json"}
            </span>
            <span>LOCAL CONNECTION</span>
          </div>
          <div className="button-row">
            <button
              className="button"
              aria-pressed={codeTab === "codex"}
              onClick={() => setCodeTab("codex")}
            >
              Codex
            </button>
            <button
              className="button"
              aria-pressed={codeTab === "json"}
              onClick={() => setCodeTab("json")}
            >
              HTTP client JSON
            </button>
          </div>
          <button className="copy-btn" onClick={() => void copy()}>
            {copied ? <Check size={12} /> : <Copy size={12} />}{" "}
            {copied ? "Copied" : "Copy"}
          </button>
          <pre>
            <code>{code}</code>
          </pre>
          <p style={{ fontSize: 10, color: "#9fbfcb", marginTop: 15 }}>
            {codeTab === "codex"
              ? "Run this command once on this computer, then reload MCP connections in Codex. The local stdio connection needs no copied token. Start NeuroLoop before asking an agent to run inference."
              : "This is a template. Download client config for an expiring authenticated HTTP configuration."}
          </p>
        </div>
      </div>
      {error && <div className="notice error">{error}</div>}
      <Panel
        title="Public tool surface"
        description="The full tool schema is discoverable by an authenticated MCP client."
      >
        <div className="panel-body tool-list">
          {[
            ...TOOLS,
            [
              "compare_creatives",
              "Compare saved responses without new GPU calls.",
            ],
            [
              "render_creative",
              "Render exact copy with a managed visual asset.",
            ],
            ["run_experiment", "Test a specified permitted operator."],
            ["get_external_receipts", "Read confirmed Weave trace URLs and delivery errors."],
            ["propose_agent_experiment", "Prepare a bounded proposal and review its exact contract."],
            ["execute_agent_proposal", "Queue an explicitly reviewed proposal using its digest."],
          ].map(([name, text]) => (
            <div className="tool-card" key={name}>
              <code>{name}</code>
              <p>{text}</p>
              {connection?.schemas?.find((tool) => tool.name === name) && (
                <details>
                  <summary>Tool parameters</summary>
                  <pre className="tool-schema">
                    {JSON.stringify(
                      connection.schemas.find((tool) => tool.name === name)
                        ?.inputSchema,
                      null,
                      2,
                    )}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      </Panel>
      <div className="grid-two">
        <Panel title="Bring an asset">
          <div className="panel-body status-detail">
            Upload media through this workspace or the authenticated{" "}
            <code>POST /api/assets</code> endpoint. MCP tools reference the
            returned managed asset ID, never an arbitrary local path or URL.
          </div>
        </Panel>
        <Panel title="W&B is a separate connection">
          <div className="panel-body status-detail">
            NeuroLoop runs experiments. W&B MCP lets an authorized agent inspect
            W&B runs and traces. W&B credentials and permissions are configured
            independently.
            <div style={{ marginTop: 12 }}>
              <External href="https://github.com/wandb/wandb-mcp-server">
                Official W&B MCP documentation
              </External>
            </div>
          </div>
        </Panel>
      </div>
      <ConnectionChecks />
    </div>
  );
}
export function ResearchView({ data }: { data: Dashboard }) {
  const [stats, setStats] = useState<PolicyStat[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    api<{ statistics: PolicyStat[] }>("policy")
      .then((d) => {
        if (alive) setStats(d.statistics);
      })
      .catch((e) => {
        if (alive) setError(errorText(e));
      });
    return () => {
      alive = false;
    };
  }, [data.counts.experiments]);
  return (
    <div className="stack">
      <ResearchEvidence />
      {error && <div className="notice error">{error}</div>}
      <Panel
        title="Operator experience · all recorded history"
        description="Outcomes belong to the recorded model, reference set, and creative context—not to humans in general."
      >
        {stats.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Operator</th>
                  <th>Context</th>
                  <th>Attempts</th>
                  <th>Accepted</th>
                  <th>Mean gain</th>
                  <th>Mean time</th>
                </tr>
              </thead>
              <tbody>
                {stats.map((s) => (
                  <tr key={s.context + s.operator}>
                    <td>{s.operator.replaceAll("_", " ")}</td>
                    <td className="mono-cell">{s.context.slice(0, 9)}</td>
                    <td>{s.attempts}</td>
                    <td>{s.successes}</td>
                    <td className="mono-cell">{score(s.mean_gain)}</td>
                    <td>{s.mean_seconds.toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Experience starts with an experiment"
            text="This table is populated only by evaluated interventions. There are no seeded success rates."
            icon={<GitBranch size={23} />}
          />
        )}
      </Panel>
      <div className="grid-two">
        <Panel title="marimo research application">
          <div className="panel-body">
            <p className="status-detail">
              Inspect the stored experiment ledger, cortical timelines, policy
              statistics, and cost comparisons in a reproducible Python
              application. Opening a notebook view does not trigger new model
              calls.
            </p>
            <div className="button-row section-space">
              <External href="http://localhost:2718">
                Open local research application
              </External>
            </div>
            <div className="system-block">
              Start the research service using the project launcher. Data
              remains local; do not publish private content to an unlisted
              notebook.
            </div>
          </div>
        </Panel>
        <Panel title="ARIA research supervisor">
          <div className="panel-body">
            <Badge value="requires_launch_setup" />
            <p className="status-detail section-space">
              ARIA can review versioned W&B evidence and launch approved
              follow-up jobs once W&B Launch credentials, a queue, and an active
              Launch agent are configured. It cannot change this run’s objective
              or budget.
            </p>
            <div className="section-space">
              <External href="https://docs.wandb.ai/aria/autoresearch">
                ARIA execution requirements
              </External>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
export function SettingsView({ data }: { data: Dashboard }) {
  const c = data.capabilities;
  return (
    <div className="stack">
      <ProfileSettings />
      <div className="grid-two">
        <Panel
          title="Model inventory"
          description="Downloaded does not automatically mean validated."
        >
          <div className="panel-body model-list">
            {c.models.map((m) => (
              <div key={m.name} className="model-row">
                <span className="model-icon">
                  <Layers size={14} />
                </span>
                <span className="model-label">{m.name}</span>
                <Badge value={m.status} />
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Interpretation boundaries">
          <div className="panel-body">
            <div className="data-row">
              <div className="row-copy">
                <strong>TSAM</strong>
                <small>{c.tsam.reason}</small>
              </div>
              <Badge value={c.tsam.status} />
            </div>
            <div className="data-row">
              <div className="row-copy">
                <strong>Kragel brain signatures</strong>
                <small>{c.kragel.reason || c.kragel.meaning}</small>
              </div>
              <Badge value={c.kragel.status} />
            </div>
            <div className="system-block">
              No model training. No personal brain measurement. No inferred
              thoughts, purchase probability, or calibrated emotion output from
              unvalidated signatures.
            </div>
          </div>
        </Panel>
      </div>
      <HardwarePanel />
      {c.generation_providers?.length ? (
        <Panel title="Creative generation providers" description="These are honest capability states. Sponsor-gated providers are not called until access is configured.">
          <div className="panel-body model-list">
            {c.generation_providers.map((provider) => (
              <div key={provider.name} className="data-row">
                <div className="row-copy">
                  <strong>{provider.name}</strong>
                  <small>{provider.detail}</small>
                </div>
                <Badge value={provider.status} />
              </div>
            ))}
          </div>
        </Panel>
      ) : null}
      <Panel
        title="Integration status"
        description="Status reflects this deployment, not a sponsor logo."
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Integration</th>
                <th>Status</th>
                <th>Responsibility</th>
              </tr>
            </thead>
            <tbody>
              {c.integrations.map((i) => (
                <tr key={i.name}>
                  <td>
                    <strong>{i.name}</strong>
                  </td>
                  <td>
                    <Badge value={i.status} />
                  </td>
                  <td>{i.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="grid-two">
        <Panel title="Media capabilities">
          <div className="panel-body">
            <dl className="metrics-list">
              {Object.entries(c.modalities).map(([name, meaning]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{meaning}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Panel>
        <Panel title="Storage & access">
          <div className="panel-body">
            <ShieldCheck size={23} className="accent" />
            <p className="status-detail section-space">
              Single-workspace local deployment with authenticated API and MCP
              access. Source media and tokens are not included in telemetry.
              Public multi-user hosting requires a separate identity and
              authorization deployment.
            </p>
            <div className="system-block">
              TRIBE and TSAM retain their upstream restrictions. Having model
              files on disk does not establish commercial permission.
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
