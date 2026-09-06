"""Request/response Pydantic models for the workout-history API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import Exercise, RepScore


class ManualEntryCreate(BaseModel):
    exercise: Exercise
    date: date
    sets: int = Field(ge=1)
    reps: int = Field(ge=1)
    weight: float | None = None
    notes: str | None = None


class HistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise: Exercise
    date: date
    source: Literal["manual", "video"]
    created_at: datetime
    sets: int | None = None
    reps: int | None = None
    weight: float | None = None
    notes: str | None = None
    rep_count: int | None = None
    avg_form_accuracy: float | None = None
    rep_scores: list[RepScore] | None = None
