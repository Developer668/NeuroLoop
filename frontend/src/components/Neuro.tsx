"use client";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  ArrowUp,
  ArrowUpRight,
  Command,
  Plug,
  Plus,
  X,
} from "lucide-react";
import { api } from "@/lib/types";
import LoadingState from "@/components/ui/loading-state";
import { PromptInput } from "@/components/ui/local-command-input";

export function NeuroMark({ size = 20 }: { size?: number }) {
  return (
    <Image
      src="/brand/neuro-ai.png"
      alt=""
      width={size}
      height={size}
      style={{ borderRadius: "22%", objectFit: "contain", flexShrink: 0 }}
      aria-hidden="true"
    />
  );
}
type Reply = {
  command: string;
  message: string;
  links: { label: string; href: string }[];
  checked_at: string;
};
export default function Neuro() {
  const [draft, setDraft] = useState(""),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [history, setHistory] = useState<Reply[]>([]);
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
          <NeuroMark size={23} /> NEURO AI
        </span>
        <Link href="/workspace?view=connections">
          <Plug size={15} /> Connect an agent <ArrowUpRight size={14} />
        </Link>
      </div>
      <div className="neuro-command-intro">
        <NeuroMark size={64} />
        <div>
          <h1 id="neuro-title">Neuro AI</h1>
          <p>Inspect your workspace and open the evidence behind a result.</p>
        </div>
        <span className="neuro-local-label">Local commands</span>
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
              <LoadingState label="Reading your workspace" variant="Orbit" />
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
      <PromptInput value={draft} onChange={setDraft} onSubmit={() => void submit()} busy={busy} />
      <p className="neuro-footnote">
        This page runs local evidence commands. For an AI-led experiment,{" "}
        <Link href="/workspace?view=connections">connect through MCP</Link>.
      </p>
    </section>
  );
}

