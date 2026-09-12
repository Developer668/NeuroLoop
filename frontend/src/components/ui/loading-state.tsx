"use client";
import { useEffect, useState } from "react";

const chevron = Array.from({ length: 9 }, (_, i) => ((i % 3) + Math.abs(Math.floor(i / 3) - 1)) * 90);
const order = [0, 1, 2, 5, 8, 7, 6, 3];
const orbit = Array.from({ length: 9 }, (_, i) => order.includes(i) ? order.indexOf(i) * 110 : null);
export default function LoadingState({ label = "Reading evidence", variant = "Drive" }: { label?: string; variant?: "Drive" | "Dots" | "Orbit" }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const start = performance.now();
    const timer = setInterval(() => setSeconds((performance.now() - start) / 1000), 100);
    return () => clearInterval(timer);
  }, []);
  return <div className="neuro-loading" role="status">
    <span className="neuro-loading-grid" aria-hidden="true">
      {(variant === "Orbit" ? orbit : chevron).map((delay, i) => <span key={i} style={{ borderRadius: variant === "Dots" ? "50%" : 1, opacity: delay === null ? .07 : .15, animation: delay === null ? "none" : `pixel-on ${variant === "Orbit" ? 950 : 650}ms ease-in-out ${delay}ms infinite` }} />)}
    </span>
    <span className="neuro-loading-label">{label}</span>
    <time aria-hidden="true">{seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(1)}s`}</time>
  </div>;
}
