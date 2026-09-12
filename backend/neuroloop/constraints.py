"""Metadata-backed creative constraints.

Flattened pixels are not treated as proof of copy, logos, or objects. The
checks below use exact values in editable layer manifests or declared asset
metadata. Missing proof for a locked property is a failed ``unverifiable``
check, never an implicit pass.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from typing import Any


class ConstraintError(ValueError):
    """The declared constraint contract is malformed or unsupported."""


class ConstraintViolation(ConstraintError):
    """A candidate did not satisfy a valid constraint contract."""

    def __init__(self, report: "ConstraintReport") -> None:
        self.report = report
        super().__init__(report.message)


MISSING = object()


def _first(values: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in values:
            return values[name]
    return default


def _as_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConstraintError(f"{name} must be boolean")
    return value


def _as_number(value: Any, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConstraintError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ConstraintError(f"{name} must be a finite number >= {minimum:g}")
    return number


def _as_strings(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    values = (value,) if isinstance(value, str) else value
    if not isinstance(values, Sequence) or isinstance(values, (bytes, bytearray, str)):
        raise ConstraintError(f"{name} must be a string or list of strings")
    result = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise ConstraintError(f"{name} must contain non-empty strings")
    return result


def _as_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConstraintError(f"{name} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _as_text_mapping(value: Any, name: str) -> dict[str, str]:
    result = _as_mapping(value, name)
    if any(not key.strip() or not isinstance(item, str) or not item for key, item in result.items()):
        raise ConstraintError(f"{name} must map non-empty layer ids to text")
    return {key: item for key, item in result.items()}


def _details(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        details = value.get("details")
        result = dict(details) if isinstance(details, Mapping) else dict(value)
        if isinstance(details, Mapping):
            result.update({key: item for key, item in value.items() if key != "details"})
        return result
    details = getattr(value, "details", None) or getattr(value, "metadata", None)
    if isinstance(details, Mapping):
        return dict(details)
    raise ConstraintError("Candidate metadata is required for creative constraint checks")


def _at(values: Mapping[str, Any], path: str) -> Any:
    current: Any = values
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return MISSING
        current = current[part]
    return current


def _normal_text(value: str) -> str:
    return " ".join(value.split())


def _ratio(values: Mapping[str, Any]) -> float | None:
    width, height = values.get("width"), values.get("height")
    if not isinstance(width, (int, float)) or isinstance(width, bool) or not isinstance(height, (int, float)) or isinstance(height, bool) or width <= 0 or height <= 0:
        return None
    ratio = float(width) / float(height)
    return ratio if math.isfinite(ratio) else None


def _audio_count(values: Mapping[str, Any]) -> int | None:
    count = values.get("audio_streams", values.get("audio_stream_count"))
    if isinstance(count, Sequence) and not isinstance(count, (str, bytes, bytearray)):
        return len(count)
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        return count
    if values.get("has_audio") is True:
        return 1
    if values.get("has_audio") is False:
        return 0
    return None


def _layer_text(layer: Any) -> tuple[str | None, str | None]:
    if isinstance(layer, str):
        return None, layer
    if not isinstance(layer, Mapping):
        return None, None
    kind = str(layer.get("kind") or layer.get("type") or "").lower()
    text = next((layer[key] for key in ("text", "content", "value") if isinstance(layer.get(key), str)), None)
    if text is None or kind and kind not in {"text", "copy", "headline", "subline", "claim", "product", "caption"}:
        return None, None
    return str(layer.get("id") or layer.get("layer_id") or layer.get("name")) if layer.get("id", layer.get("layer_id", layer.get("name"))) is not None else None, text


def editable_text_layers(value: Any) -> dict[str, str]:
    """Extract declared editable text only; no OCR or visual inference."""
    metadata = _details(value)
    result: dict[str, str] = {}
    ordinal = 0

    def add(key: Any, text: Any) -> None:
        nonlocal ordinal
        if isinstance(text, str) and text:
            result[str(key) if key is not None else f"text_{ordinal}"] = text
            ordinal += 1

    def add_many(items: Any) -> None:
        if isinstance(items, Mapping):
            for key, item in items.items():
                layer_key, text = _layer_text(item)
                add(key, item if isinstance(item, str) else text)
        elif isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
            for item in items:
                layer_key, text = _layer_text(item)
                add(layer_key, text)
        elif isinstance(items, str):
            add(None, items)

    for key in ("text_layers", "editable_text_layers", "copy_layers", "editable_copy"):
        if key in metadata:
            add_many(metadata[key])
    for key in ("layers", "editable_layers"):
        if isinstance(metadata.get(key), (Mapping, list, tuple)):
            add_many(metadata[key])
    composition = metadata.get("composition")
    if isinstance(composition, Mapping):
        for key in ("text_layers", "editable_text_layers", "copy_layers", "layers"):
            if key in composition:
                add_many(composition[key])
        for key in ("headline", "subline", "copy", "claims_text", "product"):
            add(key, composition.get(key))
    for key in ("headline", "subline", "copy", "claims_text"):
        add(key, metadata.get(key))
    if isinstance(metadata.get("preview_text"), str) and "characters" in metadata:
        add("source_text", metadata["preview_text"])
    return result


def _logo_entries(value: Any) -> list[dict[str, Any]]:
    metadata = _details(value)
    result: list[dict[str, Any]] = []

    def add(item: Any) -> None:
        if isinstance(item, str):
            result.append({"value": item})
        elif isinstance(item, Mapping):
            result.append(dict(item))

    for key in ("logo", "logo_asset", "logos", "logo_assets"):
        items = metadata.get(key)
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
            for item in items:
                add(item)
        elif items is not None:
            add(items)
    for key in ("logo_asset_id", "logo_sha256", "logo_hash"):
        if metadata.get(key) is not None:
            add({key: metadata[key]})
    for key in ("layers", "editable_layers"):
        items = metadata.get(key)
        if isinstance(items, Mapping):
            items = list(items.values())
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
            for item in items:
                if isinstance(item, Mapping) and any("logo" in str(item.get(name, "")).lower() for name in ("kind", "type", "role")):
                    add(item)
    composition = metadata.get("composition")
    if isinstance(composition, Mapping):
        result.extend(_logo_entries(composition))
    return result


def declared_objects(value: Any) -> set[str]:
    """Read declared object labels only; never guess from pixels."""
    metadata = _details(value)
    values = [metadata[key] for key in ("declared_objects", "objects", "object_tags", "object_labels") if key in metadata]
    composition = metadata.get("composition")
    if isinstance(composition, Mapping):
        values.extend(composition[key] for key in ("declared_objects", "objects", "object_tags", "object_labels") if key in composition)
    result: set[str] = set()
    for value in values:
        if isinstance(value, Mapping):
            result.update(str(key).strip() for key, item in value.items() if item is not False and item is not None)
            result.update(str(item).strip() for item in value.values() if isinstance(item, str) and item.strip())
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                token = (item.get("name") or item.get("label") or item.get("id")) if isinstance(item, Mapping) else item
                if isinstance(token, str) and token.strip():
                    result.add(token.strip())
        elif isinstance(value, str) and value.strip():
            result.add(value.strip())
    return result


@dataclass(frozen=True)
class ConstraintReport:
    passed: bool
    checks: tuple[dict[str, Any], ...] = ()
    violations: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "passed" if self.passed else "rejected"

    @property
    def reasons(self) -> tuple[str, ...]:
        return self.violations

    @property
    def message(self) -> str:
        return "All declared creative constraints passed." if self.passed else "Creative constraint gate rejected the candidate: " + "; ".join(self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "status": self.status, "checks": list(self.checks), "violations": list(self.violations), "reasons": list(self.violations), "evidence": dict(self.evidence), "message": self.message}

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


@dataclass(frozen=True)
class CreativeConstraints:
    """A frozen set of verifiable requirements.

    ``preserve_*`` and ``locked_properties`` compare a candidate with a
    baseline. ``required_*`` and ``expected_*`` compare directly with a
    declared value. ``required_objects`` means declared object metadata only.
    """

    product: Any = None
    required_copy: tuple[str, ...] = ()
    claims: tuple[str, ...] = ()
    required_copy_by_layer: dict[str, str] = field(default_factory=dict)
    claims_by_layer: dict[str, str] = field(default_factory=dict)
    preserve_text: bool = False
    locked_copy: bool = False
    required_logo: Any = None
    preserve_logo: bool = False
    expected_duration: float | None = None
    preserve_duration: bool = False
    duration_tolerance: float = 0.2
    expected_width: int | None = None
    expected_height: int | None = None
    preserve_dimensions: bool = False
    expected_aspect: str | float | None = None
    preserve_aspect: bool = False
    aspect_tolerance: float = 0.01
    require_audio: bool = False
    preserve_audio: bool = False
    require_audio_signal: bool = False
    required_audio_streams: int | None = None
    required_objects: tuple[str, ...] = ()
    immutable_properties: dict[str, Any] = field(default_factory=dict)
    locked_properties: tuple[str, ...] = ()
    max_filter_edits: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_copy", _as_strings(self.required_copy, "required_copy"))
        object.__setattr__(self, "claims", _as_strings(self.claims, "claims"))
        object.__setattr__(self, "required_objects", _as_strings(self.required_objects, "required_objects"))
        object.__setattr__(self, "required_copy_by_layer", _as_text_mapping(self.required_copy_by_layer, "required_copy_by_layer"))
        object.__setattr__(self, "claims_by_layer", _as_text_mapping(self.claims_by_layer, "claims_by_layer"))
        object.__setattr__(self, "immutable_properties", _as_mapping(self.immutable_properties, "immutable_properties"))
        for name in ("preserve_text", "locked_copy", "preserve_logo", "preserve_duration", "preserve_dimensions", "preserve_aspect", "require_audio", "preserve_audio", "require_audio_signal"):
            _as_bool(getattr(self, name), name)
        object.__setattr__(self, "duration_tolerance", _as_number(self.duration_tolerance, "duration_tolerance"))
        object.__setattr__(self, "aspect_tolerance", _as_number(self.aspect_tolerance, "aspect_tolerance"))
        if self.expected_duration is not None:
            object.__setattr__(self, "expected_duration", _as_number(self.expected_duration, "expected_duration"))
        for name in ("expected_width", "expected_height"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
                raise ConstraintError(f"{name} must be a positive integer")
        if self.required_audio_streams is not None and (isinstance(self.required_audio_streams, bool) or not isinstance(self.required_audio_streams, int) or self.required_audio_streams <= 0):
            raise ConstraintError("required_audio_streams must be a positive integer")
        if self.max_filter_edits is not None and (isinstance(self.max_filter_edits, bool) or not isinstance(self.max_filter_edits, int) or not 0 <= self.max_filter_edits <= 4):
            raise ConstraintError("max_filter_edits must be an integer between 0 and 4")
        if self.expected_aspect is not None and not isinstance(self.expected_aspect, str):
            _as_number(self.expected_aspect, "expected_aspect", minimum=0.000001)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | "CreativeConstraints" | None) -> "CreativeConstraints":
        if values is None or isinstance(values, cls):
            return values if isinstance(values, cls) else cls()
        if not isinstance(values, Mapping):
            raise ConstraintError("Creative constraints must be a mapping")
        supported = {"product", "required_product", "product_name", "required_copy", "required_copy_text", "copy", "copy_by_layer", "claims", "claims_text", "claims_by_layer", "preserve_text", "preserve_copy", "locked_copy", "required_logo", "logo", "logo_asset", "logo_asset_id", "logo_sha256", "logo_hash", "preserve_logo", "expected_duration", "duration", "duration_seconds", "preserve_duration", "duration_tolerance", "expected_width", "width", "expected_height", "height", "dimensions", "preserve_dimensions", "expected_aspect", "aspect", "aspect_ratio", "preserve_aspect", "aspect_tolerance", "require_audio", "required_audio", "preserve_audio", "require_audio_signal", "audio_must_be_non_silent", "required_audio_streams", "audio_streams", "required_objects", "objects", "immutable_properties", "immutable", "user_locked", "locked_properties", "max_filter_edits"}
        unsupported = sorted(set(values) - supported)
        if unsupported:
            raise ConstraintError("Unsupported constraints: " + ", ".join(unsupported))
        copy_value, copy_by_layer = _first(values, "required_copy", "required_copy_text", "copy"), values.get("copy_by_layer")
        if isinstance(copy_value, Mapping):
            copy_by_layer, copy_value = copy_value, None
        claims_value, claims_by_layer = _first(values, "claims", "claims_text"), values.get("claims_by_layer")
        if isinstance(claims_value, Mapping):
            claims_by_layer, claims_value = claims_value, None
        dimensions = values.get("dimensions")
        width, height = _first(values, "expected_width", "width"), _first(values, "expected_height", "height")
        if dimensions is not None:
            if not isinstance(dimensions, Sequence) or isinstance(dimensions, (str, bytes, bytearray)) or len(dimensions) != 2:
                raise ConstraintError("dimensions must be [width, height]")
            width = dimensions[0] if width is None else width
            height = dimensions[1] if height is None else height
        immutable = _as_mapping(_first(values, "immutable_properties", "immutable"), "immutable_properties")
        user_locked = values.get("user_locked")
        if isinstance(user_locked, Mapping):
            immutable.update(_as_mapping(user_locked, "user_locked"))
        locked = values.get("locked_properties", user_locked if user_locked is not None and not isinstance(user_locked, Mapping) else ())
        if isinstance(locked, str):
            locked = (locked,)
        if not isinstance(locked, Sequence) or isinstance(locked, (bytes, bytearray)) or any(not isinstance(item, str) or not item.strip() for item in locked):
            raise ConstraintError("locked_properties must be a property path or list of paths")
        logo = _first(values, "required_logo", "logo", "logo_asset")
        if logo is None and (values.get("logo_asset_id") is not None or values.get("logo_sha256", values.get("logo_hash")) is not None):
            logo = {"asset_id": values.get("logo_asset_id"), "sha256": values.get("logo_sha256", values.get("logo_hash"))}
            logo = {key: item for key, item in logo.items() if item is not None}
        return cls(product=_first(values, "product", "required_product", "product_name"), required_copy=_as_strings(copy_value, "required_copy"), claims=_as_strings(claims_value, "claims"), required_copy_by_layer=_as_text_mapping(copy_by_layer, "copy_by_layer"), claims_by_layer=_as_text_mapping(claims_by_layer, "claims_by_layer"), preserve_text=_first(values, "preserve_text", "preserve_copy", default=False), locked_copy=values.get("locked_copy", False), required_logo=logo, preserve_logo=values.get("preserve_logo", False), expected_duration=_first(values, "expected_duration", "duration", "duration_seconds"), preserve_duration=values.get("preserve_duration", False), duration_tolerance=values.get("duration_tolerance", 0.2), expected_width=width, expected_height=height, preserve_dimensions=values.get("preserve_dimensions", False), expected_aspect=_first(values, "expected_aspect", "aspect_ratio", "aspect"), preserve_aspect=values.get("preserve_aspect", False), aspect_tolerance=values.get("aspect_tolerance", 0.01), require_audio=_first(values, "require_audio", "required_audio", default=False), preserve_audio=values.get("preserve_audio", False), require_audio_signal=_first(values, "require_audio_signal", "audio_must_be_non_silent", default=False), required_audio_streams=_first(values, "required_audio_streams", "audio_streams"), required_objects=_as_strings(_first(values, "required_objects", "objects"), "required_objects"), immutable_properties=immutable, locked_properties=tuple(locked), max_filter_edits=values.get("max_filter_edits"))

    def to_dict(self) -> dict[str, Any]:
        return {"product": self.product, "required_copy": list(self.required_copy), "claims": list(self.claims), "required_copy_by_layer": dict(self.required_copy_by_layer), "claims_by_layer": dict(self.claims_by_layer), "preserve_text": self.preserve_text or self.locked_copy, "locked_copy": self.locked_copy, "required_logo": self.required_logo, "preserve_logo": self.preserve_logo, "expected_duration": self.expected_duration, "preserve_duration": self.preserve_duration, "duration_tolerance": self.duration_tolerance, "expected_width": self.expected_width, "expected_height": self.expected_height, "preserve_dimensions": self.preserve_dimensions, "expected_aspect": self.expected_aspect, "preserve_aspect": self.preserve_aspect, "aspect_tolerance": self.aspect_tolerance, "require_audio": self.require_audio, "preserve_audio": self.preserve_audio, "require_audio_signal": self.require_audio_signal, "required_audio_streams": self.required_audio_streams, "required_objects": list(self.required_objects), "immutable_properties": dict(self.immutable_properties), "locked_properties": list(self.locked_properties), "max_filter_edits": self.max_filter_edits}

    def quality_expectation(self, baseline: Any = None) -> dict[str, Any]:
        """Return cheap file-level checks implied by this contract."""
        baseline = _details(baseline) if baseline is not None else {}
        result: dict[str, Any] = {"duration_tolerance": self.duration_tolerance, "aspect_tolerance": self.aspect_tolerance, "require_audio": self.require_audio or self.preserve_audio or self.required_audio_streams is not None, "require_audio_signal": self.require_audio_signal}
        duration = self.expected_duration if self.expected_duration is not None else baseline.get("duration") if self.preserve_duration else None
        width = self.expected_width if self.expected_width is not None else baseline.get("width") if self.preserve_dimensions else None
        height = self.expected_height if self.expected_height is not None else baseline.get("height") if self.preserve_dimensions else None
        aspect = self.expected_aspect if self.expected_aspect is not None else _ratio(baseline) if self.preserve_aspect else None
        streams = self.required_audio_streams if self.required_audio_streams is not None else _audio_count(baseline) if self.preserve_audio else None
        if duration is not None: result["expected_duration"] = duration
        if width is not None: result["expected_width"] = width
        if height is not None: result["expected_height"] = height
        if aspect is not None: result["expected_aspect"] = aspect
        if streams is not None: result["required_audio_streams"] = streams
        return result

    def check(self, candidate: Any, baseline: Any = None) -> ConstraintReport:
        candidate = _details(candidate)
        baseline = _details(baseline) if baseline is not None else None
        checks: list[dict[str, Any]] = []
        violations: list[str] = []

        def add(name: str, passed: bool, code: str, message: str, expected: Any = None, actual: Any = None, *, verification: str = "declared_metadata", status: str | None = None) -> None:
            checks.append({"name": name, "passed": passed, "status": status or ("passed" if passed else "failed"), "code": code, "expected": expected, "actual": actual, "message": message, "verification": verification})
            if not passed:
                violations.append(message)

        texts = editable_text_layers(candidate)
        joined = _normal_text("\n".join(texts.values()))
        if self.product is not None:
            composition = candidate.get("composition")
            actual = _first(candidate, "product", "product_name", "product_id", default=_first(composition, "product") if isinstance(composition, Mapping) else MISSING)
            add("product", actual is not MISSING and actual == self.product, "product_mismatch" if actual is not MISSING else "product_unverifiable", f"Product metadata must equal {self.product!r}; candidate has {None if actual is MISSING else actual!r}.", self.product, None if actual is MISSING else actual, status=None if actual is not MISSING else "unverifiable")
        for layer, expected in self.required_copy_by_layer.items():
            actual = texts.get(layer, MISSING)
            passed = actual is not MISSING and _normal_text(actual) == _normal_text(expected)
            add(f"required_copy.{layer}", passed, "copy_mismatch" if actual is not MISSING else "copy_unverifiable", f"Required copy layer {layer!r} is absent or changed; OCR/vision inference is not used.", expected, None if actual is MISSING else actual, status=None if actual is not MISSING else "unverifiable")
        for index, expected in enumerate(self.required_copy):
            passed = bool(texts) and _normal_text(expected) in joined
            add(f"required_copy[{index}]", passed, "copy_mismatch" if texts else "copy_unverifiable", f"Required copy {expected!r} is absent from declared editable text layers; OCR/vision inference is not used.", expected, list(texts.values()) or None, status=None if texts else "unverifiable")
        for layer, expected in self.claims_by_layer.items():
            actual = texts.get(layer, MISSING)
            passed = actual is not MISSING and _normal_text(actual) == _normal_text(expected)
            add(f"claims.{layer}", passed, "claims_mismatch" if actual is not MISSING else "claims_unverifiable", f"Claim layer {layer!r} is absent or changed; claims are checked only from declared text layers.", expected, None if actual is MISSING else actual, status=None if actual is not MISSING else "unverifiable")
        for index, expected in enumerate(self.claims):
            passed = bool(texts) and _normal_text(expected) in joined
            add(f"claims[{index}]", passed, "claims_mismatch" if texts else "claims_unverifiable", f"Claim text {expected!r} is absent from declared editable text layers; claims are not inferred from pixels.", expected, list(texts.values()) or None, status=None if texts else "unverifiable")
        if self.preserve_text or self.locked_copy:
            before = editable_text_layers(baseline) if baseline is not None else {}
            add("preserve_text", bool(before) and before == texts, "copy_mismatch" if texts else "copy_unverifiable", "Locked text preservation requires matching declared editable text layers in baseline and candidate.", before or None, texts or None, verification="declared_editable_layers", status=None if before and texts else "unverifiable")

        if self.required_logo is not None or self.preserve_logo:
            after = _logo_entries(candidate)
            def identities(items: list[dict[str, Any]]) -> list[list[str]]:
                keys = ("value", "id", "layer_id", "asset_id", "sha256", "hash", "logo_asset_id", "logo_sha256", "logo_hash", "name")
                return sorted([sorted({str(item[key]) for key in keys if item.get(key) is not None}) for item in items])
            if self.required_logo is not None:
                expected_ids = {str(item) for item in self.required_logo.values()} if isinstance(self.required_logo, Mapping) else {str(self.required_logo)}
                actual_ids = identities(after)
                add("required_logo", any(expected_ids <= set(item) for item in actual_ids), "logo_mismatch" if after else "logo_unverifiable", "Required logo identity is absent or changed; pixel matching is not used.", self.required_logo, actual_ids or None, verification="declared_logo_asset_identity", status=None if after else "unverifiable")
            before = _logo_entries(baseline) if baseline is not None else []
            if self.preserve_logo:
                passed = bool(before) and bool(after) and identities(before) == identities(after)
                add("preserve_logo", passed, "logo_mismatch" if after else "logo_unverifiable", "Locked logo preservation requires matching declared baseline/candidate logo identities; pixel matching is not used.", identities(before) or None, identities(after) or None, verification="declared_logo_asset_identity", status=None if before and after else "unverifiable")

        if self.required_objects:
            actual = declared_objects(candidate)
            missing = sorted(set(self.required_objects) - actual)
            add("required_objects", not missing, "object_not_declared" if actual else "objects_unverifiable", f"Required objects are not declared in metadata: {', '.join(missing)}. Vision inference is intentionally not used." if missing else "Required objects are explicitly declared; no visual inference was performed.", list(self.required_objects), sorted(actual) or None, verification="declared_object_metadata_only", status=None if actual else "unverifiable")

        duration = self.expected_duration if self.expected_duration is not None else baseline.get("duration", MISSING) if self.preserve_duration and baseline is not None else None
        if duration is not None and duration is not MISSING:
            actual = candidate.get("duration", MISSING)
            valid = isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(float(actual))
            passed = valid and abs(float(actual) - float(duration)) <= self.duration_tolerance
            add("duration", passed, "duration_mismatch" if valid else "duration_unverifiable", f"Candidate duration {None if actual is MISSING else actual!r}s is outside the allowed {self.duration_tolerance:g}s tolerance from {duration!r}s." if valid else "Locked duration cannot be checked because candidate metadata has no finite duration.", {"seconds": duration, "tolerance": self.duration_tolerance}, None if actual is MISSING else actual, status=None if valid else "unverifiable")
        width = self.expected_width if self.expected_width is not None else baseline.get("width", MISSING) if self.preserve_dimensions and baseline is not None else None
        height = self.expected_height if self.expected_height is not None else baseline.get("height", MISSING) if self.preserve_dimensions and baseline is not None else None
        if width is not None or height is not None:
            actual_width, actual_height = candidate.get("width", MISSING), candidate.get("height", MISSING)
            present = actual_width is not MISSING and actual_height is not MISSING
            passed = present and (width is None or actual_width == width) and (height is None or actual_height == height)
            add("dimensions", passed, "dimensions_mismatch" if present else "dimensions_unverifiable", "Candidate dimensions do not match the locked dimensions." if present else "Locked dimensions cannot be checked because candidate dimensions are missing.", {"width": width, "height": height}, None if not present else {"width": actual_width, "height": actual_height}, status=None if present else "unverifiable")
        aspect = self.expected_aspect if self.expected_aspect is not None else _ratio(baseline or {}) if self.preserve_aspect else None
        if aspect is not None:
            actual = _ratio(candidate)
            passed = False
            if actual is not None and isinstance(aspect, str) and aspect.lower() in {"landscape", "portrait", "square"}:
                passed = (aspect.lower() == "landscape" and actual > 1) or (aspect.lower() == "portrait" and actual < 1) or (aspect.lower() == "square" and abs(actual - 1) <= self.aspect_tolerance)
            elif actual is not None:
                try:
                    numeric = float(aspect.split(":")[0]) / float(aspect.split(":")[1]) if isinstance(aspect, str) and ":" in aspect else float(aspect)
                    passed = numeric > 0 and abs(actual - numeric) <= self.aspect_tolerance
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
            add("aspect", passed, "aspect_mismatch" if actual is not None else "aspect_unverifiable", f"Candidate aspect {actual!r} does not match locked aspect {aspect!r}." if actual is not None else "Locked aspect cannot be checked because candidate dimensions are missing.", {"aspect": aspect, "tolerance": self.aspect_tolerance}, actual, status=None if actual is not None else "unverifiable")
        if self.require_audio or self.preserve_audio or self.required_audio_streams is not None:
            actual = _audio_count(candidate)
            baseline_count = _audio_count(baseline) if baseline is not None else None
            needed = self.required_audio_streams or (baseline_count if self.preserve_audio and baseline_count is not None else 1)
            passed = actual is not None and actual >= needed and (not self.preserve_audio or baseline_count is None or actual == baseline_count)
            add("audio_streams", passed, "audio_stream_mismatch" if actual is not None else "audio_stream_unverifiable", "Candidate audio streams do not satisfy the locked audio requirement." if actual is not None else "Required audio cannot be checked because stream metadata is missing.", {"minimum_streams": needed, "preserve_count": self.preserve_audio}, actual, status=None if actual is not None else "unverifiable")
        if self.require_audio_signal:
            signal = candidate.get("audio_has_signal", MISSING)
            add("audio_signal", signal is True, "audio_silent" if signal is False else "audio_signal_unverifiable", "Required audio is present but silent." if signal is False else "Non-silent audio is required but decoded signal evidence is missing.", True, None if signal is MISSING else signal, verification="decoded_audio_signal", status=None if signal is not MISSING else "unverifiable")
        for path, expected in self.immutable_properties.items():
            actual = _at(candidate, path)
            if expected is True and baseline is not None:
                expected = _at(baseline, path)
            passed = actual is not MISSING and expected is not MISSING and actual == expected
            add(f"immutable.{path}", passed, "immutable_mismatch" if actual is not MISSING else "immutable_unverifiable", f"Immutable property {path!r} is absent or changed.", None if expected is MISSING else expected, None if actual is MISSING else actual, status=None if actual is not MISSING else "unverifiable")
        for path in self.locked_properties:
            expected, actual = _at(baseline or {}, path), _at(candidate, path)
            passed = expected is not MISSING and actual is not MISSING and expected == actual
            add(f"locked.{path}", passed, "locked_property_mismatch" if actual is not MISSING else "locked_property_unverifiable", f"User-locked property {path!r} is absent or changed.", None if expected is MISSING else expected, None if actual is MISSING else actual, status=None if actual is MISSING else "unverifiable")
        return ConstraintReport(not violations, tuple(checks), tuple(violations), {"contract": self.to_dict(), "baseline_used": baseline is not None, "editable_text_layers": sorted(texts), "declared_objects": sorted(declared_objects(candidate)), "verification_boundary": "declared metadata/editable layers/assets only; no vision inference"})

    validate = check

    def assert_satisfied(self, candidate: Any, baseline: Any = None) -> ConstraintReport:
        report = self.check(candidate, baseline)
        if not report.passed:
            raise ConstraintViolation(report)
        return report


def check_constraints(constraints: Mapping[str, Any] | CreativeConstraints, candidate: Any, baseline: Any = None) -> ConstraintReport:
    return CreativeConstraints.from_mapping(constraints).check(candidate, baseline)


validate_constraints = check_constraints


__all__ = ["ConstraintError", "ConstraintViolation", "ConstraintReport", "CreativeConstraints", "check_constraints", "validate_constraints", "editable_text_layers", "declared_objects"]
