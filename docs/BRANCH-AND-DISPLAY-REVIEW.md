# Branch and display review — September 11, 2026

## Remote comparison

Fetched `origin/codex/neuroloop-sync-20260911`. Both fetched commit and local HEAD are `5ea4350d6b68f87f68b942985fe1aa4933609fcd`; ahead/behind is 0/0. All committed backend changes on that branch are already present. No pull or merge was necessary. This does not mean the working directory is identical: it contains newer uncommitted work.

Local functional differences retained:

- Process-scoped CPU verification while the graphics-crash hold remains active; memory reserve and shared worker lock remain enforced.
- Corrected video feature aggregation: 2,816 features rather than the erroneous 1,408; exact identical-frame feature reuse and lossless static presentations.
- CPU-only text placement, Windows process-liveness checks, and feature-cache namespaces incorporating the complete model profile and device.
- Explicit Kragel registration/transfer decision gates and exclusion of padding-only timestamps from diagnostics.
- Updated isolated model dependency lock, regression tests, real CPU execution receipts, and expanded research notebooks.

These are local changes, not yet published by this review. Model weights and local data are not established by Git ancestry; separate inference evidence is required.

## Display changes

Removed the last editorial hero CSS layer and restored the preceding local two-column heading/brain composition. Kept the earlier enlarged brain, evidence navigation, sponsor strip and meme. A copy of the immediately preceding source is in `artifacts/ui-before-local-rollback`.

Magnitude colors now use light neutral anatomy below 12% of the fixed recording maximum, transitioning through red/orange/yellow. The legend describes that display threshold. Raw numerical predictions and recording bounds are unchanged. Signed mode remains available; magnitude mode hides sign. A nonzero prediction across a surface is not evidence that every part of a person's brain activated. There are 20,484 modeled cortical surface vertices here, not individually observed neurons. Meta's correlation visualization is also a different quantity from predicted response magnitude.

Brain Lab has one play/pause and speed control for stimulus and cortical frames. Video/audio use the media clock; static images and text advance through recorded timestamps. No interpolation creates new cortical samples. The one-second motion test has only one recorded sample, so its brain cannot demonstrate a multi-frame trajectory.

Research is labeled **Logs & analytics**. It includes saved response timelines, compute history, run outcomes, measured changes, operator counts, hemisphere heatmaps, TSAM/Kragel readouts and an execution-event table. The local marimo notebook can also be opened inline. Missing interventions remain empty; records are not invented to populate charts.

## Molab

Stopped the hosted notebook kernel and returned to the notebook dashboard, which reported **Running 0**. The notebook remains saved. Do not reopen it merely to check shutdown: opening it can provision a session again.

The official [June 2026 announcement](https://marimo.io/blog/reintroducing-molab) describes the public preview as free for reasonable usage. Its 4 CPUs and 32 GiB are hosted resources, separate from the laptop. Local marimo on port 2718 reads the current local database; Molab contains a historical sanitized snapshot, not a live connection to this database.

## Technical evidence and limits

Re-read evaluation `f97ea87b-c878-4f40-b6f6-54a47977f9c9` through the actual NeuroLoop MCP. The stored combined CPU output has shape 6 × 20,484, actual TSAM logits and seven Kragel diagnostic trajectories. See [fresh execution](FRESH-EXECUTION.md) and `artifacts/fresh-model-verification/combined-evidence.zip` for the prior forward-run and manifest verification. This review does not label a saved-output read as a new forward pass.

TSAM remains experimental without held-out calibration. Kragel registration and TRIBE transfer validation remain incomplete; it is excluded from decision scoring. GPU stability remains unproven. ARIA has a real review, but the bounded Launch experiment has not passed acceptance. TypeSafe and W&B Inference remain deferred.

## Prize assessment

There is no defensible win percentage without the competing entries and judging outcomes. The following is a comparative assessment of this project's evidence, not odds or a certification of eligibility:

| Category | Current strength | Main missing evidence |
|---|---|---|
| Best use of marimo | Strongest current fit | Demonstrate a real decision made using its linked charts and data |
| Best use of Weave | Credible | Show how traces identified a failure and changed an experiment |
| Best loop design | Plausible | Held-out evidence that the policy improves outcomes over a fixed baseline |
| Most production-ready | Weak today | Graphics stability, clean install/restore rehearsal, scientific and licensing gates |
| Best use of ARIA | Incomplete | Accepted bounded Launch experiment and imported result |
| Best use of TypeSafe | No current basis | No active TypeSafe implementation |

An honest pitch is a bounded, observable creative experimentation system using frozen models. It is not neural self-training, a validated human emotion decoder, or autonomous hardware repair.

## Verification in this review

- Frontend production build and TypeScript checks passed.
- Edge showed the restored two-column landing hero and neutral anatomy with warm magnitude overlays in dark mode.
- The combined video played, advanced the cortical frame, and ended at media time 5.0 s with frame 5 selected.
- The static-image presentation advanced from frame 0 to frame 7 and returned to the stopped play control.
- The logs page returned actual persisted run events, not sample rows. The embedded local marimo notebook rendered its interactive charts.
- NeuroLoop MCP returned the saved combined evaluation with its actual model profile and numerical evidence.
- Molab's notebook dashboard showed Running 0 after shutdown. No notebook was deleted.

The broader dashboard changes here are modest spacing, contrast, navigation and copy refinements, not a claim that every workspace screen has been redesigned. Scientific validation and GPU diagnosis are still outstanding.
