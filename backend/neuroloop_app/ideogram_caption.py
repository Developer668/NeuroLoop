"""Ideogram's structured caption contract; no inferred or synthetic media."""
import json

PLAN_INSTRUCTION = """
The image generator is Ideogram 4. Each CandidatePlan.prompt MUST be a JSON-encoded
string containing its actual structured image caption, not a prose prompt wrapped
inside one object description. Use these keys in this exact order:
high_level_description: a one- or two-sentence visual summary;
style_description: keys aesthetics, lighting, medium, art_style (for graphic design
or illustration), then optional color_palette. For photography use keys aesthetics,
lighting, photo, medium instead. Choose the medium from the brief, never hardcode photography.
compositional_deconstruction: keys background (specific visual setting), elements.
Each element describes one actual object or one exact text string. Object keys are
type='obj', optional bbox, desc, optional color_palette. Text keys are type='text',
optional bbox, text (literal approved copy), desc, optional color_palette.
bbox is optional [y_min,x_min,y_max,x_max], integers 0..1000. Palette entries are
uppercase #RRGGBB. Preserve key ordering. Describe the desired image and spatial
relationships concretely; keep policy explanations and exclusions in EditIntent,
not as depicted elements. Render no unapproved copy. The JSON caption is part of
the exact plan TypeSafe reviews before execution; do not add a second unreviewed
creative rewrite during generation.
Set CandidatePlan.parameters to {}: the operator-selected Ideogram sampling preset
is fixed, and generic guidance_scale/num_inference_steps/strength controls are not
supported by this adapter. For future image alternatives, the planner may inspect
parent evidence and pixels, but Ideogram receives only the new JSON caption. Never
promise direct editing or media conditioning. Preserve lineage in parent_creative_id.
"""


def caption_json(prompt):
    """Fail before GPU work if the reviewed prompt is not a structured caption."""
    caption = json.loads(prompt)
    if not isinstance(caption, dict) or "compositional_deconstruction" not in caption:
        raise ValueError("Ideogram requires its structured JSON caption")
    if set(caption) - {"high_level_description", "style_description", "compositional_deconstruction"}:
        raise ValueError("Unknown Ideogram caption fields")
    composition = caption["compositional_deconstruction"]
    if not isinstance(composition, dict) or not isinstance(composition.get("background"), str) or not isinstance(composition.get("elements"), list):
        raise ValueError("Ideogram requires background and element descriptions")
    if not composition["elements"]:
        raise ValueError("Ideogram caption has no visual elements")
    for element in composition["elements"]:
        if not isinstance(element, dict) or element.get("type") not in {"obj", "text"} or not isinstance(element.get("desc"), str):
            raise ValueError("Invalid Ideogram element")
        if element["type"] == "text" and not isinstance(element.get("text"), str):
            raise ValueError("Text elements require literal copy")
    return json.dumps(caption, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
