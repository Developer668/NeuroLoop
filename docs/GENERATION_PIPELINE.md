# Bounded multimodal generation

Defaults: 2 initial candidates; beam width 2; 2 children per retained parent; 3 rounds including round zero; at most 10 candidates, 80 model calls, 3600 serialized-model seconds and 7200 elapsed seconds. Limits are typed and enforceable. Currency caps require declared conservative quotes; an unknown price is not zero.

GenerationContext gives the real prompt, edit intent, current_media (None only initially), original LocalAsset references, output_dir, cancellation callback and remaining time. LocalAsset paths exist only inside the notebook after authenticated transfer and SHA verification. They are never raw D: paths in a distributed API request.

The adapter must return a real file inside the provided output directory. The worker journals a generated receipt before upload and a result receipt before acknowledgement. On ambiguous lost generation leases, the app stops at NEEDS_ATTENTION/UNCERTAIN. It can accept a valid late original receipt, but does not blindly generate again. Explicit uncertainty acknowledgement can incur another generation cost; no UI silently supplies that acknowledgement.

Post-generation validation checks actual bytes, media limits and artifact ownership. Regeneration never claims pixel-isolated edits. New copies, nonselected candidates and failed records remain inspectable.
