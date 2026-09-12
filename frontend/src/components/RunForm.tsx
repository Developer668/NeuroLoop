"use client";
import { useMemo, useState, type FormEvent } from "react";
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
] as const;

const EMOTIONS = [
  ["happiness", "Happiness"],
  ["surprise", "Surprise"],
  ["fear", "Fear"],
  ["sadness", "Sadness"],
  ["anger", "Anger"],
  ["neutral", "Neutral"],
  ["contempt", "Contempt"],
  ["disgust", "Disgust"],
] as const;

type EmotionName = (typeof EMOTIONS)[number][0];
type TargetState = Record<EmotionName, { enabled: boolean; desired: number }>;
const DEFAULT_TARGETS: TargetState = {
  happiness: { enabled: true, desired: 0.8 },
  surprise: { enabled: true, desired: 0.6 },
  fear: { enabled: true, desired: 0.1 },
  sadness: { enabled: false, desired: 0.1 },
  anger: { enabled: false, desired: 0.1 },
  neutral: { enabled: false, desired: 0.3 },
  contempt: { enabled: false, desired: 0.1 },
  disgust: { enabled: false, desired: 0.1 },
};

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
  const [mode, setMode] = useState("analyze");
  const [objective, setObjective] = useState<"response_target" | "reference_similarity">("response_target");
  const [budget, setBudget] = useState(6);
  const [maxSeconds, setMaxSeconds] = useState(1800);
  const [gain, setGain] = useState(0.005);
  const [stopScore, setStopScore] = useState(0.9);
  const [noSpeech, setNoSpeech] = useState(false);
  const [staticMode, setStaticMode] = useState(false);
  const [presentation, setPresentation] = useState(8);
  const [operators, setOperators] = useState<string[]>([
    "contrast_up",
    "contrast_down",
    "brightness_up",
    "brightness_down",
    "saturation_up",
    "saturation_down",
  ]);
  const [words, setWords] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tsam, setTsam] = useState(false);
  const [kragel, setKragel] = useState(capabilities.kragel.status === "experimental_ready");
  const [goal, setGoal] = useState("Make the creative feel more positive and engaging without increasing fear.");
  const [targets, setTargets] = useState<TargetState>(DEFAULT_TARGETS);

  const usingReferences = mode === "compare" || (mode === "optimize" && objective === "reference_similarity");
  const selectedAssets = useMemo(
    () => [original, ...(usingReferences ? project.reference_ids.map((id) => assets.find((a) => a.id === id)) : [])].filter(Boolean) as Asset[],
    [assets, original, project.reference_ids, usingReferences],
  );
  const includesAudio = selectedAssets.some((a) => a.details.has_audio);
  const speechMissing = capabilities.asr.status !== "available";
  const targetEntries = EMOTIONS.filter(([name]) => targets[name].enabled);
  const responseMode = mode === "optimize" && objective === "response_target";
  const minEvaluations = 1 + (usingReferences ? project.reference_ids.length : 0);
  const canUseTsam = original?.kind === "video" && !!original.details.has_audio && capabilities.tsam.status === "experimental_weights_present";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (capabilities.execution?.paused) {
      setError("Model execution is paused after a graphics crash. Saved results remain available.");
      return;
    }
    if (responseMode && !targetEntries.length) {
      setError("Choose at least one response target.");
      return;
    }
    if (responseMode && !tsam && !kragel) {
      setError("Response-target optimization needs TSAM, Kragel, or both.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let transcript: unknown[] = [];
      if (words.trim()) {
        try {
          transcript = JSON.parse(words);
          if (!Array.isArray(transcript)) throw new Error();
        } catch {
          throw new Error("Timed words must be a JSON array of {text, start, end} records.");
        }
      }
      const responseTarget = responseMode
        ? {
            goal,
            emotions: Object.fromEntries(
              targetEntries.map(([name]) => [name, { desired: targets[name].desired, weight: 1 }]),
            ),
          }
        : undefined;
      const body = {
        project_id: project.id,
        mode,
        objective: responseMode ? "response_target" : "reference_similarity",
        target: responseTarget,
        max_evaluations: Math.max(budget, minEvaluations),
        max_seconds: maxSeconds,
        min_gain: gain,
        target_score: stopScore,
        no_speech: noSpeech,
        transcript,
        allow_static_presentation: staticMode,
        presentation_seconds: presentation,
        operators,
        include_tsam: tsam,
        tsam_research_acknowledged: tsam,
        include_kragel: kragel,
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
        {error && <div className="notice error" role="alert"><AlertCircle size={16} />{error}</div>}

        <label className="field">
          <span>Run mode</span>
          <select aria-label="Run mode" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="analyze">Analyze · TRIBE and selected response readouts</option>
            <option value="compare" disabled={!project.reference_ids.length}>Compare · cortical reference similarity</option>
            <option value="optimize" disabled={!(["image", "video"].includes(original?.kind || ""))}>Optimize · run the closed loop</option>
          </select>
        </label>

        {mode === "optimize" && (
          <label className="field">
            <span>Optimization objective</span>
            <select value={objective} onChange={(e) => setObjective(e.target.value as typeof objective)}>
              <option value="response_target">Response target · TSAM + Kragel ensemble</option>
              <option value="reference_similarity" disabled={!project.reference_ids.length}>Reference similarity · research objective</option>
            </select>
            <small>
              Response-target mode does not need a reference creative. It keeps TSAM and Kragel separate, then combines their relative evidence through a versioned ensemble.
            </small>
          </label>
        )}

        {responseMode && (
          <div className="field">
            <span>Desired response</span>
            <textarea value={goal} onChange={(e) => setGoal(e.target.value)} maxLength={1000} rows={2} />
            <div className="response-target-grid">
              {EMOTIONS.map(([name, label]) => (
                <div className="response-target" key={name}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={targets[name].enabled}
                      onChange={(e) => setTargets((old) => ({ ...old, [name]: { ...old[name], enabled: e.target.checked } }))}
                    />
                    <span>{label}</span>
                  </label>
                  <input
                    aria-label={`${label} target`}
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    disabled={!targets[name].enabled}
                    value={targets[name].desired}
                    onChange={(e) => setTargets((old) => ({ ...old, [name]: { ...old[name], desired: Number(e.target.value) } }))}
                  />
                  <strong>{targets[name].desired.toFixed(2)}</strong>
                </div>
              ))}
            </div>
            <small>These are targets for relative model evidence, not claims that a percentage of viewers will feel an emotion.</small>
          </div>
        )}

        <div className="field-row">
          <label className="field">
            <span>Maximum neural evaluations</span>
            <input type="number" min={minEvaluations} max={12} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
            <small>Original{usingReferences ? " and references" : ""} count toward the budget. Cache hits do not.</small>
          </label>
          <label className="field">
            <span>Wall-clock budget (seconds)</span>
            <input type="number" min={30} max={7200} step={30} value={maxSeconds} onChange={(e) => setMaxSeconds(Number(e.target.value))} />
          </label>
        </div>

        {mode === "optimize" && (
          <>
            <div className="field-row">
              <label className="field">
                <span>Minimum retained gain</span>
                <input type="number" min={0.0001} max={0.25} step={0.001} value={gain} onChange={(e) => setGain(Number(e.target.value))} />
              </label>
              <label className="field">
                <span>Stop at target match</span>
                <input type="number" min={responseMode ? 0 : -1} max={1} step={0.01} value={stopScore} onChange={(e) => setStopScore(Number(e.target.value))} />
              </label>
            </div>
            <div className="field">
              <span>Permitted local interventions</span>
              <div className="operator-grid">
                {OPERATORS.filter(([id]) => !id.startsWith("headline_") || original?.details.composition).map(([id, label]) => (
                  <label className="check-card" key={id}>
                    <input type="checkbox" checked={operators.includes(id)} onChange={(e) => setOperators((old) => e.target.checked ? [...old, id] : old.filter((v) => v !== id))} />
                    {label}
                  </label>
                ))}
              </div>
              <small>These controlled edits run now. Ideogram 4 and MiniMax H3 generation remain intentionally disabled until sponsor credits/access are available.</small>
            </div>
          </>
        )}

        <div className="field">
          <span>Response readouts</span>
          <label className="check">
            <input type="checkbox" checked={kragel} disabled={capabilities.kragel.status !== "experimental_ready"} onChange={(e) => setKragel(e.target.checked)} />
            <span>
              Kragel 2015 emotion-pattern expression
              <small>{capabilities.kragel.status === "experimental_ready" ? "Experimental TRIBE-derived readout using published MNI emotion signatures projected onto fsaverage5." : `Unavailable: ${capabilities.kragel.status}`}</small>
            </span>
          </label>
          {canUseTsam && (
            <label className="check section-space">
              <input type="checkbox" checked={tsam} onChange={(e) => setTsam(e.target.checked)} />
              <span>
                TSAM direct audiovisual emotion readout
                <small>Independent of TRIBE. Enabling this acknowledges the included upstream research-use terms. Outputs are uncalibrated model evidence.</small>
              </span>
            </label>
          )}
        </div>

        {original?.kind === "image" && (
          <div className="field">
            <label className="check">
              <input type="checkbox" checked={staticMode} onChange={(e) => setStaticMode(e.target.checked)} required />
              <span>Allow experimental repeated-frame TRIBE presentation.<small>This is a presentation adaptation, not thumbnail preference measurement.</small></span>
            </label>
            <label className="field section-space"><span>Presentation duration</span><input type="number" min={5} max={30} value={presentation} onChange={(e) => setPresentation(Number(e.target.value))} /></label>
          </div>
        )}

        {includesAudio && (
          <div className="field">
            <label className="check">
              <input type="checkbox" checked={noSpeech} onChange={(e) => setNoSpeech(e.target.checked)} />
              <span>I confirm the evaluated media contains no spoken words.<small>Only select this for genuinely speech-free media.</small></span>
            </label>
            {speechMissing && !noSpeech && <small className="system-block">Automatic local speech transcription is not installed. Supply timed words for spoken media.</small>}
          </div>
        )}

        {(original?.kind === "text" || (includesAudio && !noSpeech)) && (
          <details open={original?.kind === "text"} className="transcript-options">
            <summary>{original?.kind === "text" ? "Set text presentation timings" : "Advanced: provide timed transcript"}</summary>
            <label className="field">
              <span>Original timed words (JSON)</span>
              <textarea className="mono" value={words} onChange={(e) => setWords(e.target.value)} placeholder={'[{"text":"Introducing","start":0.2,"end":0.8}]'} required={original?.kind === "text"} rows={3} />
            </label>
          </details>
        )}

        <div className="notice info">
          TRIBE, response readouts, target, and scoring profile stay fixed for the run. The policy learns only which permitted creative interventions improve the declared model-evidence target.
        </div>
        {capabilities.generation_providers?.length ? (
          <div className="notice info">
            Sponsor generation: {capabilities.generation_providers.map((p) => `${p.name}: ${p.status.replaceAll("_", " ")}`).join(" · ")}
          </div>
        ) : null}
        <div className="dialog-footer">
          <button type="button" className="button" onClick={onClose}>Cancel</button>
          <button className="button primary" disabled={busy || capabilities.execution?.paused || !original || (mode === "optimize" && !operators.length)}>
            {capabilities.execution?.paused ? "Execution paused" : busy ? "Queuing…" : "Start run"}<ArrowRight size={14} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
