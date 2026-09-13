"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Plug } from "lucide-react";
import { NeuroMark } from "./Neuro";
import styles from "./LoopComposer.module.css";
import { PromptInput } from "./ui/ai-chat-input";

export type ComposeRequest = {
  prompt: string;
  brand: string;
  kind: "image" | "video";
  aspect: string;
  files: File[];
  duration: number;
};
export default function LoopComposer({
  busy,
  submit,
}: {
  busy: boolean;
  submit: (request: ComposeRequest) => Promise<void>;
}) {
  const [prompt, setPrompt] = useState(""),
    [brand, setBrand] = useState(""),
    [kind, setKind] = useState<"image" | "video">("video"),
    [aspect, setAspect] = useState("16:9"),
    [duration, setDuration] = useState(5),
    [files, setFiles] = useState<File[]>([]);
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem("neuroloop-landing-brief");
      if (!saved) return;
      const draft = JSON.parse(saved);
      if (typeof draft.prompt === "string" && draft.prompt.length <= 8000) {
        setPrompt(draft.prompt);
        if (draft.kind === "image" || draft.kind === "video") setKind(draft.kind);
        sessionStorage.removeItem("neuroloop-landing-brief");
      }
    } catch { /* Storage may be unavailable; the empty composer remains usable. */ }
  }, []);
  const unsupported =
    kind === "image" &&
    files.some((f) => /^(image|video|audio)\//.test(f.type));
  async function send() {
    if (!busy && !unsupported && prompt.trim() && brand.trim())
      await submit({ prompt, brand, kind, aspect, files, duration });
  }
  return (
    <section
      className={`neuro-page ${styles.page}`}
      aria-labelledby="neuro-title"
    >
      <div className="neuro-page-top">
        <span>
          <NeuroMark size={23} /> NEURO AI
        </span>
        <Link href="/workspace?view=settings">
          <Plug size={15} /> Connections <ArrowUpRight size={14} />
        </Link>
      </div>
      <div className="neuro-command-intro">
        <NeuroMark size={64} />
        <div>
          <h2 id="neuro-title">Neuro AI</h2>
          <p>Bring your ideas and references. Create, compare, and refine.</p>
        </div>
        <span className="neuro-local-label">Creative workspace</span>
      </div>
      <div className={styles.composer}>
        <PromptInput
          value={prompt}
          onChange={setPrompt}
          brand={brand}
          onBrandChange={setBrand}
          kind={kind}
          onKindChange={setKind}
          aspect={aspect}
          onAspectChange={setAspect}
          files={files}
          onFilesChange={setFiles}
          busy={busy}
          unsupported={unsupported}
          onSubmit={send}
        />
      </div>
      {kind === "video" && <label className="ev-select">Video length
        <select aria-label="Video length" value={duration} disabled={busy} onChange={e => setDuration(Number(e.target.value))}>
          <option value={5}>5 seconds</option><option value={10}>10 seconds</option><option value={15}>15 seconds</option>
        </select>
      </label>}
      <p className="neuro-footnote">Describe your ad, add references if needed, then press Start creative loop. Your results and progress appear on the run page.</p>
      <details className={styles.details}>
        <summary>Run details</summary>
        <p className="neuro-footnote">
          {kind === "video"
            ? `${duration}-second video. Images, video, audio, and document references stay with the campaign.`
            : "Text-to-image. Later rounds create alternatives from evaluation evidence; they do not edit the previous image's pixels."}{" "}
          The run uses a maximum of 3 rounds and 10 candidates. Jobs wait when
          the notebook or required models are offline.
        </p>
      </details>
    </section>
  );
}
