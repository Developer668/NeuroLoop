# MeowStore generation diagnosis

The full automatic loop is **not verified**. Latest run: `8ccbf060-eea4-4458-89b7-17dbf48eb83c` in campaign `07a7bfdc-72eb-4c0c-802d-0dcb0056b4db`.

The actual GLM plan completed with supported empty sampling parameters and exact locked requirement identifiers. TypeSafe returned APPROVE with confidence 0.48, below the unchanged 0.70 run threshold. The engine stopped before creating a generation job. This run has no generated advertisement or child revision. Earlier failed attempts are preserved.

## Implemented and verified

- Campaign pages restore the latest saved run on initial loading. Choosing new-run inputs remains possible without the polling timer overriding that choice.
- Progress states explicitly distinguish completed planning jobs from generated media and explain plan-review stops.
- The run displays the actual agent plan and no longer says it is waiting for a model after a terminal planning stop.
- Publish Ads labels original uploads separately from model output.
- Brain & emotion fetches evidence for the selected campaign; MeowStore no longer displays another campaign's video or predictions.
- Planner output validation rejects invented sampling controls. The deployed generators retain their operator-owned presets.
- The hosted research adapter was updated to supply the subprocess import paths and the diagnostic cell was corrected to unpack the registry output and provenance.

## Real research execution

Separate campaign `f1265505-af1b-4d48-b306-4fdf5bcad7bf`, generated video `f2227383-495e-4039-802f-a354084c5a0e`, SHA256 `2e147002ad965efaaa1ac9405f51de99c94a0eee106312f855abb4a5014c6627`:

- TSAM receipt `5091e142-50ad-4953-bff3-5f0038928928`: SUCCEEDED, actual audiovisual inference.
- Quantized TRIBE receipt `e2f7c1f9-cb80-4651-a95a-0da6981fbec2`: SUCCEEDED, 6 × 20,484 cortical values.
- Cortical artifact `2a7b6d29-c0a4-4017-8531-500de74884ea` is downloadable in Brain & emotion.
- Browser inspection confirmed both receipts and their W&B artifact backups as VERIFIED. These are research predictions on the NeuroLoop video, not MeowStore results or measured viewer responses.
- Outcome telemetry was exported and remote verification completed after these executions.

Validation: frontend production build and TypeScript passed; 20 planner/model contract tests passed after the latest backend changes. Browser inspection confirmed run restoration, plan visibility, zero MeowStore receipts, and real research receipts in the appropriate campaign.

Detailed persisted evidence: `artifacts/verification/meowstore-generation-diagnosis.json`.
