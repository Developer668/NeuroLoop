"use client";
import { useState, useRef, type FormEvent } from "react";
import dynamic from "next/dynamic";
import {
  ArrowRight,
  Upload,
  AlertCircle,
  ShieldCheck,
  FileText,
} from "lucide-react";
import { api, Asset, Project, Run, Capability } from "@/lib/types";
import { Brand, Modal, errorText } from "./UI";

type TimedWord = { text: string; start: number; end: number };
const EntranceBrain = dynamic(() => import("./BrainCanvas"), { ssr: false });
export function ConnectGate({ onConnected }: { onConnected: () => void }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [token, setToken] = useState("");
  async function connect(local: boolean) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(local ? { mode: "local" } : { token }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Authentication failed");
      setToken("");
      onConnected();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <section className="auth-story">
        <Brand />
        <div className="auth-observatory">
          <EntranceBrain publicMesh cinematic />
        </div>
        <div className="auth-story-copy">
          <span className="eyebrow">A SPACE FOR CLOSER LOOKS</span>
          <h1>
            Bring something
            <br />
            worth exploring.
          </h1>
          <p>
            Your creative. A considered experiment. A record you can return to.
          </p>
        </div>
        <span className="auth-note">
          20,484 SURFACE VERTICES / TWO HEMISPHERES
        </span>
      </section>
      <section className="auth-form">
        <div className="auth-card">
          <span className="eyebrow">Welcome to the lab</span>
          <h2>Open your workspace.</h2>
          <p>
            Pick up where you left off. Your creatives, experiments and saved
            responses are waiting here.
          </p>
          {error && (
            <div role="alert" className="notice error">
              <AlertCircle size={16} />
              {error}
            </div>
          )}
          <button
            className="button primary"
            disabled={busy}
            onClick={() => void connect(true)}
          >
            {busy ? "Connecting…" : "Connect to this computer"}
            <ArrowRight size={15} />
          </button>
          <details className="token-access">
            <summary>Connect with an access token</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void connect(false);
              }}
            >
              <label className="field">
                <span>Workspace access token</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste your token"
                  required
                  minLength={24}
                  maxLength={256}
                />
              </label>
              <button className="button" disabled={busy || !token}>
                Connect securely
              </button>
            </form>
          </details>
          <footer>
            <a href="/">Return to homepage</a>
          </footer>
        </div>
      </section>
    </div>
  );
}
export function UploadBox({
  onUploaded,
}: {
  onUploaded: (assets: Asset[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null),
    [drag, setDrag] = useState(false),
    [busy, setBusy] = useState(false),
    [items, setItems] = useState<{ name: string; status: string }[]>([]);
  async function upload(files: FileList | File[]) {
    if (busy) return;
    setBusy(true);
    const array = Array.from(files).slice(0, 10);
    setItems(array.map((f) => ({ name: f.name, status: "Queued" })));
    const uploaded: Asset[] = [];
    for (let i = 0; i < array.length; i++) {
      const f = array[i];
      setItems((old) =>
        old.map((v, j) => (j === i ? { ...v, status: "Uploading…" } : v)),
      );
      try {
        if (f.size > 200 * 1024 * 1024) throw new Error("File exceeds 200 MB");
        const form = new FormData();
        form.append("file", f);
        const result = await api<Asset>("assets", {
          method: "POST",
          body: form,
        });
        uploaded.push(result);
        setItems((old) =>
          old.map((v, j) => (j === i ? { ...v, status: "Saved" } : v)),
        );
      } catch (e) {
        setItems((old) =>
          old.map((v, j) => (j === i ? { ...v, status: errorText(e) } : v)),
        );
      }
    }
    setBusy(false);
    if (input.current) input.current.value = "";
    if (uploaded.length) onUploaded(uploaded);
  }
  return (
    <div>
      <input
        ref={input}
        type="file"
        className="visually-hidden"
        aria-label="Upload creative files"
        accept=".mp4,.mov,.webm,.mkv,.avi,.png,.jpg,.jpeg,.webp,.mp3,.wav,.ogg,.flac,.txt"
        multiple
        onChange={(e) => {
          if (e.target.files) void upload(e.target.files);
        }}
      />
      <div
        className={"upload-zone " + (drag ? "dragging" : "")}
        role="button"
        tabIndex={0}
        aria-disabled={busy}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            if (!busy) input.current?.click();
          }
        }}
        onClick={() => {
          if (!busy) input.current?.click();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          void upload(e.dataTransfer.files);
        }}
      >
        <Upload size={25} />
        <h3>
          {busy ? "Saving your work…" : "Bring something worth exploring."}
        </h3>
        <p>Drop creative files here, or click to browse.</p>
        <small>
          Video, image, audio or UTF-8 text · 200 MB per file · 60-second media
          limit
        </small>
      </div>
      {items.length > 0 && (
        <div className="upload-progress" aria-live="polite">
          {items.map((item, i) => (
            <div key={i}>
              <span>{item.name}</span>
              <span>{item.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
export function ProjectDialog({
  assets,
  project,
  initialAsset,
  onClose,
  onSaved,
}: {
  assets: Asset[];
  project?: Project;
  initialAsset?: string;
  onClose: () => void;
  onSaved: (p: Project) => void;
}) {
  const [name, setName] = useState(project?.name || ""),
    [brief, setBrief] = useState(project?.brief || ""),
    [assetId, setAssetId] = useState(project?.asset_id || initialAsset || ""),
    [refs, setRefs] = useState<string[]>(project?.reference_ids || []),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const original = assets.find((a) => a.id === assetId);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<Project>(
        project ? "projects/" + project.id : "projects",
        {
          method: project ? "PUT" : "POST",
          body: JSON.stringify({
            name,
            brief,
            asset_id: assetId || null,
            reference_ids: refs,
            constraints: project?.constraints || {
              preserve_duration: true,
              preserve_audio: true,
              max_filter_edits: 2,
            },
          }),
        },
      );
      onSaved(result);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={project ? "Edit project" : "A new line of inquiry"}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <p className="modal-subtitle">
          Keep the brief, original, and references together. A run snapshots
          these choices so its objective cannot drift.
        </p>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        <label className="field">
          <span>Project name</span>
          <input
            required
            maxLength={120}
            autoFocus
            placeholder="e.g. Autumn launch — first cut"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Creative brief</span>
          <textarea
            maxLength={4000}
            placeholder="What are you exploring? What must stay the same?"
            value={brief}
            onChange={(e) => setBrief(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Original creative</span>
          <select
            aria-label="Original creative"
            value={assetId}
            onChange={(e) => {
              setAssetId(e.target.value);
              setRefs([]);
            }}
          >
            <option value="">Choose later</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} · {a.kind}
              </option>
            ))}
          </select>
        </label>
        <div className="field">
          <span>
            Reference creatives <small>optional for analysis · up to 3</small>
          </span>
          <div className="check-list">
            {assets
              .filter(
                (a) =>
                  a.id !== assetId &&
                  (!original || a.kind === original.kind) &&
                  a.sha256 !== original?.sha256,
              )
              .map((a) => (
                <label key={a.id} className="check-card">
                  <input
                    type="checkbox"
                    checked={refs.includes(a.id)}
                    disabled={!refs.includes(a.id) && refs.length >= 3}
                    onChange={(e) =>
                      setRefs((old) =>
                        e.target.checked
                          ? [...old, a.id]
                          : old.filter((v) => v !== a.id),
                      )
                    }
                  />
                  <span>{a.name}</span>
                </label>
              ))}
            {assets.filter(
              (a) =>
                a.id !== assetId && (!original || a.kind === original.kind),
            ).length === 0 && (
              <small>
                Upload another creative of the same media type to add a
                reference.
              </small>
            )}
          </div>
        </div>
        <div className="dialog-footer">
          <button type="button" className="button" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Saving…" : project ? "Save changes" : "Create project"}
            <ArrowRight size={14} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
export function ComposeDialog({
  asset,
  onClose,
  onSaved,
}: {
  asset: Asset;
  onClose: () => void;
  onSaved: (a: Asset) => void;
}) {
  const [headline, setHeadline] = useState(""),
    [subline, setSubline] = useState(""),
    [duration, setDuration] = useState(8),
    [start, setStart] = useState(1),
    [aspect, setAspect] = useState("landscape"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<Asset>("creatives", {
        method: "POST",
        body: JSON.stringify({
          asset_id: asset.id,
          headline,
          subline,
          duration,
          headline_start: start,
          aspect,
        }),
      });
      onSaved(result);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Compose an editable creative" onClose={onClose}>
      <form onSubmit={submit}>
        <p className="modal-subtitle">
          Source: {asset.name}. Create a deterministic composition with an
          independently editable headline timeline. This renders supplied
          assets; it does not generate new imagery.
        </p>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        <div className="notice warning">
          The composition is silent. Original source files are never changed.
        </div>
        <label className="field">
          <span>Headline</span>
          <input
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            required
            maxLength={120}
            placeholder="Words worth keeping."
          />
        </label>
        <label className="field">
          <span>Supporting line</span>
          <input
            value={subline}
            onChange={(e) => setSubline(e.target.value)}
            maxLength={200}
          />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Duration (seconds)</span>
            <input
              type="number"
              min={5}
              max={30}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>Headline appears at</span>
            <input
              type="number"
              min={0}
              max={duration - 0.5}
              step={0.25}
              value={start}
              onChange={(e) => setStart(Number(e.target.value))}
            />
          </label>
        </div>
        <label className="field">
          <span>Frame</span>
          <select
            aria-label="Frame"
            value={aspect}
            onChange={(e) => setAspect(e.target.value)}
          >
            <option value="landscape">Landscape · 16:9</option>
            <option value="portrait">Portrait · 9:16</option>
            <option value="square">Square · 1:1</option>
          </select>
        </label>
        <div className="dialog-footer">
          <button
            type="button"
            className="button"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? "Rendering composition…" : "Render creative"}
            <ArrowRight size={14} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
