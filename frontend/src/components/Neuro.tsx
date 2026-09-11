"use client";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  ArrowUp,
  ArrowUpRight,
  Command,
  Database,
  Plug,
  Plus,
  X,
} from "lucide-react";
import { api } from "@/lib/types";
import { PixelLoading } from "./ReleaseMotion";

export function NeuroMark({ size = 20 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M5 25V13C5 5 12 4 17 11L21 17C26 24 29 20 27 12C25 4 16 8 15 17C14 27 8 28 5 25Z"
        stroke="currentColor"
        strokeWidth="3.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 11C12 13 12 25 20 25C26 25 28 20 27 15"
        stroke="currentColor"
        strokeWidth="3.3"
        strokeLinecap="round"
      />
    </svg>
  );
}
type Reply = {
  command: string;
  message: string;
  links: { label: string; href: string }[];
  checked_at: string;
};
const commands = [
  {
    value: "/latest",
    title: "Pick up where you left off",
    detail: "Open your latest saved evaluation.",
    icon: Database,
  },
  {
    value: "/status",
    title: "Check the workspace",
    detail: "Read current execution and model status.",
    icon: Command,
  },
  {
    value: "/experiments",
    title: "Review your experiments",
    detail: "Find recorded runs and their outcomes.",
    icon: ArrowUpRight,
  },
];

export default function Neuro() {
  const [draft, setDraft] = useState(""),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [history, setHistory] = useState<Reply[]>([]),
    [menu, setMenu] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null),
    pending = useRef(false),
    end = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  useEffect(() => {
    try {
      setDraft(sessionStorage.getItem("neuroloop-neuro-draft") || "");
    } catch {}
    setReady(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    try {
      sessionStorage.setItem("neuroloop-neuro-draft", draft);
    } catch {}
    if (textarea.current) {
      textarea.current.style.height = "auto";
      textarea.current.style.height =
        Math.min(180, textarea.current.scrollHeight) + "px";
    }
  }, [draft, ready]);
  useEffect(() => {
    if (history.length)
      end.current?.scrollIntoView({
        behavior: reduce ? "instant" : "smooth",
        block: "nearest",
      });
  }, [history, reduce]);
  async function submit(value = draft) {
    if (!value.trim() || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    setMenu(false);
    try {
      const reply = await api<Reply>("neuro/command", {
        method: "POST",
        body: JSON.stringify({ command: value }),
      });
      setHistory((previous) => [...previous, reply].slice(-20));
      if (
        [
          "/status",
          "/latest",
          "/experiments",
          "/connections",
          "/help",
        ].includes(value.trim().toLowerCase())
      )
        setDraft((current) => (current === value ? "" : current));
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to read local evidence. Your draft is preserved.",
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="neuro-page" aria-labelledby="neuro-title">
      <div className="neuro-page-top">
        <span>
          <NeuroMark size={23} /> NEURO
        </span>
        <Link href="/workspace?view=connections">
          <Plug size={15} /> Connect an agent <ArrowUpRight size={14} />
        </Link>
      </div>
      <div className="neuro-intro">
        <Image
          className="neuro-artwork"
          src="/brand/neuro-assistant-v1.png"
          alt="Neuro's interlocking navy and teal ribbon"
          width={230}
          height={230}
          priority
        />
        <div>
          <span className="eyebrow">A LITTLE CLARITY GOES A LONG WAY.</span>
          <h1 id="neuro-title">
            Make sense of
            <br />
            <em>what you found.</em>
          </h1>
          <p>
            Your experiments, results, and next questions.
            <br />
            One place to find your footing.
          </p>
        </div>
      </div>
      <div className="neuro-mode">
        <span className="neuro-mode-dot" /> Evidence commands are available{" "}
        <span>·</span> AI conversation is coming later
      </div>
      <div className="neuro-command-cards">
        {commands.map(({ value, title, detail, icon: Icon }) => (
          <button
            key={value}
            disabled={busy}
            onClick={() => void submit(value)}
          >
            <Icon size={19} />
            <strong>{title}</strong>
            <span>{detail}</span>
            <code>{value}</code>
          </button>
        ))}
      </div>
      <div
        className="neuro-thread"
        aria-label="Command history"
        aria-live="polite"
        aria-busy={busy}
      >
        {history.map((reply, index) => (
          <motion.article
            className="neuro-exchange"
            key={`${reply.checked_at}-${index}`}
            initial={{ opacity: 0, y: reduce ? 0 : 12 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="neuro-question">
              <Command size={14} />
              <span>{reply.command}</span>
            </div>
            <div className="neuro-answer">
              <NeuroMark size={25} />
              <div>
                <small>
                  LOCAL LEDGER{" "}
                  <time>{new Date(reply.checked_at).toLocaleTimeString()}</time>
                </small>
                <p>{reply.message}</p>
                <div className="neuro-result-links">
                  {reply.links.map((link) => (
                    <Link key={link.href} href={link.href}>
                      {link.label}
                      <ArrowUpRight size={14} />
                    </Link>
                  ))}
                </div>
              </div>
            </div>
          </motion.article>
        ))}
        <AnimatePresence>
          {busy && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <PixelLoading label="Reading your workspace" variant="orbit" />
            </motion.div>
          )}
        </AnimatePresence>
        <div ref={end} />
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <form
        className="neuro-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label className="sr-only" htmlFor="neuro-input">
          Local command or saved draft
        </label>
        <textarea
          id="neuro-input"
          ref={textarea}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          maxLength={2500}
          placeholder="Type a command, or save a thought for later…"
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <div className="neuro-compose-tools">
          <button
            type="button"
            className="neuro-command-toggle"
            aria-expanded={menu}
            aria-controls="neuro-command-menu"
            onClick={() => setMenu(!menu)}
          >
            {menu ? <X size={17} /> : <Plus size={17} />} Commands
          </button>
          <span className="neuro-draft-state">
            {draft.length
              ? `${draft.length.toLocaleString()} / 2,500 · Draft saved in this session`
              : "Local workspace"}
          </span>
          <button
            className="neuro-send"
            disabled={busy || !draft.trim()}
            aria-label="Run local command"
          >
            <ArrowUp size={20} />
          </button>
        </div>
        {menu && (
          <div className="neuro-command-menu" id="neuro-command-menu">
            {[
              "/status",
              "/latest",
              "/experiments",
              "/connections",
              "/help",
            ].map((command) => (
              <button
                key={command}
                type="button"
                onClick={() => {
                  setDraft(command);
                  setMenu(false);
                  textarea.current?.focus();
                }}
              >
                <Command size={13} />
                {command}
              </button>
            ))}
          </div>
        )}
      </form>
      <p className="neuro-footnote">
        Commands read saved evidence. Free-text drafts stay here until AI
        Inference is enabled. To work with an external AI,{" "}
        <Link href="/workspace?view=connections">connect through MCP</Link>.
      </p>
    </section>
  );
}
