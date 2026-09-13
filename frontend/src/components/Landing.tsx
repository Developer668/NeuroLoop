"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  ArrowRight,
  AudioLines,
  FileText,
  Film,
  Braces,
  Check,
  ScanLine,
} from "lucide-react";
import { Brand } from "./UI";
import { MotionFooter } from "./ReleaseMotion";
import { IntegrationStrip } from "./IntegrationStrip";
const BrainCanvas = dynamic(() => import("./BrainCanvas"), {
  ssr: false,
  loading: () => (
    <div className="brain-loading">Preparing the cortical surface…</div>
  ),
});
export default function Landing() {
  const root = useRef<HTMLElement>(null);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const nodes = root.current?.querySelectorAll("[data-reveal]");
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("revealed");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.12 },
    );
    nodes?.forEach((node) => observer.observe(node));
    // Scroll-aware nav: condense into a deeper glass bar once the page moves.
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    // Pointer-tracked spotlight in the hero observatory (fine pointers only,
    // never when the visitor prefers reduced motion).
    const hero = root.current?.querySelector<HTMLElement>(".landing-hero");
    const fine =
      window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const onMove = (event: PointerEvent) => {
      if (!hero) return;
      const rect = hero.getBoundingClientRect();
      hero.style.setProperty("--mx", `${event.clientX - rect.left}px`);
      hero.style.setProperty("--my", `${event.clientY - rect.top}px`);
    };
    if (fine && hero) hero.addEventListener("pointermove", onMove);
    // Eased count-up for the observatory readouts. The markup already ships
    // the final values, so hydration stays stable; we only animate when the
    // visitor allows motion.
    const counters = root.current?.querySelectorAll<HTMLElement>(
      "[data-count-to]",
    );
    let raf = 0;
    if (
      counters?.length &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      const started = performance.now();
      const duration = 1600;
      const tick = (now: number) => {
        const t = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - t, 3);
        counters.forEach((node) => {
          const target = Number(node.dataset.countTo || "0");
          const pad = Number(node.dataset.countPad || "0");
          const value = Math.round(target * eased);
          const label = pad
            ? String(value).padStart(pad, "0")
            : value.toLocaleString("en-US");
          if (node.firstChild) node.firstChild.textContent = label;
        });
        if (t < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
      if (fine && hero) hero.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);
  return (
    <main className="landing" ref={root} id="top">
      <div className="reading-progress" aria-hidden="true" />
      <nav className={"landing-nav" + (scrolled ? " scrolled" : "")}>
        <Brand />
        <div className="landing-nav-links">
          <a href="#how-it-works">How it works</a>
          <a href="#for-agents">For agents</a>
          <Link className="button primary" href="/workspace">
            Open workspace
            <ArrowUpRight size={15} />
          </Link>
        </div>
      </nav>
      <section className="landing-hero">
        <div className="hero-copy-new" data-reveal>
          <span className="eyebrow">THE CREATIVE EXPERIMENT ENGINE</span>
          <h1>Great creative.<br /><span>A closer look.</span></h1>
          <p>
            Explore how your creative is predicted to engage the cortex. Test a
            deliberate change. Follow the evidence to your next version.
          </p>
          <div className="hero-actions">
            <Link href="/workspace?view=library" className="button primary">
              Bring your creative
              <ArrowUpRight size={18} />
            </Link>
            <a href="#how-it-works" className="text-link">
              See the process
              <ArrowRight size={15} />
            </a>
          </div>
          <div className="input-formats">
            <span>
              <Film size={15} />
              Video
            </span>
            <span>
              <AudioLines size={15} />
              Audio
            </span>
            <span>
              <FileText size={15} />
              Text
            </span>
            <span className="format-note">One connected workflow</span>
          </div>
        </div>
        <div className="hero-observatory" data-reveal>
          <div className="orbital-ring ring-one" />
          <div className="orbital-ring ring-two" />
          <div className="orbit-label label-top">THE CORTICAL OBSERVATORY</div>
          <BrainCanvas publicMesh cinematic />
          <div className="orbit-label label-bottom">
            <span data-count-to="20484">
              20,484<small>surface vertices</small>
            </span>
            <span data-count-to="2" data-count-pad="2">
              02<small>hemispheres</small>
            </span>
            <ScanLine size={22} />
          </div>
          <span className="observatory-note">
            Anatomical reference · fsaverage5 cortical surface
          </span>
        </div>
      </section>
      <div className="method-strip">
        <span>CREATIVITY, WITH A RECORD.</span>
        <span>
          Originals preserved
          <Check size={14} />
        </span>
        <span>
          Controlled experiments
          <Check size={14} />
        </span>
        <span>
          Evidence you can inspect
          <Check size={14} />
        </span>
      </div>
      <section className="landing-process" id="how-it-works">
        <div className="section-intro" data-reveal>
          <span className="eyebrow">A CLEARER WAY FORWARD</span>
          <h2>
            Keep the original.
            <br />
            Question the next version.
          </h2>
          <p>
            One original. One deliberate change. A record of what happened.
            Compare predictions on the same basis before deciding what to keep.
          </p>
        </div>
        <div className="process-steps">
          <article data-reveal>
            <div className="step-illustration original-stack">
              <span />
              <span />
              <span>
                <Film size={30} />
                <small>YOUR ORIGINAL</small>
              </span>
            </div>
            <span className="step-number">01 / BRING</span>
            <h3>Start with something real.</h3>
            <p>
              Upload your creative and chosen references. Define the goal,
              preserve your source, and keep the brief in view.
            </p>
            <Link href="/workspace?view=library">
              Open your library
              <ArrowUpRight size={16} />
            </Link>
          </article>
          <article data-reveal>
            <div className="step-illustration experiment-diagram">
              <span>Original</span>
              <i />
              <span className="variant-node">A controlled change</span>
              <i />
              <span>Evaluate</span>
            </div>
            <span className="step-number">02 / EXPLORE</span>
            <h3>Make the change count.</h3>
            <p>
              Run a bounded experiment against the same references and model
              profile. Follow every keep, revert, and stopping decision.
            </p>
            <Link href="/workspace?view=projects">
              Create an experiment
              <ArrowUpRight size={16} />
            </Link>
          </article>
          <article data-reveal>
            <div className="step-illustration evidence-graphic">
              <div>
                <Check size={18} />
                Source preserved
              </div>
              <div>
                <Braces size={18} />
                Evidence attached
              </div>
              <div>
                <ArrowUpRight size={18} />
                Selected creative
              </div>
            </div>
            <span className="step-number">03 / DECIDE</span>
            <h3>Take the evidence with you.</h3>
            <p>
              Inspect the cortical timeline, compare recorded responses, and
              export the selected file with its complete experiment history.
            </p>
            <Link href="/workspace?view=brain">
              Explore the brain lab
              <ArrowUpRight size={16} />
            </Link>
          </article>
        </div>
      </section>
      <section className="evidence-path" aria-labelledby="evidence-path-title" data-reveal>
        <div>
          <span className="eyebrow">FOLLOW THE EVIDENCE</span>
          <h2 id="evidence-path-title">One experiment.<br />Three ways to inspect it.</h2>
          <p>Move from a moment in the creative to the complete record of the run.</p>
        </div>
        <div className="evidence-path-links">
          <Link href="/workspace?view=brain"><span className="evidence-path-number">01</span><div><strong>The response</strong><p>Explore the predicted cortical surface and its timeline in Brain Lab.</p></div><ArrowUpRight size={19} /></Link>
          <Link href="/workspace?view=research"><span className="evidence-path-number">02</span><div><strong>The comparison</strong><p>Inspect saved evaluations, charts and the local research ledger.</p></div><ArrowUpRight size={19} /></Link>
          <Link href="/workspace?view=telemetry"><span className="evidence-path-number">03</span><div><strong>The execution</strong><p>Follow model calls, saved logs and verified trace links.</p></div><ArrowUpRight size={19} /></Link>
        </div>
      </section>
      <section className="agent-section" id="for-agents">
        <div data-reveal>
          <span className="eyebrow">YOUR WORKFLOW, CONNECTED</span>
          <h2>
            A workspace for you.
            <br />
            An interface for
            <br />
            <span>your agent.</span>
          </h2>
          <p>
            Connect an MCP-compatible client to the same evaluation engine. Give
            it a goal and a budget. Get back a creative, the evidence, and a
            reason to stop.
          </p>
          <Link href="/workspace?view=settings" className="button">
            Connect with MCP
            <ArrowUpRight size={16} />
          </Link>
        </div>
        <div className="agent-terminal" data-reveal>
          <div className="terminal-bar">
            <span />
            <span />
            <span />
            <small>NeuroLoop / example MCP sequence</small>
          </div>
          <div className="terminal-content">
            <small>DISCOVER</small>
            <code><span className="syntax-function">get_capabilities</span><span className="syntax-punctuation">(</span><span className="syntax-argument"></span><span className="syntax-punctuation">)</span></code>
            <small>EXPERIMENT</small>
            <code><span className="syntax-function">create_campaign</span><span className="syntax-punctuation">(</span><span className="syntax-argument">spec</span><span className="syntax-punctuation">)</span></code>
            <code><span className="syntax-function">optimize</span><span className="syntax-punctuation">(</span><span className="syntax-argument">campaign_id, idempotency_key, config, reference_asset_ids</span><span className="syntax-punctuation">)</span></code>
            <small>REVIEW & EXPORT</small>
            <code><span className="syntax-function">get_evidence</span><span className="syntax-punctuation">(</span><span className="syntax-argument">run_id, creative_id</span><span className="syntax-punctuation">)</span></code>
            <code><span className="syntax-function">export_result</span><span className="syntax-punctuation">(</span><span className="syntax-argument">run_id</span><span className="syntax-punctuation">)</span></code>
            <div className="terminal-note">
              Authenticated. Bounded. Traceable.
            </div>
          </div>
        </div>
      </section>
      <section className="honest-science" data-reveal>
        <span className="eyebrow">THE SCIENCE, IN PERSPECTIVE</span>
        <h2>
          More to explore.
          <br />
          Less to assume.
        </h2>
        <div>
          <p>
            TRIBE predicts an average cortical response to a stimulus. Reference
            similarity measures agreement between model predictions. It does not
            measure a person’s thoughts, preference, or likelihood to buy.
          </p>
          <p>
            The brain above shows real reference anatomy. Response overlays
            appear after an evaluation. Surface vertices are samples of the
            cortex, not individually observed neurons.
          </p>
          <Link className="text-link" href="/workspace?view=research">
            Explore the method and limitations
            <ArrowUpRight size={15} />
          </Link>
        </div>
      </section>

      <IntegrationStrip />
      <aside className="build-easter-egg" aria-label="Behind the build">
        <details>
          <summary>
            <span>
              <span className="eyebrow">BEHIND THE BUILD</span>
              <span className="build-easter-egg-title">Built locally. Tested emotionally.</span>
            </span>
            <span className="build-easter-egg-toggle" aria-hidden="true">+</span>
          </summary>
          <figure>
            <img
              src="/brand/neuroloop-tribe-local-meme.png"
              width={1448}
              height={1086}
              loading="lazy"
              decoding="async"
              alt="Woman yelling at a cat: I said run TRIBE locally. The cat replies: You have 12 GB of VRAM. Codex and Meta TRIBE v2 badges. Caption: The model fits. The laptop has questions."
            />
            <figcaption>A little humor from building NeuroLoop on a laptop.</figcaption>
          </figure>
        </details>
      </aside>

      <MotionFooter />
    </main>
  );
}
