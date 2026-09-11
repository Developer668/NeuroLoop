from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, populate_by_name=True)

class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    brief: str = Field(default='', max_length=4000)
    asset_id: str | None = None
    reference_ids: list[str] = Field(default_factory=list, max_length=3)
    constraints: dict = Field(default_factory=dict)

class TimedWord(StrictModel):
    text: str = Field(min_length=1, max_length=200)
    start: float = Field(ge=0, le=3600)
    end: float = Field(gt=0, le=3600)
    @model_validator(mode='after')
    def times(self):
        if self.end <= self.start:
            raise ValueError('Word end must follow start')
        return self

EmotionName = Literal['happiness','surprise','fear','sadness','anger','neutral','contempt','disgust']

class EmotionTarget(StrictModel):
    desired: float = Field(ge=0, le=1)
    weight: float = Field(default=1.0, gt=0, le=5)


class NormalizedTimeWindow(StrictModel):
    """A source-duration-normalized interval, independent of prediction rows."""

    start: float = Field(ge=0, le=1)
    end: float = Field(gt=0, le=1)
    label: str = Field(default='', max_length=120)

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Time-window end must follow start')
        return self


class TargetWindow(NormalizedTimeWindow):
    id: str = Field(default='', max_length=120)
    weight: float = Field(default=1.0, gt=0, le=5)
    emotions: dict[EmotionName, EmotionTarget] = Field(default_factory=dict)

    @model_validator(mode='after')
    def has_emotions(self):
        if not self.emotions:
            raise ValueError('Each target window requires at least one emotion target')
        return self


class ResponseTarget(StrictModel):
    goal: str = Field(default='', max_length=1000)
    emotions: dict[EmotionName, EmotionTarget] = Field(default_factory=dict)
    version: Literal['target-spec/v1'] = 'target-spec/v1'
    scope: Literal['whole_creative', 'time_window', 'multi_window'] = 'whole_creative'
    time_window: NormalizedTimeWindow | None = None
    windows: list[TargetWindow] = Field(default_factory=list, max_length=16)
    # Additive spelling for clients that pluralize this field.
    time_windows: list[TargetWindow] = Field(default_factory=list, max_length=16)

    @model_validator(mode='after')
    def nonempty(self):
        if self.windows and self.time_windows:
            raise ValueError('Use windows or time_windows, not both')
        selected_windows = self.windows or self.time_windows
        if self.time_window is not None and selected_windows:
            raise ValueError('Use one time_window or multiple windows, not both')
        if not self.emotions and not selected_windows and self.time_window is None:
            raise ValueError('At least one emotion target is required')
        if self.time_window is not None and self.scope == 'whole_creative':
            self.scope = 'time_window'
        if selected_windows and self.scope == 'whole_creative':
            self.scope = 'multi_window'
        if self.scope == 'time_window' and self.time_window is None and not selected_windows:
            raise ValueError('A time_window scope requires a normalized time window')
        return self


# Public scientific-contract name; ResponseTarget remains the compatibility name.
TargetSpec = ResponseTarget

class RunCreate(StrictModel):
    project_id: str
    mode: Literal['analyze', 'compare', 'optimize'] = 'analyze'
    objective: Literal['reference_similarity','response_target'] = 'reference_similarity'
    target: TargetSpec | None = None
    max_evaluations: int = Field(default=4, ge=1, le=12)
    max_seconds: int = Field(default=1800, ge=30, le=7200)
    min_gain: float = Field(default=0.005, ge=0.0001, le=0.25)
    target_score: float = Field(default=0.98, ge=-1, le=1)
    no_speech: bool = False
    transcript: list[TimedWord] = Field(default_factory=list, max_length=2000)
    allow_static_presentation: bool = False
    presentation_seconds: int = Field(default=8, ge=5, le=30)
    operators: list[Literal['contrast_up','contrast_down','brightness_up','brightness_down','saturation_up','saturation_down','headline_early','headline_late']] = Field(default_factory=lambda:['contrast_up','contrast_down','brightness_up','brightness_down'])
    hypothesis: str = Field(default='', max_length=1000)
    include_tsam: bool = False
    tsam_research_acknowledged: bool = False
    include_kragel: bool = False

    @model_validator(mode='after')
    def response_contract(self):
        if self.include_tsam and not self.tsam_research_acknowledged:
            raise ValueError('Acknowledge the TSAM research-use terms before requesting the experimental readout')
        if self.objective == 'response_target' and self.target is None:
            raise ValueError('A response-target objective requires a target')
        if self.target is not None and self.objective != 'response_target':
            raise ValueError('A response target requires objective=response_target')
        if self.objective == 'response_target' and not (self.include_tsam or self.include_kragel):
            raise ValueError('Response-target optimization requires TSAM, Kragel, or both')
        return self

class CreativeCreate(StrictModel):
    asset_id: str
    headline: str = Field(min_length=1, max_length=120)
    subline: str = Field(default='', max_length=200)
    duration: int = Field(default=8, ge=5, le=30)
    headline_start: float = Field(default=1.0, ge=0, le=25)
    aspect: Literal['landscape','portrait','square'] = 'landscape'

class CompareRequest(StrictModel):
    evaluation_ids: list[str] = Field(min_length=2,max_length=12)

class TranscriptUpdate(StrictModel):
    words: list[TimedWord] = Field(min_length=1, max_length=2000)

class LoginRequest(StrictModel):
    token: str

class WorkspacePreferences(StrictModel):
    workspace_name: str = Field(default='My workspace', min_length=1, max_length=60)
    display_name: str = Field(default='NeuroLoop', min_length=1, max_length=60)
    reduced_motion: bool = False
