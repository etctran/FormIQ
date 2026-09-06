"""Workout history endpoints: manual entry CRUD. Also used internally
by app.api.routes to auto-log every successful video analysis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.history import service
from app.history.database import get_session
from app.history.models import WorkoutEntry
from app.history.schemas import HistoryEntry, ManualEntryCreate

router = APIRouter(prefix="/history", tags=["history"])


@router.post("", response_model=HistoryEntry, status_code=201)
def create_history_entry(
    data: ManualEntryCreate, session: Session = Depends(get_session)
) -> WorkoutEntry:
    return service.create_entry(session, data)


@router.get("", response_model=list[HistoryEntry])
def list_history_entries(session: Session = Depends(get_session)) -> list[WorkoutEntry]:
    return service.list_entries(session)


@router.delete("/{entry_id}", status_code=204)
def delete_history_entry(entry_id: int, session: Session = Depends(get_session)) -> None:
    if not service.delete_entry(session, entry_id):
        raise HTTPException(status_code=404, detail="History entry not found")
