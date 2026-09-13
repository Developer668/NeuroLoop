import styles from "./HelpGuide.module.css";

const chapters = [
  { id: "start", title: "Create your first ad", body: <>
    <ol>
      <li><strong>Check Connections & settings.</strong> The notebook runs the models. It must be connected and have the models needed for your request. A model listed as registered has not necessarily completed a job.</li>
      <li><strong>Open Create.</strong> Click the prompt box. Enter your brand or project name and describe the product, audience, scene, and desired result. Choose the media type and aspect ratio.</li>
      <li><strong>Add references when supported.</strong> Video requests can include reference media and documents. The current image path uses text prompts and does not edit an uploaded image. Use product facts you can support.</li>
      <li><strong>Check Run details, then start the creative loop.</strong> This creates a saved campaign and run. Starting another request creates another run; refreshing the page does not start over.</li>
      <li><strong>Watch the progress panel.</strong> It shows the current job, completed jobs, and connection updates. Open View run & outputs to see generated media, decisions, and the execution history.</li>
    </ol>
    <p><strong>Example brief:</strong> “Create a product ad for a desk lamp. One steady shot on a tidy desk. Warm light turns on. Keep the lamp shape consistent. No text or unsupported claims.”</p>
    <p>Choose 5, 10, or 15 seconds using Video length below the composer. This setting controls duration; a number written in your prompt does not override it.</p>
  </> },
  { id: "loop", title: "What happens after you click Start?", body: <>
    <div className={styles.flow} aria-label="Creative loop stages">Plan → Review plan → Generate → Evaluate → Decide → Revise or stop</div>
    <p>The planner proposes an approach. TypeSafe reviews it. A generation model produces media, evaluators inspect it, and the decision process chooses the next action. A revision creates another candidate linked to its parent.</p>
    <p>Some steps can repeat. The loop can stop for human review, missing evidence, a failure, or a configured limit. A stopped run does not necessarily mean an ad was completed or accepted.</p>
    <p>The bar counts completed jobs that are already scheduled. It is not an estimate of the total time remaining. While a model is working, the activity bar has no percentage unless the service supplies one.</p>
  </> },
  { id: "results", title: "Find, compare, and review your results", body: <>
    <ol>
      <li>Open <strong>Campaigns</strong> and select your campaign. Use <strong>Runs</strong> and the run selector to return to an earlier attempt.</li>
      <li>The run page shows the current creative once generation returns an output. <strong>Media library</strong> holds campaign media. Uploaded references and generated ads are different items.</li>
      <li>Use <strong>Compare</strong> to inspect candidates and <strong>Lineage</strong> to follow revisions. Compare quality scores only when the evaluator and evaluation settings match.</li>
      <li>Review the media yourself. Use the available feedback actions to record your decision. A favorable model score is not your approval.</li>
      <li>Use the media download links to save originals. Advertising is a separate workflow; creating an ad does not publish it.</li>
    </ol>
  </> },
  { id: "brain", title: "Understand brain and emotion data", body: <>
    <p>Open <strong>Brain & emotion</strong> and choose the exact media under evaluation. The section links jump to playback, cortical timelines, emotion outputs, brain regions, and model receipts.</p>
    <dl>
      <dt>TRIBE V2</dt><dd>Predicts cortical response to video. Play the video or move the scrubber to inspect stored prediction frames. The colors are model predictions, not a recording of someone watching your ad.</dd>
      <dt>TSAM</dt><dd>Produces audiovisual affect scores for recorded time windows. Follow playback or select a window. Raw scores are not probabilities or measured feelings.</dd>
      <dt>Kragel</dt><dd>Shows experimental cortical pattern correlations. Select an emotion pattern to focus its timeline. Registration and decision-eligibility labels explain whether the result can inform a decision.</dd>
      <dt>GLM</dt><dd>Reviews sampled visual content and, when recorded, summarizes what happened. Its quality score is a model assessment, not measured audience or advertising performance.</dd>
    </dl>
    <p>An empty result means no matching evidence has arrived. Images do not receive cortical predictions through the current video-only TRIBE adapter.</p>
  </> },
  { id: "logs", title: "Find logs and saved evidence", body: <>
    <p><strong>Logs & charts</strong> starts with the outcome scorecard. Other sections show execution attempts, model evidence, decision gates, worker connections, backups, and run history. Search the tables, sort columns, export CSV, or download the full snapshot.</p>
    <p><strong>Weave</strong> stores instrumented agent and model calls, timings, errors, and published evidence tables. Open a verified trace link from the run. <strong>W&B</strong> stores charts and versioned media/evidence artifacts. A backup export is not an additional creative run.</p>
    <p>The web polls run state every 2.5 seconds and the telemetry page every 10 seconds. Marimo’s evidence charts read published snapshots when refreshed; they are not a continuous stream of every notebook event.</p>
    <p><strong>Unavailable</strong> means there is not enough recorded evidence to calculate a metric. Missing cost is not zero cost, and a connected model is not proof of a completed generation.</p>
  </> },
  { id: "help", title: "When something is waiting or missing", body: <>
    <dl>
      <dt>Notebook offline / waiting to start</dt><dd>Your request is saved. Open Connections & settings, then the configured Marimo notebook. Its model setup and worker must be running. An open notebook tab alone does not connect the worker. Return to the run after it connects.</dd>
      <dt>Connected, but still queued</dt><dd>The required model may be unavailable or another job may be using it. Check the named capability in the progress panel and worker details in Logs & charts.</dd>
      <dt>Working, but no video yet</dt><dd>Loading and generation can take time. Check the worker’s latest update. The app cannot display a generated file until the service returns it.</dd>
      <dt>Needs review or failed</dt><dd>Read the stop reason and latest decision. Resolve the missing input or connection before using an available retry action. If the provider outcome is uncertain, inspect the recorded result before requesting another generation.</dd>
      <dt>Old update time or connection error</dt><dd>The panel may be showing the last saved state. Use Refresh workspace and check the local service and notebook connection. Repeatedly clicking Start creates extra work.</dd>
      <dt>No brain data, score, or chart</dt><dd>Choose the correct media and inspect Models & receipts. The evaluator may not have run, may have failed, or may not support that media. The app does not fill missing results with sample data.</dd>
    </dl>
  </> },
];

export default function HelpGuide() {
  return <article className={styles.guide}>
    <header><span>NEUROLOOP GUIDE</span><h1>How to use NeuroLoop</h1><p>Create an ad, follow its progress, review the result, and inspect the evidence behind it.</p></header>
    <nav className={styles.shortcuts} aria-label="Start using NeuroLoop"><a href="/workspace?view=neuro">Create an ad</a><a href="/workspace?view=overview">Find a campaign</a><a href="/workspace?view=settings">Check connections</a></nav>
    <nav className={styles.contents} aria-label="Guide contents">{chapters.map(c => <a key={c.id} href={`#guide-${c.id}`}>{c.title}</a>)}</nav>
    {chapters.map((c, i) => <section key={c.id} id={`guide-${c.id}`}><h2><span>{i + 1}</span>{c.title}</h2>{c.body}</section>)}
  </article>;
}
