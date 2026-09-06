from datetime import date as date_, datetime as datetime_

import pytest
from pydantic import ValidationError

from app.history.schemas import HistoryEntry, ManualEntryCreate


def test_manual_entry_create_accepts_valid_payload() -> None:
    entry = ManualEntryCreate(
        exercise="squat", date="2026-09-01", sets=3, reps=8, weight=100.0, notes="felt good"
    )
    assert entry.exercise == "squat"
    assert entry.sets == 3


def test_manual_entry_create_allows_omitted_optional_fields() -> None:
    entry = ManualEntryCreate(exercise="pushup", date="2026-09-01", sets=3, reps=10)
    assert entry.weight is None
    assert entry.notes is None


@pytest.mark.parametrize("field", ["sets", "reps"])
def test_manual_entry_create_rejects_zero(field: str) -> None:
    payload = {"exercise": "squat", "date": "2026-09-01", "sets": 3, "reps": 8}
    payload[field] = 0
    with pytest.raises(ValidationError):
        ManualEntryCreate(**payload)


def test_manual_entry_create_rejects_unknown_exercise() -> None:
    with pytest.raises(ValidationError):
        ManualEntryCreate(exercise="bicep_curl", date="2026-09-01", sets=3, reps=8)


class _FakeOrmEntry:
    """Stand-in for a WorkoutEntry ORM instance, for from_attributes conversion."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_history_entry_converts_from_orm_attributes() -> None:
    orm_entry = _FakeOrmEntry(
        id=1,
        exercise="squat",
        date=date_(2026, 9, 1),
        source="manual",
        created_at=datetime_(2026, 9, 1, 12, 0, 0),
        sets=3,
        reps=8,
        weight=100.0,
        notes=None,
        rep_count=None,
        avg_form_accuracy=None,
        rep_scores=None,
    )
    entry = HistoryEntry.model_validate(orm_entry)
    assert entry.id == 1
    assert entry.source == "manual"
    assert entry.sets == 3
