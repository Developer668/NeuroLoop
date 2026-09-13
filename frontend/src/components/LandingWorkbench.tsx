"use client";
import { useState } from "react";
import { ArrowUpRight, ArrowRight, FileText, Film, ScanLine, GitBranch } from "lucide-react";
import styles from "./LandingWorkbench.module.css";

const chapters = [
  { label: "The brief", title: "Give the idea a direction.", body: "Name the product, choose a moment, and say what must stay unchanged. Your references travel with the brief.", icon: FileText, items: ["Product & audience", "Scene & camera", "References & constraints"], output: "A brief you can edit", link: "neuro" },
  { label: "The creative", title: "Put the first version on screen.", body: "Generate an image or video in the connected notebook. The actual file returns to your campaign, alongside its model and generation settings.", icon: Film, items: ["Image or video", "Original file preserved", "Generation settings attached"], output: "A creative you can play", link: "library" },
  { label: "The evidence", title: "Look beyond a single score.", body: "Read the visual review. Explore cortical and affective predictions when those evaluators are available. Keep missing evidence visible.", icon: ScanLine, items: ["Visual review", "Available model predictions", "Sources & uncertainty"], output: "A record you can inspect", link: "brain" },
  { label: "The next version", title: "Change something for a reason.", body: "Use the recorded review to guide a revision. Compare it with its parent, follow the decision, and keep the full history.", icon: GitBranch, items: ["Evidence-led revision", "Parent and child comparison", "Human review before deployment"], output: "A decision you can trace", link: "runs" },
];
const prompts = [
  { name: "Product film", text: "Create a five-second product film for my brand. Show the product on a quiet studio surface with one slow camera push. Keep its shape and packaging faithful to my reference. Use soft directional light, crisp detail and no added claims. End on a clean hero shot." },
  { name: "Campaign image", text: "Create an editorial campaign image for my brand. Put the product at the center of a simple, tactile scene. Use the supplied reference for product identity. Leave clear space for copy, avoid invented logos and keep every visible detail intentional." },
  { name: "Improve a video", text: "Review my attached video against the brief. Identify one specific visual issue supported by the footage. Propose a focused revision that preserves product identity and camera direction. Compare the revision with the original and explain what changed." },
];

export default function LandingWorkbench() {
  const [chapter, setChapter] = useState(0);
  const [choice, setChoice] = useState(0);
  const [brief, setBrief] = useState(prompts[0].text);
  const [error, setError] = useState("");
  const active = chapters[chapter];
  const Icon = active.icon;
  function begin() {
    try {
      sessionStorage.setItem("neuroloop-landing-brief", JSON.stringify({ prompt: brief, kind: choice === 1 ? "image" : "video" }));
      window.location.assign("/workspace?view=neuro");
    } catch { setError("Your browser could not save this draft. Copy your brief, then open the workspace."); }
  }
  return <div className={styles.experience}>
    <section className={styles.walkthrough} aria-labelledby="loop-story-title" id="inside-the-loop">
      <div className={styles.intro} data-reveal><span className="eyebrow">INSIDE THE LOOP</span><h2 id="loop-story-title">The idea is only<br />the beginning.</h2><p>Every version should leave you with something more than another file.</p></div>
      <div className={styles.stage}>
        <div className={styles.chapters} role="group" aria-label="Explore the creative loop">
          {chapters.map((item, index) => <button key={item.label} aria-pressed={chapter === index} onClick={() => setChapter(index)}><span>0{index + 1}</span>{item.label}<ArrowRight size={16} /></button>)}
        </div>
        <div className={styles.detail} key={chapter}>
          <div className={styles.object} aria-hidden="true"><div className={styles.sheetBack} /><div className={styles.sheetMiddle} /><div className={styles.sheetFront}><span>NEUROLOOP / 0{chapter + 1}</span><Icon size={60} strokeWidth={1} /><strong>{active.output}</strong><div className={styles.rule} /><small>{active.items[0]}</small></div></div>
          <div className={styles.chapterCopy}><span className="eyebrow">0{chapter + 1} / {active.label.toUpperCase()}</span><h3>{active.title}</h3><p>{active.body}</p><ul>{active.items.map(item => <li key={item}>{item}</li>)}</ul><a className="text-link" href={`/workspace?view=${active.link}`}>Open in the workspace <ArrowUpRight size={16} /></a></div>
        </div>
      </div>
      <p className={styles.caption}>Explore the workflow above. Live results appear in your workspace after a run.</p>
    </section>
    <section className={styles.briefSection} id="start-a-brief" aria-labelledby="brief-title" data-reveal>
      <div><span className="eyebrow">START WITH A SENTENCE</span><h2 id="brief-title">What are you<br />working on?</h2><p>A clear brief gives the loop something concrete to work with. Pick a starting point and make it yours.</p><a className="text-link" href="/workspace?view=docs">Read the working guide <ArrowUpRight size={15} /></a></div>
      <div className={styles.editor}><div className={styles.editorTop}><span>YOUR CREATIVE BRIEF</span><FileText size={16} /></div><div className={styles.presets} role="group" aria-label="Brief starting points">{prompts.map((item, index) => <button key={item.name} aria-pressed={choice === index} onClick={() => { setChoice(index); setBrief(item.text); }}>{item.name}</button>)}</div><label className={styles.promptLabel} htmlFor="landing-brief">Edit your brief</label><textarea id="landing-brief" value={brief} maxLength={8000} onChange={event => setBrief(event.target.value)} /><div className={styles.editorBottom}><span>Attach your references in the workspace.</span><button className="button primary" disabled={!brief.trim()} onClick={begin}>Use this brief <ArrowUpRight size={17} /></button></div>{error && <p role="alert">{error}</p>}<small className={styles.draftNote}>Saves a draft. Nothing generates until you start the run.</small></div>
    </section>
  </div>;
}
