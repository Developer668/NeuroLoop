"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  AudioLines,
  Check,
  ChevronDown,
  FileText,
  Film,
  ImageIcon,
  Mic,
  Plus,
  Square,
  X,
} from "lucide-react";
import LoadingState from "./loading-state";
import styles from "./prompt-input.module.css";

type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult:
    | ((event: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
};
type Props = {
  value: string;
  onChange: (value: string) => void;
  brand: string;
  onBrandChange: (value: string) => void;
  kind: "image" | "video";
  onKindChange: (value: "image" | "video") => void;
  aspect: string;
  onAspectChange: (value: string) => void;
  files: File[];
  onFilesChange: (files: File[]) => void;
  onSubmit: () => Promise<void>;
  busy: boolean;
  unsupported: boolean;
};

/** The supplied expanding prompt design, connected to NeuroLoop's creative API. */
export function PromptInput(props: Props) {
  const {
    value,
    onChange,
    brand,
    onBrandChange,
    kind,
    onKindChange,
    aspect,
    onAspectChange,
    files,
    onFilesChange,
    onSubmit,
    busy,
    unsupported,
  } = props;
  const [focused, setFocused] = useState(false),
    [menu, setMenu] = useState(false),
    [recording, setRecording] = useState(false),
    [voiceError, setVoiceError] = useState("");
  const [preview, setPreview] = useState<File | null>(null);
  const input = useRef<HTMLTextAreaElement>(null),
    upload = useRef<HTMLInputElement>(null),
    dialog = useRef<HTMLDialogElement>(null);
  const recognition = useRef<Recognition | null>(null),
    urls = useRef(new Map<File, string>()),
    sending = useRef(false);
  const [mediaUrls, setMediaUrls] = useState(new Map<File, string>());
  const expanded = true;
  useEffect(() => {
    const cache = urls.current;
    for (const [file, url] of cache)
      if (!files.includes(file)) {
        URL.revokeObjectURL(url);
        cache.delete(file);
      }
    for (const file of files)
      if (!cache.has(file)) cache.set(file, URL.createObjectURL(file));
    setMediaUrls(new Map(cache));
  }, [files]);
  useEffect(() => {
    const cache = urls.current;
    return () => {
      recognition.current?.stop();
      cache.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);
  useEffect(() => {
    if (input.current) {
      input.current.style.height = "auto";
      input.current.style.height = `${Math.min(180, Math.max(90, input.current.scrollHeight))}px`;
    }
  }, [value, expanded]);
  useEffect(() => {
    if (preview) dialog.current?.showModal();
    else dialog.current?.close();
  }, [preview]);
  const canSend =
    !busy &&
    !unsupported &&
    !recording &&
    value.trim().length >= 3 &&
    !!brand.trim();
  async function send() {
    if (!canSend || sending.current) return;
    sending.current = true;
    try {
      await onSubmit();
    } finally {
      sending.current = false;
    }
  }
  function startVoice() {
    const browser = window as typeof window & {
      SpeechRecognition?: new () => Recognition;
      webkitSpeechRecognition?: new () => Recognition;
    };
    const API = browser.SpeechRecognition ?? browser.webkitSpeechRecognition;
    if (!API) {
      setVoiceError(
        "Voice dictation is unavailable in this browser. Type your prompt or attach an audio file.",
      );
      setFocused(true);
      return;
    }
    setVoiceError("");
    setFocused(true);
    const session = new API();
    recognition.current = session;
    session.continuous = true;
    session.interimResults = true;
    session.lang = navigator.language;
    const prefix = value.trim();
    session.onresult = (event) =>
      onChange(
        [
          prefix,
          Array.from(event.results)
            .map((result) => result[0].transcript)
            .join(" "),
        ]
          .filter(Boolean)
          .join(" ")
          .slice(0, 12000),
      );
    session.onend = () => {
      setRecording(false);
      recognition.current = null;
    };
    session.onerror = (event) => {
      setVoiceError(
        `Dictation stopped (${event.error}). You can still type or attach audio.`,
      );
      setRecording(false);
    };
    try {
      session.start();
      setRecording(true);
    } catch {
      setVoiceError(
        "Could not start dictation. Check your microphone permissions.",
      );
      setRecording(false);
    }
  }
  return (
    <div
      className={`${styles.wrap} ${expanded ? styles.expanded : ""}`}
      onFocus={() => setFocused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setFocused(false);
          setMenu(false);
        }
      }}
    >
      <input
        ref={upload}
        type="file"
        multiple
        hidden
        aria-label="Composer references"
        disabled={busy}
        onChange={(event) => {
          const next = Array.from(event.target.files ?? []);
          onFilesChange([...files, ...next]);
          event.target.value = "";
          setFocused(true);
        }}
      />
      {files.length > 0 && (
        <div className={styles.tray} aria-label="Attached references">
          {files.map((file, index) => (
            <div className={styles.thumb} key={`${file.name}-${index}`}>
              <button
                type="button"
                className={styles.preview}
                aria-label={`Preview ${file.name}`}
                title={file.name}
                onClick={() => setPreview(file)}
              >
                {file.type.startsWith("image/") && mediaUrls.get(file) ? (
                  <img src={mediaUrls.get(file)} alt={file.name} />
                ) : file.type.startsWith("video/") ? (
                  <Film size={21} />
                ) : file.type.startsWith("audio/") ? (
                  <AudioLines size={21} />
                ) : (
                  <FileText size={21} />
                )}
              </button>
              <button
                className={styles.remove}
                type="button"
                disabled={busy}
                aria-label={`Remove ${file.name}`}
                onClick={() =>
                  onFilesChange(files.filter((_, i) => i !== index))
                }
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
        aria-busy={busy}
      >
        <div className={styles.card}>
          {!expanded ? (
            <button
              type="button"
              className={styles.open}
              onClick={() => {
                setFocused(true);
                requestAnimationFrame(() => input.current?.focus());
              }}
            >
              What would you like to create?
            </button>
          ) : (
            <textarea
              ref={input}
              className={styles.input}
              aria-label="Creative direction"
              placeholder="Describe the scene, product, dialogue, sound, and what you want to improve…"
              value={value}
              maxLength={12000}
              minLength={3}
              required
              disabled={busy || recording}
              onChange={(event) => onChange(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  void send();
                }
                if (event.key === "Escape") {
                  setMenu(false);
                  input.current?.blur();
                }
              }}
            />
          )}
          {expanded && (
            <div className={styles.toolbar}>
              <div className={styles.model}>
                <button
                  className={styles.tool}
                  type="button"
                  disabled={busy}
                  aria-label="Generation model"
                  aria-haspopup="menu"
                  aria-expanded={menu}
                  onClick={() => setMenu(!menu)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setMenu(false);
                  }}
                >
                  {kind === "video" ? (
                    <Film size={15} />
                  ) : (
                    <ImageIcon size={15} />
                  )}{" "}
                  {kind === "video" ? "MiniMax H3" : "Ideogram 4"}
                  <ChevronDown size={12} />
                </button>
                {menu && (
                  <div
                    className={styles.menu}
                    role="menu"
                    aria-label="Generation models"
                  >
                    {(["video", "image"] as const).map((model) => (
                      <button
                        key={model}
                        type="button"
                        role="menuitemradio"
                        aria-checked={kind === model}
                        onClick={() => {
                          onKindChange(model);
                          setMenu(false);
                          input.current?.focus();
                        }}
                      >
                        {model === "video" ? (
                          <Film size={17} />
                        ) : (
                          <ImageIcon size={17} />
                        )}
                        <span>
                          {model === "video" ? "MiniMax H3" : "Ideogram 4"}
                          <small>
                            {model === "video"
                              ? "Video · FP8 · 15 seconds"
                              : "Image · FP8 · Text to image"}
                          </small>
                        </span>
                        {kind === model && <Check size={14} />}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <select
                className={styles.ratio}
                aria-label="Composer aspect ratio"
                value={aspect}
                disabled={busy}
                onChange={(event) => onAspectChange(event.target.value)}
              >
                {["16:9", "9:16", "1:1", "4:5"].map((ratio) => (
                  <option key={ratio}>{ratio}</option>
                ))}
              </select>
              <span className={styles.spacer} />
              <button
                className={`${styles.tool} ${styles.attach}`}
                type="button"
                aria-label="Add references"
                title="Add images, video, audio, or documents"
                disabled={busy}
                onClick={() => upload.current?.click()}
              >
                <Plus size={18} /><span>Add media</span>
              </button>
              {!!value && !recording && (
                <button
                  className={styles.tool}
                  type="button"
                  aria-label="Dictate prompt"
                  disabled={busy}
                  onClick={startVoice}
                >
                  <Mic size={16} />
                </button>
              )}
              {value && !recording ? (
                <button
                  className={styles.send}
                  type="submit"
                  disabled={!canSend}
                  aria-label="Start creative loop"
                >
                  <ArrowUp size={18} />
                </button>
              ) : (
                <button
                  className={styles.send}
                  type="button"
                  disabled={busy}
                  aria-label={recording ? "Stop dictation" : "Dictate prompt"}
                  onClick={() =>
                    recording ? recognition.current?.stop() : startVoice()
                  }
                >
                  {recording ? <Square size={13} /> : <Mic size={16} />}
                </button>
              )}
            </div>
          )}
          {!expanded && (
            <button
              type="button"
              className={`${styles.send} ${styles.collapsedMic}`}
              aria-label="Dictate prompt"
              onClick={startVoice}
            >
              <Mic size={16} />
            </button>
          )}
        </div>
        {expanded && (
          <>
            <div className={styles.settings}>
              <label>
                Project{" "}
                <input
                  aria-label="Brand or project"
                  placeholder="Brand or project name"
                  value={brand}
                  maxLength={120}
                  required
                  disabled={busy}
                  onChange={(event) => onBrandChange(event.target.value)}
                />
              </label>
              <span>FP8</span>
            </div>
            <div className={styles.meta}>
              <span>Images, video, audio & documents</span>
              <span>{value.length.toLocaleString()} / 12,000</span>
            </div>
          </>
        )}
      </form>
      {recording && <LoadingState label="Listening" variant="Dots" />}
      {busy && (
        <LoadingState label="Preparing your creative loop" variant="Drive" />
      )}
      {unsupported && (
        <p role="alert" className={styles.error}>
          Ideogram accepts text only. Remove media references or choose MiniMax
          H3.
        </p>
      )}
      {voiceError && (
        <p role="alert" className={styles.error}>
          {voiceError}
        </p>
      )}
      <dialog
        ref={dialog}
        className={styles.dialog}
        aria-label="Reference preview"
        onClose={() => setPreview(null)}
        onClick={(event) => {
          if (event.target === event.currentTarget) setPreview(null);
        }}
      >
        {preview && (
          <>
            <header>
              <strong>{preview.name}</strong>
              <button
                type="button"
                aria-label="Close preview"
                onClick={() => setPreview(null)}
              >
                <X size={20} />
              </button>
            </header>
            {preview.type.startsWith("image/") ? (
              <img src={mediaUrls.get(preview)} alt={preview.name} />
            ) : preview.type.startsWith("video/") ? (
              <video src={mediaUrls.get(preview)} controls />
            ) : preview.type.startsWith("audio/") ? (
              <audio src={mediaUrls.get(preview)} controls />
            ) : (
              <p>
                <FileText size={28} /> {(preview.size / 1024).toFixed(1)} KB ·{" "}
                <a href={mediaUrls.get(preview)} download={preview.name}>
                  Download reference
                </a>
              </p>
            )}
          </>
        )}
      </dialog>
    </div>
  );
}
