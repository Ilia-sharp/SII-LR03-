from __future__ import annotations

from pydantic import BaseModel, Field


class SegmentResponse(BaseModel):
    start: float
    end: float
    text: str


class KeywordResponse(BaseModel):
    keyword: str
    count: int = Field(ge=1)


class TranscriptionResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    text: str
    language: str
    segments: list[SegmentResponse]
    keywords_found: list[KeywordResponse]
    model: str
    model_version: str
    latency_ms: int = Field(ge=0)
