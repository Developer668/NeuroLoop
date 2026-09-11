from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

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

class RunCreate(StrictModel):
    project_id: str
    mode: Literal['analyze', 'compare', 'optimize'] = 'analyze'
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

    @model_validator(mode='after')
    def research_readout(self):
        if self.include_tsam and not self.tsam_research_acknowledged:
            raise ValueError('Acknowledge the TSAM research-use terms before requesting the experimental readout')
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
