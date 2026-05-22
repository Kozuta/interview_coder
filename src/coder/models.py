"""Модели данных кодировщика."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SegmentType(str, Enum):
    INTRO = "intro"
    CORE = "core"
    OUTRO = "outro"
    SMALL_TALK = "small_talk"
    OFF_TOPIC = "off_topic"
    ON_TOPIC = "on_topic"


class RunMode(str, Enum):
    TEST = "test"
    FULL = "full"


class TestScopeType(str, Enum):
    DURATION_MINUTES = "duration_minutes"
    ON_TOPIC_UTTERANCES = "on_topic_utterances"


class RespondentField(BaseModel):
    key: str
    label: str
    field_type: Literal["text", "date", "select"] = "text"


class TestScope(BaseModel):
    type: TestScopeType = TestScopeType.ON_TOPIC_UTTERANCES
    value: int = 20


class RespondentMeta(BaseModel):
    id: str
    transcript_file: str
    interview_date: str | None = None
    segment: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Utterance(BaseModel):
    index: int
    timestamp_sec: float | None = None
    timestamp_raw: str | None = None
    speaker: str
    text: str
    is_respondent: bool = False
    segment_type: SegmentType | None = None
    include_in_coding: bool = False
    exclude_reason: str | None = None


class ParsedTranscript(BaseModel):
    respondent_id: str
    source_file: str
    utterances: list[Utterance] = Field(default_factory=list)


class Observation(BaseModel):
    id: str
    respondent_id: str
    quote: str
    atom: str
    context: str
    content: str = ""
    kind: Literal["observation", "insight"] = "observation"
    affinity_cluster: str = ""
    primary_code: str = ""
    secondary_code: str | None = None
    modality_tags: list[str] = Field(default_factory=list)
    is_key_task: bool = False
    normalized_category: str = ""
    utterance_index: int | None = None
    respondent_meta: dict[str, Any] = Field(default_factory=dict)


class SummaryRow(BaseModel):
    affinity_cluster: str
    normalized_category: str
    description: str
    observation_ids: list[str] = Field(default_factory=list)
    criticality: str = ""
    cluster_frequency: str = ""
    respondent_count: int = 0
    segments: str = ""
    secondary_codes: str = ""
    key_params: str = ""
    primary_code: str = ""
    count: int = 0
