"use client";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowUp, ArrowUpRight, Paperclip, Plug, X, Loader2 } from "lucide-react";
import { NeuroMark } from "./Neuro";
import styles from "./LoopComposer.module.css";

export type ComposeRequest = {
  prompt: string;
  brand: string;
  kind: "image" | "video";
  aspect: string;
  files: File[];
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
    [files, setFiles] = useState<File[]>([]);
  const unsupported =
    kind === "image" &&
    files.some((f) => /^(image|video|audio)\//.test(f.type));
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!busy && !unsupported && prompt.trim() && brand.trim()) await submit({ prompt, brand, kind, aspect, files });
  }
  return (
    <section className={`neuro-page ${styles.page}`} aria-labelledby="neuro-title">
      <div className="neuro-page-top">
        <span><NeuroMark size={23} /> NEURO AI</span>
        <Link href="/workspace?view=settings"><Plug size={15} /> Connections <ArrowUpRight size={14} /></Link>
      </div>
      <div className="neuro-command-intro">
        <NeuroMark size={64} />
        <div>
          <h2 id="neuro-title">Neuro AI</h2>
          <p>Bring your ideas and references. Create, compare, and refine.</p>
        </div>
        <span className="neuro-local-label">Creative workspace</span>
      </div>
      <form className={`neuro-composer ${styles.composer}`} onSubmit={send} aria-busy={busy}>
        <label className="sr-only" htmlFor="neuro-creative-direction">Creative direction</label>
          <textarea
            id="neuro-creative-direction"
            aria-label="Creative direction"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            minLength={3}
            maxLength={12000}
            required
            rows={4}
            placeholder="Describe the scene, product, dialogue, sound, and what you want to improve…"
          />
        <fieldset className={styles.settings} disabled={busy}>
          <legend className="sr-only">Creative settings</legend>
          <label>
            Brand or project
            <input
              aria-label="Brand or project"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              maxLength={120}
              required
              placeholder="Brand or project name"
            />
          </label>
          <label>
            Generate with
            <select
              aria-label="Generation model"
              value={kind}
              onChange={(e) => setKind(e.target.value as "video" | "image")}
            >
              <option value="video">MiniMax H3 · FP8 video</option>
              <option value="image">Ideogram 4 · FP8 image</option>
            </select>
          </label>
          <label>
            Aspect ratio
            <select
              aria-label="Composer aspect ratio"
              value={aspect}
              onChange={(e) => setAspect(e.target.value)}
            >
              {["16:9", "9:16", "1:1", "4:5"].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        </fieldset>
        <div className={`nl-reference-chips ${styles.references}`} aria-label="Attached references">
          {files.map((file, index) => (
            <span key={`${file.name}-${index}`}>
              {file.name}
              <button
                type="button"
                aria-label={`Remove ${file.name}`}
                disabled={busy}
                onClick={() =>
                  setFiles((old) => old.filter((_, i) => i !== index))
                }
              >
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
        <div className={`neuro-compose-tools ${styles.tools}`}>
          <label className={`neuro-command-toggle nl-attach ${styles.attach}`}>
            <Paperclip size={16} /> Add references
            <input
              aria-label="Composer references"
              type="file"
              multiple
              disabled={busy}
              onChange={(e) => {
                const additions = Array.from(e.target.files || []);
                setFiles((old) => [...old, ...additions]);
                e.target.value = "";
              }}
            />
          </label>
          <span className="neuro-draft-state">{prompt.length ? `${prompt.length.toLocaleString()} / 12,000` : ""}</span>
          <button
            className={`neuro-send ${styles.send}`}
            disabled={busy || unsupported || !prompt.trim() || !brand.trim()}
            type="submit"
            aria-label="Start creative loop"
            title="Start creative loop"
          >
            {busy ? <Loader2 size={18} className={styles.spinner} /> : <ArrowUp size={18} />}
          </button>
        </div>
        {unsupported && (
          <p role="alert" className="nl-error">
            Ideogram accepts text only. Remove media references or choose
            MiniMax H3.
          </p>
        )}
      </form>
      <details className={styles.details}>
        <summary>Run details</summary>
        <p className="neuro-footnote">
          {kind === "video"
            ? "15-second video. Images, video, audio, and document references stay with the campaign."
            : "Text-to-image. Later rounds create alternatives from evaluation evidence; they do not edit the previous image's pixels."}{" "}
          The run uses a maximum of 3 rounds and 10 candidates. Jobs wait when
          the notebook or required models are offline.
        </p>
      </details>
    </section>
  );
}
