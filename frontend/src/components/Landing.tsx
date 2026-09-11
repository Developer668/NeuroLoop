"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";
import {
  ArrowUpRight,
  ArrowRight,
  AudioLines,
  FileText,
  Film,
  MoveUpRight,
  Braces,
  Check,
  ScanLine,
} from "lucide-react";
import { Brand } from "./UI";
import { MotionFooter } from "./ReleaseMotion";
const BrainCanvas = dynamic(() => import("./BrainCanvas"), {
  ssr: false,
  loading: () => (
    <div className="brain-loading">Preparing the cortical surface…</div>
  ),
});
export default function Landing() {
  const root = useRef<HTMLElement>(null);
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
    return () => observer.disconnect();
  }, []);
  return (
    <main className="landing" ref={root} id="top">
      <div className="reading-progress" aria-hidden="true" />
      <nav className="landing-nav">
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
          <h1>
            Great creative.
            <br />A closer <span>look.</span>
          </h1>
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
            <span>
              20,484<small>surface vertices</small>
            </span>
            <span>
              02<small>hemispheres</small>
            </span>
            <ScanLine size={22} />
          </div>
          <span className="observatory-note">
            Anatomical surface · drag to explore
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
            From a good instinct
            <br />
            to a considered decision.
          </h2>
          <p>
            A focused loop for creative work. Start with what you have. Change
            what you can explain.
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
          <Link href="/workspace?view=connections" className="button">
            Connect with MCP
            <ArrowUpRight size={16} />
          </Link>
        </div>
        <div className="agent-terminal" data-reveal>
          <div className="terminal-bar">
            <span />
            <span />
            <span />
            <small>NeuroLoop / MCP tool sequence</small>
          </div>
          <div className="terminal-content">
            <small>DISCOVER</small>
            <code>get_capabilities()</code>
            <small>EXPERIMENT</small>
            <code>evaluate_creative(project_id)</code>
            <code>run_experiment(project_id, operator)</code>
            <small>REVIEW & EXPORT</small>
            <code>get_evidence(evaluation_id)</code>
            <code>export_result(run_id)</code>
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

      <MotionFooter />
    </main>
  );
}
