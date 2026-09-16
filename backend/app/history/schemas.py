"""Request/response Pydantic models for the workout-history API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from datetime import date as Date  # see comment on ManualEntryUpdate.date below
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.analysis import Exercise, RepScore


class ManualEntryCreate(BaseModel):
    exercise: Exercise
    date: date
    sets: int = Field(ge=1)
    reps: int = Field(ge=1)
    weight: float | None = None
    notes: str | None = None


class ManualEntryUpdate(BaseModel):
    """Partial update for a manual entry — every field optional, only
    fields explicitly set by the client are applied (see
    service.update_entry's `exclude_unset=True` usage).

    Note: the `date` field below is typed with the `Date` alias, not the
    bare `date` type. A field named `date` with a default value creates a
    class-level `date = None` attribute that shadows the imported `date`
    type when Pydantic resolves this file's postponed
    (`from __future__ import annotations`) annotations — removing this
    alias would silently break `date | None` into `None | None` and raise
    a TypeError at class-definition time."""

    exercise: Exercise | None = None
    date: Date | None = None
    sets: int | None = Field(default=None, ge=1)
    reps: int | None = Field(default=None, ge=1)
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

    @field_validator("created_at", mode="after")
    @classmethod
    def _ensure_created_at_is_utc_aware(cls, value: datetime) -> datetime:
        """Every write path stores an aware datetime.now(UTC) value, but
        SQLite silently drops tzinfo on read-back regardless of the
        column's DateTime(timezone=True) flag — so a naive value here is
        always actually UTC, not local time."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
