"use client";

/** Supplied two-bank path geometry, animated in CSS and paused outside the footer. */
export function BackgroundPaths() {
  return <div className="background-paths" aria-hidden="true"><svg viewBox="0 0 696 316" fill="none">
    {[-1, 1].flatMap(position => Array.from({ length: 36 }, (_, i) => <path
      key={`${position}-${i}`} className="bg-path"
      style={{ animationDelay: `${-i * .7}s`, animationDuration: `${20 + i % 11}s` }}
      d={`M-${380 - i * 5 * position} -${189 + i * 6}C-${380 - i * 5 * position} -${189 + i * 6} -${312 - i * 5 * position} ${216 - i * 6} ${152 - i * 5 * position} ${343 - i * 6}C${616 - i * 5 * position} ${470 - i * 6} ${684 - i * 5 * position} ${875 - i * 6} ${684 - i * 5 * position} ${875 - i * 6}`}
      stroke="currentColor" strokeWidth={.5 + i * .03} strokeOpacity={Math.min(.1 + i * .03, 1)} pathLength={1} strokeDasharray="0.42 1"
    />))}
  </svg></div>;
}
