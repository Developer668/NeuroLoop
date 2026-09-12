"use client";

export function LineChart({
  series,
  labels = [],
  height = 190,
  caption,
}: {
  series: { name: string; values: number[]; tone?: string }[];
  labels?: string[];
  height?: number;
  caption?: string;
}) {
  const all = series.flatMap((s) => s.values).filter(Number.isFinite);
  if (!all.length)
    return (
      <div className="chart-empty">
        <span>No recorded measurements yet</span>
        <small>A chart appears after a real evaluation completes.</small>
      </div>
    );
  let min = Math.min(...all),
    max = Math.max(...all);
  const padding = Math.max((max - min) * 0.14, 0.01);
  min -= padding;
  max += padding;
  const width = 640,
    left = 46,
    right = 15,
    top = 16,
    bottom = 34,
    plotH = height - top - bottom;
  const count = Math.max(...series.map((s) => s.values.length), 2);
  const x = (i: number) => left + (i / (count - 1)) * (width - left - right);
  const y = (n: number) => top + ((max - n) / (max - min)) * plotH;
  return (
    <figure className="line-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={caption || series.map((s) => s.name).join(", ")}
      >
        {[0, 1, 2, 3].map((i) => {
          const v = min + ((max - min) * i) / 3;
          return (
            <g key={i}>
              <line
                x1={left}
                x2={width - right}
                y1={y(v)}
                y2={y(v)}
                className="chart-grid"
              />
              <text x={left - 10} y={y(v) + 4} textAnchor="end">
                {v.toFixed(2)}
              </text>
            </g>
          );
        })}
        {series.map((s, k) => (
          <g
            key={s.name}
            style={{ color: s.tone || (k ? "var(--copper)" : "var(--wine)") }}
          >
            <polyline
              points={s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              vectorEffect="non-scaling-stroke"
            />
            {s.values.map((v, i) => (
              <circle
                key={i}
                cx={x(i)}
                cy={y(v)}
                r={3.3}
                fill="var(--paper)"
                stroke="currentColor"
                strokeWidth="1.8"
              >
                <title>
                  {s.name}: {v.toFixed(4)}
                </title>
              </circle>
            ))}
          </g>
        ))}
        {(labels.length
          ? labels
          : Array.from({ length: count }, (_, i) => String(i))
        ).map((l, i) =>
          i === 0 || i === count - 1 || count <= 9 ? (
            <text key={i} x={x(i)} y={height - 8} textAnchor="middle">
              {l}
            </text>
          ) : null,
        )}
      </svg>
      <figcaption>
        {series.map((s, k) => (
          <span key={s.name}>
            <i
              style={{
                background: s.tone || (k ? "var(--copper)" : "var(--wine)"),
              }}
            />
            {s.name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

export function BudgetBar({
  used,
  total,
  label,
}: {
  used: number;
  total: number;
  label: string;
}) {
  return (
    <div className="budget-bar">
      <div>
        <span>{label}</span>
        <strong>
          {used} <em>/ {total}</em>
        </strong>
      </div>
      <progress value={used} max={Math.max(total, 1)} aria-label={label} />
    </div>
  );
}
