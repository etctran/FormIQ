"""Business logic for reading/writing workout history — kept separate
from the API routes so it can be unit-tested without spinning up
FastAPI, and reused by both the manual-entry endpoints and /analyze's
auto-log side effect.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.history.models import WorkoutEntry
from app.history.schemas import ManualEntryCreate
from app.schemas.analysis import AnalysisResponse, Exercise


def create_entry(session: Session, data: ManualEntryCreate) -> WorkoutEntry:
    entry = WorkoutEntry(
        exercise=data.exercise.value,
        date=data.date,
        source="manual",
        created_at=datetime.now(UTC),
        sets=data.sets,
        reps=data.reps,
        weight=data.weight,
        notes=data.notes,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def list_entries(session: Session) -> list[WorkoutEntry]:
    stmt = select(WorkoutEntry).order_by(WorkoutEntry.date.desc(), WorkoutEntry.created_at.desc())
    return list(session.scalars(stmt))


def delete_entry(session: Session, entry_id: int) -> bool:
    entry = session.get(WorkoutEntry, entry_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True


def log_video_entry(
    session: Session, exercise: Exercise, response: AnalysisResponse
) -> WorkoutEntry:
    rep_count = len(response.reps)
    avg_form_accuracy = (
        sum(rep.form_accuracy for rep in response.reps) / rep_count if rep_count else None
    )
    entry = WorkoutEntry(
        exercise=exercise.value,
        date=datetime.now(UTC).date(),
        source="video",
        created_at=datetime.now(UTC),
        rep_count=rep_count,
        avg_form_accuracy=avg_form_accuracy,
        rep_scores=[rep.model_dump(mode="json") for rep in response.reps],
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry
