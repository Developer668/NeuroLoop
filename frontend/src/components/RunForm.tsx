"use client";
import { useState, type FormEvent } from "react";
import { ArrowRight, AlertCircle } from "lucide-react";
import { api, Asset, Project, Run, Capability } from "@/lib/types";
import { Modal, errorText } from "./UI";

const OPERATORS = [
  ["contrast_up", "Contrast +8%"],
  ["contrast_down", "Contrast −8%"],
  ["brightness_up", "Luminance +0.035"],
  ["brightness_down", "Luminance −0.035"],
  ["saturation_up", "Saturation +12%"],
  ["saturation_down", "Saturation −12%"],
  ["headline_early", "Headline 0.75s earlier"],
  ["headline_late", "Headline 0.75s later"],
];
export default function RunForm({
  project,
  assets,
  capabilities,
  onClose,
  onCreated,
}: {
  project: Project;
  assets: Asset[];
  capabilities: Capability;
  onClose: () => void;
  onCreated: (r: Run) => void;
}) {
  const original = assets.find((a) => a.id === project.asset_id);
  const [mode, setMode] = useState("analyze"),
    [budget, setBudget] = useState(
      Math.max(4, project.reference_ids.length + 2),
    ),
    [maxSeconds, setMaxSeconds] = useState(900),
    [gain, setGain] = useState(0.005),
    [target, setTarget] = useState(0.98),
    [noSpeech, setNoSpeech] = useState(false),
    [staticMode, setStaticMode] = useState(false),
    [presentation, setPresentation] = useState(8),
    [operators, setOperators] = useState([
      "contrast_up",
      "contrast_down",
      "brightness_up",
      "brightness_down",
    ]),
    [words, setWords] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [tsam, setTsam] = useState(false);
  const includesAudio = assets.some(
    (a) =>
      (a.id === project.asset_id || project.reference_ids.includes(a.id)) &&
      a.details.has_audio,
  );
  const speechMissing = capabilities.asr.status !== "available";
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (capabilities.execution?.paused) {
      setError(
        "Model execution is paused after a graphics crash. Saved results remain available.",
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      let transcript = [];
      if (words.trim()) {
        try {
          transcript = JSON.parse(words);
          if (!Array.isArray(transcript)) throw new Error();
        } catch {
          throw new Error(
            "Timed words must be a JSON array of {text, start, end} records.",
          );
        }
      }
      const body = {
        project_id: project.id,
        mode,
        max_evaluations: budget,
        max_seconds: maxSeconds,
        min_gain: gain,
        target_score: target,
        no_speech: noSpeech,
        transcript,
        allow_static_presentation: staticMode,
        presentation_seconds: presentation,
        operators,
        include_tsam: tsam,
        tsam_research_acknowledged: tsam,
      };
      const run = await api<Run>("runs", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      onCreated(run);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Set the experiment boundary" onClose={onClose}>
      <form onSubmit={submit}>
        <p className="modal-subtitle">
          {project.name} · {original?.name || "No original selected"}
        </p>
        {error && (
          <div className="notice error" role="alert">
            <AlertCircle size={16} />
            {error}
          </div>
        )}
        <label className="field">
          <span>Run mode</span>
          <select
            aria-label="Run mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="analyze">
              Analyze — record cortical predictions
            </option>
            <option value="compare" disabled={!project.reference_ids.length}>
              Compare — measure against references
            </option>
            <option
              value="optimize"
              disabled={
                !project.reference_ids.length ||
                !["image", "video"].includes(original?.kind || "")
              }
            >
              Optimize — test bounded edits
            </option>
          </select>
          <small>
            {project.reference_ids.length} reference
            {project.reference_ids.length === 1 ? "" : "s"} selected.
            Comparisons use a fixed numerical objective, not an estimate of
            liking.
          </small>
        </label>
        <div className="field-row">
          <label className="field">
            <span>Maximum neural evaluations</span>
            <input
              type="number"
              min={project.reference_ids.length + 1}
              max={12}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
            <small>
              Includes original and references; cache hits do not use a new
              evaluation.
            </small>
          </label>
          <label className="field">
            <span>Wall-clock budget (seconds)</span>
            <input
              type="number"
              min={30}
              max={7200}
              step={30}
              value={maxSeconds}
              onChange={(e) => setMaxSeconds(Number(e.target.value))}
            />
            <small>
              No new stage starts after the budget. An in-flight inference ends
              safely.
            </small>
          </label>
        </div>
        {mode === "optimize" && (
          <>
            <div className="field-row">
              <label className="field">
                <span>Minimum retained gain</span>
                <input
                  type="number"
                  min={0.0001}
                  max={0.25}
                  step={0.001}
                  value={gain}
                  onChange={(e) => setGain(Number(e.target.value))}
                />
              </label>
              <label className="field">
                <span>Stop at reference score</span>
                <input
                  type="number"
                  min={-1}
                  max={1}
                  step={0.01}
                  value={target}
                  onChange={(e) => setTarget(Number(e.target.value))}
                />
              </label>
            </div>
            <div className="field">
              <span>Permitted experiments</span>
              <div className="operator-grid">
                {OPERATORS.filter(
                  ([id]) =>
                    !id.startsWith("headline_") ||
                    original?.details.composition,
                ).map(([id, label]) => (
                  <label className="check-card" key={id}>
                    <input
                      type="checkbox"
                      checked={operators.includes(id)}
                      onChange={(e) =>
                        setOperators((old) =>
                          e.target.checked
                            ? [...old, id]
                            : old.filter((v) => v !== id),
                        )
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
              <small>
                Duration and source assets stay fixed. Two consecutive
                non-improving edits stop the search. No paid generation calls
                are made.
              </small>
            </div>
          </>
        )}
        {original?.kind === "image" && (
          <div className="field">
            <label className="check">
              <input
                type="checkbox"
                checked={staticMode}
                onChange={(e) => setStaticMode(e.target.checked)}
                required
              />
              <span>
                Allow an experimental repeated-frame presentation.
                <small>
                  This is not validated thumbnail preference or click
                  prediction.
                </small>
              </span>
            </label>
            <label className="field section-space">
              <span>Presentation duration</span>
              <input
                type="number"
                min={5}
                max={30}
                value={presentation}
                onChange={(e) => setPresentation(Number(e.target.value))}
              />
            </label>
          </div>
        )}
        {includesAudio && (
          <div className="field">
            <label className="check">
              <input
                type="checkbox"
                checked={noSpeech}
                onChange={(e) => setNoSpeech(e.target.checked)}
              />
              <span>
                I confirm the original and references contain no spoken words.
                <small>
                  Only select this for genuinely speech-free media. It is not a
                  bypass for unavailable transcription.
                </small>
              </span>
            </label>
            {speechMissing && !noSpeech && (
              <small className="system-block">
                Automatic local speech transcription is not installed. Supply
                timed words for spoken assets before starting; the server will
                refuse to silently omit language.
              </small>
            )}
          </div>
        )}
        {(original?.kind === "text" || (includesAudio && !noSpeech)) && (
          <details
            open={original?.kind === "text"}
            className="transcript-options"
          >
            <summary>
              {original?.kind === "text"
                ? "Set the text presentation timings"
                : "Advanced: provide your own timed transcript"}
            </summary>
            <label className="field">
              <span>Original timed words (JSON)</span>
              <textarea
                className="mono"
                value={words}
                onChange={(e) => setWords(e.target.value)}
                placeholder={'[{"text":"Introducing","start":0.2,"end":0.8}]'}
                required={original?.kind === "text"}
                rows={3}
              />
              <small>
                Seconds refer to the actual stimulus. References use the timed
                transcripts saved in the asset library.
              </small>
            </label>
          </details>
        )}
        {original?.kind === "video" &&
          original.details.has_audio &&
          capabilities.tsam.status === "experimental_weights_present" && (
            <label className="check section-space">
              <input
                type="checkbox"
                checked={tsam}
                onChange={(e) => setTsam(e.target.checked)}
              />
              <span>
                Include TSAM viewer-emotion research readout
                <small>
                  I acknowledge the upstream research-use restrictions.
                  Eight-class logits are experimental, uncalibrated, and do not
                  affect keep/revert decisions.{" "}
                  <a
                    href="https://huggingface.co/dnamodel/tsam-viewer-emotions"
                    target="_blank"
                    rel="noreferrer"
                  >
                    Review model terms ↗
                  </a>
                </small>
              </span>
            </label>
          )}
        <div className="notice info">
          The objective and model profile stay fixed. No purchases, thoughts, or
          calibrated human feelings are inferred from these scores.
        </div>
        <div className="dialog-footer">
          <button type="button" className="button" onClick={onClose}>
            Cancel
          </button>
          <button
            className="button primary"
            disabled={
              busy ||
              capabilities.execution?.paused ||
              !original ||
              (mode === "optimize" && !operators.length)
            }
          >
            {capabilities.execution?.paused
              ? "Execution paused"
              : busy
                ? "Queuing…"
                : "Start run"}
            <ArrowRight size={14} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
