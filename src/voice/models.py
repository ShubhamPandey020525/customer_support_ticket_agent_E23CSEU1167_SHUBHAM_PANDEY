"""Pydantic models for the voice endpoints.

Mirrors mid_session_requirements/voice/models.py, extended with an error model.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptionResponse(BaseModel):
    success: bool = True
    transcript: str = Field(default="", min_length=0)
    processing_time_ms: int = Field(ge=0, default=0)
    error: str | None = None


class SynthesisRequest(BaseModel):
    message_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)
