"use client";
import { useEffect, useState, type ReactNode } from "react";
import styles from "./LiveLogPanel.module.css";

export default function LiveLogPanel({ title, count, updatedAt, children }: {
  title: string; count: number; updatedAt?: number; children: ReactNode;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const age = updatedAt ? Math.max(0, Math.floor((now - updatedAt) / 1000)) : null;
  return <details className={`nl-panel ${styles.panel}`} open>
    <summary className={styles.header}>
      <span>{title} <small>{count} records</small></span>
      <small className={styles.sync}>{age === null ? "Connecting…" : age > 10 ? `Updates delayed · ${age}s since sync` : `Live · synced ${age}s ago`}</small>
    </summary>
    <p className={styles.hint}>Newest first · refreshes every 2.5 seconds · expand a record for details</p>
    <div className={styles.viewport} role="region" aria-label={`${title} records`} tabIndex={0}>
      {count ? children : <p>No records yet. New activity will appear here automatically.</p>}
    </div>
  </details>;
}
