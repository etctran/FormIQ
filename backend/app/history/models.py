"""ORM model backing the workout history table. One table serves both
manual entries and auto-logged video analyses, discriminated by
`source`; columns specific to one source are NULL for the other (see
docs/superpowers/specs/2026-09-05-workout-history-tracking-design.md).
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.history.database import Base


class WorkoutEntry(Base):
    __tablename__ = "workout_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exercise: Mapped[str] = mapped_column(String, nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # manual entries only
    sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # video entries only
    rep_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_form_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    rep_scores: Mapped[list | None] = mapped_column(JSON, nullable=True)
