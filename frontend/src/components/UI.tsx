"use client";
import { useEffect, useRef, type ReactNode } from "react";
import Link from "next/link";
import {
  X,
  Image as ImageIcon,
  FileText,
  Volume2,
  Film,
  ArrowUpRight,
  UserRound,
} from "lucide-react";
import type { Asset } from "@/lib/types";

export function ProfileAvatar() {
  return <UserRound size={19} strokeWidth={1.5} aria-hidden="true" />;
}

/**
 * Eased count-up for dashboard metrics. The final value is rendered on the
 * server and on first paint, so hydration stays stable; the animation only
 * runs client-side and only when the visitor allows motion.
 */
export function AnimatedNumber({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const started = performance.now();
    const duration = 1200;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - started) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      node.textContent = Math.round(value * eased).toLocaleString("en-US");
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span ref={ref}>{value.toLocaleString("en-US")}</span>;
}

export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="NeuroLoop home">
      <span className="brand-symbol">
        <img src="/brand/neuroloop.png" alt="" width={72} height={72} />
      </span>
      <span>
        NeuroLoop<span className="brand-dot">.</span>
      </span>
    </Link>
  );
}
export function Badge({ value }: { value: string }) {
  return <span className={"badge " + value}>{value.replaceAll("_", " ")}</span>;
}
export function Panel({
  title,
  description,
  action,
  children,
  footer,
  className = "",
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <section className={"panel " + className}>
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
      {footer && <div className="panel-footer">{footer}</div>}
    </section>
  );
}
export function Empty({
  title,
  text,
  action,
  icon,
}: {
  title: string;
  text: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon || <ImageIcon size={23} />}</div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.showModal();
    const cancel = (event: Event) => {
      event.preventDefault();
      close.current();
    };
    el.addEventListener("cancel", cancel);
    return () => {
      el.removeEventListener("cancel", cancel);
      el.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-label={title}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          const r = e.currentTarget.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            onClose();
        }
      }}
    >
      <div className="dialog-head">
        <h2>{title}</h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close dialog"
        >
          <X size={18} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function AssetVisual({
  asset,
  play = false,
}: {
  asset?: Asset;
  play?: boolean;
}) {
  if (!asset)
    return (
      <div className="asset-image">
        <ImageIcon size={28} />
      </div>
    );
  if (play && asset.kind === "video")
    return (
      <div className="asset-image">
        <video
          src={`/api/assets/${asset.id}/content`}
          controls
          preload="metadata"
          aria-label={asset.name}
        />
      </div>
    );
  if (play && asset.kind === "audio")
    return (
      <div className="asset-image">
        <audio
          controls
          src={`/api/assets/${asset.id}/content`}
          aria-label={asset.name}
        />
      </div>
    );
  return (
    <div className="asset-image">
      {asset.kind === "text" ? (
        <pre>{asset.details.preview_text || asset.name}</pre>
      ) : asset.details.preview ? (
        <img
          src={`/api/assets/${asset.id}/preview`}
          alt={asset.name}
          loading="lazy"
        />
      ) : asset.kind === "audio" ? (
        <Volume2 size={35} />
      ) : asset.kind === "video" ? (
        <Film size={35} />
      ) : (
        <ImageIcon size={35} />
      )}
      <span className="media-tag">
        {asset.kind}
        {asset.details.composition ? " · editable" : ""}
      </span>
    </div>
  );
}
export function External({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="link-text">
      {children}
      <ArrowUpRight size={13} />
    </a>
  );
}
export const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "An unexpected error occurred";
export const dateText = (value: string) =>
  new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
