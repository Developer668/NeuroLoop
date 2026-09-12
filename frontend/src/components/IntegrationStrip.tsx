"use client";
import { useRef } from "react";
import { useInView } from "motion/react";
import Link from "next/link";

const integrations = [
  { name: "marimo", asset: "marimo", role: "Interactive research", width: 120 },
  { name: "Weights & Biases", asset: "wandb", role: "Experiment records", width: 190 },
  { name: "W&B Weave", asset: "weave", role: "Execution traces", width: 40 },
];

export function IntegrationStrip() {
  const ref = useRef<HTMLElement>(null);
  const visible = useInView(ref);
  return (
    <section ref={ref} className="integration-strip" aria-label="Tools used in NeuroLoop">
      <div className="integration-strip-heading">
        <span className="eyebrow">BUILT WITH</span>
      </div>
      <div className="integration-window">
        <div className="integration-track" style={{ animationPlayState: !visible ? "paused" : "running" }}>
          {[0, 1].map(copy => (
            <div className="integration-group" key={copy} aria-hidden={copy === 1 ? true : undefined}>
              {integrations.map(item => (
                <div className="integration-item" key={item.asset}>
                  <div className="integration-logo">
                    <img src={`/brand/integrations/${item.asset}.svg`} alt={item.name} width={item.width} height={40} loading="lazy" />
                    {item.asset === "weave" && <span aria-hidden="true">Weave</span>}
                  </div>
                  <span className="integration-role">{item.role}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <Link className="integration-details" href="/workspace?view=connections">Explore the integrations ↗</Link>
    </section>
  );
}
