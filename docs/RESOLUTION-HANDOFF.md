# Scientific and credential handoff

This is a checklist for information you can obtain. No messages were sent to
maintainers and no credentials were fetched or printed during the audit.

## Kragel: what to obtain

Local evidence: `models/brain_readouts/kragel2015/compatibility.json` and retained
sources in `models/brain_readouts/kragel2015/source`.

The downloaded hemisphere arrays contain 32,492 scalars each; TRIBE uses fsaverage5
with 10,242 vertices each. The local mesh-named files contain scalar arrays, not
the geometry/registration necessary to establish correspondence. A filename or
vertex count cannot identify a verified mapping.

Start with the [CANlab pattern description](https://github.com/canlab/Neuroimaging_Pattern_Masks/blob/master/Multivariate_signature_patterns/2015_Kragel_emotionClassificationBPLS/contents_description.md),
the [2015 paper DOI](https://doi.org/10.1093/scan/nsv032), and the
[CANlab repository issues](https://github.com/canlab/Neuroimaging_Pattern_Masks/issues).
CANlab describes these as bootstrap-z maps and gives a volume-based similarity
example; this does not establish a calibrated classifier for TRIBE predictions.

Ask the maintainers for:

1. Exact source surface/template identity, hemisphere ordering, medial-wall mask,
   and the coordinates, topology and registration spheres used for these GIFTIs.
2. A documented transform to fsaverage/fsaverage5, or the original volume template
   plus its verified transform/projection route. Include software versions and
   actual command lines. Do not substitute index resizing.
3. The intended scoring procedure: bootstrap-z visualization maps versus decoder
   weights, required normalization, mask, intercept, scaling and class ordering.
4. A known reference input with expected scores so our implementation can be checked.
5. Appropriate validation data and terms for testing transfer from predicted TRIBE
   cortical values to the measured-fMRI setting where the signatures were developed.

Suggested message to copy and send yourself:

> We are evaluating the seven Kragel 2015 emotion patterns in a local research
> application. Our target is TRIBE v2 fsaverage5 cortical predictions: 10,242
> vertices per hemisphere. The retained surface patterns have 32,492 values per
> hemisphere. Could you provide their exact source surface, medial-wall handling,
> registration geometry/transforms, intended scoring weights/procedure and a known
> reference example? We will not interpret arbitrary resampling or successful code
> execution as validation of transfer to synthetic cortical predictions.

Deliver the response/files under `models/brain_readouts/kragel2015/registration`
when available, with source URLs and hashes. This is a proposed destination, not
a claim that those files already exist. Acceptance requires alignment checks,
hemisphere/mask checks, reference-score reproduction and held-out transfer results.
Keep the decoder unavailable until that evidence exists.

## TSAM: why it is still experimental

Strict checkpoint loading and CPU execution are implemented. The eight-class order
follows the pinned source implementation: Anger, Contempt, Disgust, Fear, Happiness,
Neutral, Sadness, Surprise. Some model/dataset card text lists seven categories;
obtain confirmation against the precise checkpoint and split files before using
class labels as validated conclusions.

Sources:

- [Original implementation and contact](https://github.com/gmontana/DecodingViewerEmotions)
- [Checkpoint repository](https://huggingface.co/dnamodel/tsam-viewer-emotions)
- [AdCumen dataset and splits](https://huggingface.co/datasets/dnamodel/adcumen-viewer-emotions)
- [Paper](https://www.nature.com/articles/s41598-024-76968-9)

The original repository lists Giovanni Montana, `g.montana@warwick.ac.uk`, for
research questions, and Warwick Ventures, `ventures@warwick.ac.uk`, for commercial
use inquiries. Verify the linked current terms for your intended use. The paper
page could not be fetched in this audit; no new claims are based on its full text.

Ask for checkpoint-specific preprocessing and label mapping, expected predictions
on a known clip, the intended evaluation split, and clarification of inconsistent
card labels. Then reproduce the upstream test procedure; report balanced accuracy,
per-class recall/F1 and confusion matrices. Check whether clips from a source ad
cross splits before claiming generalization. Test on separately held-out material
representative of your actual use. Probability claims require separate calibration
and calibration-error evaluation; a softmax alone does not establish them.

Current numerical logits should remain signed, explicitly uncalibrated, and separate
from TRIBE/optimization. Registration is a Kragel problem; it does not solve TSAM's
validation problem. Dataset access and commercial permissions are also separate.

## Sponsor information to provide privately

Use [W&B authorization](https://wandb.ai/authorize) for your key. Put it in
`D:\NeuroLoop\.env`; provide the entity/project name and intended integration
scope without exposing the key. Follow [SPONSORS.md](SPONSORS.md).

For Weave: key, entity/project, permission to export the documented metadata.
For Inference: model access, credits and permission for a small remote planner
request that includes the brief. For ARIA: account access, Launch queue, agent and
compute choice, plus implementation of the missing job/result bridge. No CoreWeave
credentials are necessary while compute remains local.
