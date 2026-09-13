"""Versioned contracts shared by the API, notebook, agent and UI.

No unavailable scientific signal is represented as zero or as a made-up score.
"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import hashlib
import json
import math


def now() -> float:
    return datetime.now(timezone.utc).timestamp()


def utc(timestamp: float | None = None) -> str:
    return datetime.fromtimestamp(now() if timestamp is None else timestamp, timezone.utc).isoformat()


def uid() -> str:
    return str(uuid4())


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RunState(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    EVALUATING = "EVALUATING"
    DECIDING = "DECIDING"
    REGENERATING = "REGENERATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    APPROVED = "APPROVED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL = {RunState.COMPLETE, RunState.FAILED, RunState.CANCELLED}
PAUSED = {RunState.READY_FOR_REVIEW, RunState.NEEDS_ATTENTION, RunState.APPROVED}


class Claim(Contract):
    text: str = Field(min_length=1, max_length=1000)
    source_id: str = Field(min_length=1, max_length=200)
    source_quote: str = Field(min_length=1, max_length=3000)


class BrandSpec(Contract):
    name: str = Field(min_length=1, max_length=120)
    product_description: str = Field(default="", max_length=6000)
    approved_claims: list[Claim] = Field(default_factory=list, max_length=50)
    prohibited_claims: list[str] = Field(default_factory=list, max_length=50)
    voice: str = Field(default="", max_length=2000)
    colors: list[str] = Field(default_factory=list, max_length=12)
    locked_requirements: list[str] = Field(default_factory=lambda: ["product_identity"], max_length=40)
    source_text: str = Field(default="", max_length=24000)


class CampaignSpec(Contract):
    title: str = Field(min_length=1, max_length=160)
    brief: str = Field(min_length=3, max_length=12000)
    brand: BrandSpec
    objective: str = Field(default="creative_quality", max_length=300)
    audience: str = Field(default="", max_length=1000)
    platform: str = Field(default="instagram_reels", max_length=100)
    media_kind: Literal["video", "image"] = "video"
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"] = "9:16"
    duration_seconds: float = Field(default=12, ge=1, le=60)
    target_emotions: dict[str, float] = Field(default_factory=dict)

    @field_validator("target_emotions")
    @classmethod
    def emotion_values(cls, values):
        if len(values) > 20 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values.values()):
            raise ValueError("Emotion targets must be finite relative preferences in [0,1]")
        return values


class RunConfig(Contract):
    initial_candidates: int = Field(default=2, ge=1, le=3)
    beam_width: int = Field(default=2, ge=1, le=3)
    branch_factor: int = Field(default=2, ge=1, le=3)
    max_rounds: int = Field(default=3, ge=1, le=6)  # Includes initial round 0.
    max_candidates: int = Field(default=10, ge=1, le=30)
    max_wall_seconds: int = Field(default=7200, ge=30, le=43200)
    max_gpu_seconds: float = Field(default=3600, gt=0, le=43200)
    max_cost_usd: float | None = Field(default=None, gt=0, le=500)
    generation_cost_reservation_usd: float | None = Field(default=None, ge=0)
    max_model_calls: int = Field(default=80, ge=1, le=300)
    min_improvement: float = Field(default=0.02, ge=0, le=1)
    plateau_rounds: int = Field(default=2, ge=1, le=4)
    quality_threshold: float = Field(default=0.9, ge=0, le=1)
    decision_confidence_floor: float = Field(default=0.70, ge=0, le=1)
    required_evaluators: list[Literal["vision", "tsam", "tribe"]] = Field(default_factory=lambda: ["vision"])
    optional_evaluators: list[Literal["tsam", "tribe"]] = Field(default_factory=lambda: ["tsam", "tribe"])
    evaluator_disagreement_limit: float = Field(default=0.4, ge=0, le=1)
    review_on_missing_evidence: bool = True

    @model_validator(mode="after")
    def bounds(self):
        if self.max_candidates < self.initial_candidates:
            raise ValueError("Candidate budget must cover initial candidates")
        if "vision" not in self.required_evaluators:
            raise ValueError("Vision quality and brand constraints must be evaluated")
        if len(set(self.required_evaluators)) != len(self.required_evaluators):
            raise ValueError("Duplicate evaluators")
        if self.max_cost_usd is not None and self.generation_cost_reservation_usd is None:
            raise ValueError("A dollar ceiling requires a conservative per-generation reservation")
        return self


class StartRun(Contract):
    config: RunConfig = Field(default_factory=RunConfig)
    reference_asset_ids: list[str] = Field(default_factory=list, max_length=30)


class EvidenceObservation(Contract):
    evaluation_id: str = Field(min_length=1)
    response_metric: str = Field(min_length=1)
    value: float = Field(ge=0, le=1)
    # Null for aggregate scores; do not invent temporal measurements.
    time_range: tuple[float, float] | None = None

    @field_validator("time_range")
    @classmethod
    def ordered_range(cls, value):
        if value is not None and not 0 <= value[0] <= value[1]:
            raise ValueError("Evidence range must be ordered and nonnegative")
        return value


class CreativeEvidence(Contract):
    evaluation_id: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=3000)


class OptimizationHypothesis(Contract):
    observation: EvidenceObservation
    creative_evidence: CreativeEvidence
    explanation: str = Field(min_length=1, max_length=3000)
    confidence: float = Field(ge=0, le=1)
    target: str = Field(min_length=1, max_length=1000)
    instruction: str = Field(min_length=1, max_length=3000)
    expected_metric: str = Field(min_length=1)
    expected_direction: Literal["increase", "decrease"]
    minimum_expected_delta: float | None = Field(default=None, ge=0, le=1)


class EditIntent(Contract):
    primary_goal: str = Field(min_length=1, max_length=1000)
    requested_changes: list[str] = Field(default_factory=list, max_length=20)
    preserve: list[str] = Field(default_factory=list, max_length=40)
    reasoning_evidence_ids: list[str] = Field(default_factory=list, max_length=40)
    expected_outcome: str = Field(default="", max_length=1500)
    optimization: OptimizationHypothesis | None = None


class CandidatePlan(Contract):
    parent_creative_id: str | None = None
    prompt: str = Field(min_length=3, max_length=16000)
    strategy: str = Field(min_length=1, max_length=160)
    edit_intent: EditIntent
    seed: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict, json_schema_extra={
        "type": "object", "additionalProperties": False,
        "properties": {"guidance_scale": {"type": "number", "minimum": 0, "maximum": 30},
                       "num_inference_steps": {"type": "integer", "minimum": 1, "maximum": 100},
                       "strength": {"type": "number", "minimum": 0, "maximum": 1}}})

    @field_validator("parameters")
    @classmethod
    def bounded_parameters(cls, value):
        # Resolution/duration/model/loading are operator-owned, not LLM controls.
        bounds = {"guidance_scale": (0, 30), "num_inference_steps": (1, 100), "strength": (0, 1)}
        if set(value) - bounds.keys():
            raise ValueError("Only bounded generation settings may be proposed")
        for key, number in value.items():
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not bounds[key][0] <= number <= bounds[key][1]:
                raise ValueError("Generation setting is outside its safe range")
            if key == "num_inference_steps" and not isinstance(number, int):
                raise ValueError("Inference steps must be an integer")
        return value


class PlanResult(Contract):
    summary: str = Field(min_length=1, max_length=5000)
    candidates: list[CandidatePlan] = Field(min_length=1, max_length=9)
    model: str = Field(min_length=1)
    usage: dict[str, int] = Field(default_factory=dict)


class PlanReview(Contract):
    plan_hash: str = Field(min_length=64, max_length=64)
    choice: Literal["APPROVE", "REJECT"]
    confidence: float = Field(ge=0, le=1)
    model: str = Field(min_length=1)
    raw_response: dict[str, Any]


class ModelProvenance(Contract):
    model: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=300)
    configuration_hash: str = Field(min_length=1, max_length=200)
    checkpoint_sha256: str | None = None

    @property
    def comparison_key(self) -> str:
        return digest(self.model_dump())


class Score(Contract):
    value: float = Field(ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str = Field(min_length=1, max_length=1000)
    meaning: str = Field(min_length=1, max_length=2000)
    timestamp: str = Field(default_factory=utc)


class ConstraintResult(Contract):
    name: str = Field(min_length=1, max_length=200)
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    evidence: str = Field(min_length=1, max_length=3000)


class EvaluationResult(Contract):
    evaluator: Literal["vision", "tsam", "tribe"]
    status: Literal["SUCCEEDED", "UNAVAILABLE", "NOT_APPLICABLE", "INSUFFICIENT_EVIDENCE"]
    provenance: ModelProvenance
    scores: dict[str, Score] = Field(default_factory=dict)
    constraints: list[ConstraintResult] = Field(default_factory=list, max_length=100)
    observations: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=30)
    gpu_seconds: float = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    uncertainty: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def truthful_status(self):
        if self.status != "SUCCEEDED" and self.scores:
            raise ValueError("Unavailable evaluations cannot contain scores")
        if self.evaluator in {"tsam", "tribe"} and not self.limitations:
            raise ValueError("Neural/affective proxies require explicit interpretation limitations")
        if self.evaluator == "tribe" and any(k in self.scores for k in ("ctr", "conversion", "purchase_probability")):
            raise ValueError("TRIBE output does not establish commercial outcome probabilities")
        return self


class GenerationResult(Contract):
    asset_id: str
    provenance: ModelProvenance
    gpu_seconds: float = Field(default=0, ge=0)
    runtime_seconds: float = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    parameters: dict[str, Any] = Field(default_factory=dict)


class DecisionResult(Contract):
    decision: Literal["KEEP", "REGENERATE", "GENERATE_ALTERNATIVE", "RUN_MORE_EVALUATION", "ASK_HUMAN", "READY_FOR_DEPLOYMENT", "STOP", "REJECT"]
    selected_creative_ids: list[str] = Field(default_factory=list, max_length=3)
    strategy: str = Field(default="EVIDENCE_LED", max_length=200)
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str] = Field(default_factory=list, max_length=30)
    raw_response: dict[str, Any]
    model: str = Field(min_length=1)


class WorkerHello(Contract):
    worker_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    capabilities: dict[str, dict[str, Any]]
    provider: str = Field(default="local", max_length=100)
    provider_workload_approved: bool = False


class LeaseRequest(Contract):
    worker_id: str
    lease_token: str = Field(min_length=20)
    progress: dict[str, Any] = Field(default_factory=dict)


class CompleteJob(LeaseRequest):
    result: dict[str, Any]


class FailJob(LeaseRequest):
    code: Literal["NOT_CONFIGURED", "UNAVAILABLE", "CANCELLED", "OUT_OF_MEMORY", "INVALID_OUTPUT", "TRANSIENT", "UNCERTAIN", "FAILED"]
    detail: str = Field(max_length=2000)
    safe_to_retry: bool = False
    gpu_seconds: float = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)


class FeedbackRequest(Contract):
    creative_id: str
    kind: Literal["like", "dislike", "prefer", "annotation", "reject", "lock"]
    text: str = Field(default="", max_length=4000)


class ResumeRequest(Contract):
    acknowledge_uncertain_cost: bool = False


class ResearchProposal(Contract):
    source: Literal["ARIA", "human"]
    hypothesis: str = Field(min_length=5, max_length=5000)
    evidence_run_ids: list[str] = Field(min_length=1, max_length=50)
    proposed_config: RunConfig
    source_receipt: str = Field(min_length=1, max_length=2000)


class DeploymentSpec(Contract):
    run_id: str
    creative_id: str
    ad_account_id: str = Field(pattern=r"^(act_)?[0-9]+$")
    page_id: str = Field(pattern=r"^[0-9]+$")
    destination: str = Field(min_length=10, max_length=2000)
    daily_budget_minor: int = Field(ge=100, le=1000000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    audience: dict[str, Any]
    objective: Literal["OUTCOME_TRAFFIC"] = "OUTCOME_TRAFFIC"
    message: str = Field(max_length=2000)
    headline: str = Field(max_length=255)
    special_ad_categories: list[Literal["CREDIT", "EMPLOYMENT", "HOUSING", "ISSUES_ELECTIONS_POLITICS", "FINANCIAL_PRODUCTS_SERVICES"]] = Field(default_factory=list)
    research_license_approved_for_commercial_use: bool = False

    @field_validator("destination")
    @classmethod
    def destination_https(cls, value):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Destination must be an HTTPS URL without credentials")
        return value
