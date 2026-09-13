"use client";
import { useState } from "react";
import { ArrowUpRight, FileText, FolderOpen, Plus, Upload } from "lucide-react";
import type { Asset, Campaign, Creative } from "./LoopWorkspace";

const content = (id: string) => `/api/v2/assets/${id}/content`;
export function CampaignCollection({
  campaigns,
  overview,
  queued,
  active,
  create,
  open,
}: {
  campaigns: Campaign[];
  overview: boolean;
  queued: number;
  active: number;
  create: () => void;
  open: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const visible = campaigns.filter((c) =>
    `${c.spec.title} ${c.spec.brand.name}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <>
      {overview && (
        <>
          <section className="overview-hero nl-overview">
            <div>
              <span className="eyebrow">YOUR CREATIVE WORKSPACE</span>
              <h2>
                Every creative decision,
                <br />
                <em>considered.</em>
              </h2>
              <p>
                Bring your references together. Generate a first direction,
                compare the evidence, and follow each iteration.
              </p>
              <button className="button primary" onClick={create}>
                Start a campaign <ArrowUpRight size={16} />
              </button>
            </div>
            <div
              className="nl-loop-diagram"
              aria-label="Creative optimization cycle"
            >
              <span>Brief & references</span>
              <span>Generate</span>
              <span>Evaluate & compare</span>
              <span>Refine the next iteration</span>
            </div>
          </section>
          <div className="nl-metrics">
            <article>
              <span>CAMPAIGNS</span>
              <strong>{campaigns.length}</strong>
            </article>
            <article>
              <span>ACTIVE JOBS</span>
              <strong>{active}</strong>
            </article>
            <article>
              <span>QUEUED JOBS</span>
              <strong>{queued}</strong>
            </article>
            <article>
              <span>MEDIA</span>
              <strong>Image + video</strong>
            </article>
          </div>
        </>
      )}
      <section className="nl-panel">
        <div className="nl-collection-heading">
          <h2>{overview ? "Your campaigns" : "Projects"}</h2>
          <input
            type="search"
            aria-label="Search campaigns"
            placeholder="Search campaigns…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        {visible.length ? (
          <div className="nl-card-grid">
            {visible.map((c) => (
              <button
                className="project-card nl-project"
                key={c.id}
                onClick={() => open(c.id)}
              >
                <FolderOpen size={23} />
                <h3>{c.spec.title}</h3>
                <p>{c.spec.brief}</p>
                <span>
                  {c.spec.brand.name} · {c.spec.media_kind}
                </span>
                <ArrowUpRight size={17} />
              </button>
            ))}
          </div>
        ) : (
          <div className="nl-empty">
            <FolderOpen size={26} />
            <h3>
              {query
                ? "No matching campaigns"
                : "A home for your next creative"}
            </h3>
            <p>
              Keep the brief, original references, generated media, and
              experiment history together.
            </p>
            <button className="button" onClick={create}>
              <Plus size={15} /> New campaign
            </button>
          </div>
        )}
      </section>
    </>
  );
}

export function MediaLibrary({
  assets,
  campaignId,
  busy,
  upload,
}: {
  assets: Asset[];
  campaignId: string;
  busy: boolean;
  upload: (files: FileList | null) => void;
}) {
  const [filter, setFilter] = useState("all"),
    [query, setQuery] = useState("");
  const visible = assets.filter(
    (a) =>
      (filter === "all" || a.kind === filter) &&
      a.name.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <section className="nl-panel">
      <h2>Your creative library</h2>
      <p>
        Original references and generated outputs stay attached to their
        campaign.
      </p>
      {!campaignId ? (
        <div className="nl-empty">
          Select a campaign above to browse or upload media.
        </div>
      ) : (
        <>
          <label className="nl-upload">
            <Upload size={24} />
            <strong>Add images, videos, audio, or documents</strong>
            <span>Select multiple files together</span>
            <input
              aria-label="Upload campaign media"
              type="file"
              multiple
              disabled={busy}
              onChange={(e) => {
                upload(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
          <div className="nl-controls">
            <input
              aria-label="Search media"
              type="search"
              placeholder="Search media…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <select
              aria-label="Media type"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              {["all", "image", "video", "audio", "document"].map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
            <span>{visible.length} files</span>
          </div>
          <div className="nl-card-grid">
            {visible.map((a) => (
              <article className="asset-card nl-library-card" key={a.id}>
                <AssetPreview asset={a} />
                <div>
                  <h3>{a.name}</h3>
                  <small>
                    {a.kind} · {a.mime}
                  </small>
                  <a
                    className="nl-text-button"
                    href={content(a.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open original <ArrowUpRight size={14} />
                  </a>
                </div>
              </article>
            ))}
          </div>
          {!visible.length && (
            <div className="nl-empty">No media matches this selection.</div>
          )}
        </>
      )}
    </section>
  );
}
function AssetPreview({ asset }: { asset: Asset }) {
  if (asset.kind === "image")
    return <img src={content(asset.id)} alt={asset.name} loading="lazy" />;
  if (asset.kind === "video")
    return <video src={content(asset.id)} controls preload="metadata" />;
  if (asset.kind === "audio")
    return <audio src={content(asset.id)} controls preload="metadata" />;
  return (
    <div className="nl-document-preview">
      <FileText size={38} />
      <span>{asset.mime}</span>
    </div>
  );
}

export function CreativeComparison({
  creatives,
  kind,
}: {
  creatives: Creative[];
  kind: string;
}) {
  const available = creatives.filter((c) => c.output_asset_id);
  const [leftId, setLeft] = useState(""),
    [rightId, setRight] = useState("");
  const left = available.find((c) => c.id === leftId) || available[0];
  const right = available.find((c) => c.id === rightId) || available.at(-1);
  if (available.length < 2)
    return (
      <div className="nl-empty">
        Generate at least two candidates in this run to compare their media and
        evidence.
      </div>
    );
  const lq = left?.evidence?.quality,
    rq = right?.evidence?.quality;
  const comparable =
    left?.evidence?.evaluations.find((e) => e.evaluator === "vision")
      ?.comparison_key ===
      right?.evidence?.evaluations.find((e) => e.evaluator === "vision")
        ?.comparison_key &&
    !!lq &&
    !!rq;
  return (
    <section className="nl-panel">
      <h2>Compare creatives</h2>
      <p>
        {comparable && left?.id !== right?.id
          ? `Quality proxy difference: ${(rq!.value - lq!.value).toFixed(3)}. Same evaluator configuration; this is not a measured sales lift.`
          : "Select distinct candidates with comparable evaluation evidence to inspect a score difference."}
      </p>
      <div className="nl-two-col">
        {[
          { candidate: left, select: setLeft, label: "First candidate" },
          { candidate: right, select: setRight, label: "Second candidate" },
        ].map(({ candidate, select, label }) => (
          <article key={label}>
            <label>
              {label}
              <select
                aria-label={label}
                value={candidate?.id || ""}
                onChange={(e) => select(e.target.value)}
              >
                {available.map((c) => (
                  <option key={c.id} value={c.id}>
                    Round {c.round + 1} · {c.plan.strategy} · {c.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
            {candidate && (
              <>
                {kind === "image" ? (
                  <img
                    className="nl-media"
                    src={content(candidate.output_asset_id!)}
                    alt={label}
                  />
                ) : (
                  <video
                    className="nl-media"
                    src={content(candidate.output_asset_id!)}
                    controls
                    preload="metadata"
                  />
                )}
                <h3>{candidate.plan.strategy}</h3>
                <p>{candidate.plan.prompt}</p>
                <strong>
                  Quality proxy:{" "}
                  {candidate.evidence?.quality?.value.toFixed(3) ?? "Pending"}
                </strong>
                {candidate.evidence?.hard_constraints.map((c) => (
                  <div className="nl-check" key={c.name}>
                    <span>{c.name}</span>
                    <span>{c.status}</span>
                  </div>
                ))}
              </>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
