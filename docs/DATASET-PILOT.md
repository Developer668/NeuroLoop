# Pitt labeled ad pilot

The local pilot is a small, static-image pack for deterministic, model-free
data and provenance checks. It is not a replacement for the audiovisual
evaluation fixtures.

## What is in the pack

The pack contains 50 manifest rows and 50 image files selected from the
`Mindykkyan/PittadsDB-AdsPics` mirror of the University of Pittsburgh Ads
dataset. The ten selected upstream affective/attitudinal labels are balanced at
five rows each:

`active`, `amazed`, `angry`, `calm`, `cheerful`, `confident`, `creative`,
`emotional`, `inspired`, and `sad`.

Each row keeps the source key, source URL, raw annotator label lists, majority
vote count, byte length, and SHA-256 digest. These are human ad-perception
annotations, not measured cortical responses, sentiment probabilities, or
ground-truth claims about a viewer.

The pack is static image ads with human sentiment annotations. It has no audio
or video stream and therefore cannot validate the audiovisual TSAM path. It
should only be used with an explicitly supported static-image/TRIBE experiment;
it cannot establish TSAM or audiovisual Kragel behavior.

The image rights are not established by this repository. Keep the provenance
fields, use the files only under the permissions that apply to the intended
research/demo, and do not redistribute or use them commercially without
confirming rights.

## Verify safely

The verifier is stdlib-only, does not contact the network, imports no model
runtime, runs no inference, and never writes to the pack:

```text
python3 scripts/verify_pitt_ads_pilot.py \
  /Users/adityadas/Desktop/Programming/Hackathons/NeuroLoop/data/datasets/pitt-ads-sentiment-50 \
  --json
```

For a CI-style distinct-ad gate, add `--strict-unique`. The normal check keeps
multi-label source reuse visible as a warning so the existing pack can still be
inspected without pretending it contains 50 independent source images.

At audit time, the external pack was 4.7 MB with 50 rows, 50 listed image
files, five rows per label, and all declared byte counts and SHA-256 digests
matching. It contains 49 unique source keys and 49 unique hashes: source
`10/171565.png` appears once under `angry` and once under `sad`, with hash
`8be37e48b47e93e8ee6816c3fc7d637a5d50d93dc04674b5890dc2e4b9960b96`. The
verifier reports this as `PASS_WITH_WARNINGS`; `--strict-unique` intentionally
fails it.

## Generate a new pack

The downloader selects rows in sorted source-key order, balances the ten
labels, refuses to overwrite an existing output directory, and now excludes a
source key already selected for another label:

```text
python3 scripts/download_pitt_ads_pilot.py \
  --output /path/to/new/pitt-ads-sentiment-50 \
  --count 50
```

This command downloads only the selected images, the source label legend, and
the manifest/README. It does not pull the large AdCumen archive. Keep a new
output path if a prior download exists; the script intentionally refuses to
overwrite it.

## Tests

The focused tests build temporary synthetic packs and never access the external
folder, download data, import models, or run inference:

```text
python3 -m pytest backend/tests/test_dataset_pilot.py -q
```
