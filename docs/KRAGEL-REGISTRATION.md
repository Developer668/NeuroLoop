# Kragel registration and scoring audit

Status: **diagnostic projection available; registration and TRIBE transfer are not validated.**

The seven published Kragel volumes are present. This is separate from whether their coordinate systems and trained scoring procedure match TRIBE output. New results explicitly report `registration_verified`, `decision_eligible: false`, and `cannot_be_used_for_decisions: true`.

## What was found

The downloaded pial/white geometry comes from Nilearn 0.12.1's fsaverage5 dataset. All four files contain 10,242 vertices per hemisphere. The GIFTI coordinates identify a FreeSurfer fsaverage5 surface source, with an unknown-to-Talairach coordinate-system label and identity transform. That metadata does **not** prove these coordinates are MNI152 volume world coordinates.

The Kragel files are NIfTI pairs despite their `.hdr`/`.img` extensions. The inspected volume has 41 x 49 x 35 voxels, approximately 3.8 mm spacing, LAS orientation, and an aligned sform/qform. The published companion surface names reference `Template_T1_IXI555_MNI152_GS`. An aligned header alone does not identify the precise spatial normalization chain.

Previously the adapter used `inverse(volume_affine) @ surface_RAS`. That converts coordinates into voxel indices only if the two world coordinate systems already match. It is not a spatial registration algorithm.

## Why a generic affine was not silently applied

[FreeSurfer's official coordinate documentation](https://surfer.nmr.mgh.harvard.edu/fswiki/CoordinateSystems) gives the surface-to-MNI305 chain as `TalXFM @ Norig @ inverse(Torig)`, and separately supplies this MNI305-to-MNI152 affine:

```text
 0.9975 -0.0073  0.0176 -0.0429
 0.0146  1.0009 -0.0024  1.5496
-0.0130 -0.0093  0.9971  1.1840
 0       0       0       1
```

The latter matrix is only one part of the required chain. The exact-source `orig.mgz` and `talairach.xfm` needed to establish the preceding chain are not present in this installation. Substituting files from an unrelated FreeSurfer release would not establish a match to our actual mesh. In addition, a generic MNI affine is not evidence that the IXI555 normalization used for these maps matches the target template precisely.

[Wu et al.'s original mapping study](https://pmc.ncbi.nlm.nih.gov/articles/PMC6239990/) evaluates nonlinear registration fusion between MNI and FreeSurfer coordinates and explains the limitations of simpler mappings. A validated registration-fusion mapping at the correct fsaverage resolution is another possible route; it must have documented template compatibility and vertex correspondence.

## Implemented contract

`backend/neuroloop/kragel.py` now records registration separately from asset readiness and includes registration in the projection-cache identity. Without a receipt, identity mapping remains available only as an explicitly unverified diagnostic. An invalid receipt fails projection instead of silently falling back.

A reviewed complete affine can be supplied at `data/geometry/kragel-registration.json` with:

- `surface_to_volume_world`: finite, invertible homogeneous 4 x 4 matrix for the complete chain.
- `geometry_sha256`: exact filenames/hashes for all four pial and white surfaces.
- `volume_sha256`: exact filenames/hashes for all fourteen signature header/data files.
- `source_space`, `target_space`, `method`, `reference`, `reviewed_by`.
- `validation`: `spatial_alignment_passed`, `hemisphere_order_passed`, and `report_sha256` identifying the reviewed alignment report.

The adapter then uses `inverse(volume_affine) @ surface_to_volume_world @ surface_RAS`. Matrix validity and matching hashes are necessary technical checks, not automated scientific proof. A review receipt is an externally supplied assertion and must correspond to actual reviewed evidence. Even a reviewed registration remains **ineligible for optimization decisions** until transfer and scoring validation are completed.

## Actual CPU comparison

The seven local volumes were sampled independently with SciPy `ndimage.map_coordinates(order=1)` at the same five cortical ribbon depths. There were 19,853 mutually finite vertices per pattern. Across patterns, maximum absolute differences were 0.0000881 to 0.0001795; RMS differences were 0.00000292 to 0.00000380. The adapter's finite-corner renormalization retains some vertices that SciPy's direct NaN propagation excludes; therefore support is not identical. The adapter reported approximately 99.91% finite coverage, which is **not** a registration-quality score.

Full numerical results and exact asset hashes are saved locally in `artifacts/kragel-interpolation-audit.json`. This comparison verifies interpolation consistency on available samples only. It does not validate anatomical alignment or emotion scoring. No GPU run was performed.

Three registration-contract tests cover unverified defaults, rejecting singular matrices, exact-asset binding, and keeping transfer eligibility false even with a registration receipt. Together with the scientific response-contract suite, 16 tests passed.

## What is still needed

1. Exact-source surface-to-MNI chain or validated registration-fusion mapping, plus confirmation of the published volumes' template space.
2. Anatomical overlay/landmark inspection on the corresponding template; hemisphere and vertex-order checks; reviewer report bound to these asset hashes.
3. Reference scoring reproduction from the original author method using an authorized measured-fMRI example and expected scores. The current adapter computes normalized cortical spatial similarity to bootstrap-z maps, not the original validated whole-brain classifier. Missing subcortical voxels, masking, preprocessing, and trained scoring weights must be addressed rather than assumed equivalent.
4. Independent held-out stimuli with measured fMRI and emotion labels, evaluated through a predefined protocol. Training/test separation, transfer metrics, uncertainty, calibration and failure cases must be reported before emotion or optimization claims.

The [CANlab pattern documentation](https://github.com/canlab/Neuroimaging_Pattern_Masks) and [Kragel and LaBar's original article](https://doi.org/10.1093/scan/nsv032) are the reference starting points. Downloaded assets and strict shape checks cannot replace these remaining requirements.
