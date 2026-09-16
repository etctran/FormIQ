from datetime import date

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.history import service
from app.history.database import Base, build_engine
from app.history.schemas import ManualEntryCreate, ManualEntryUpdate
from app.schemas.analysis import AnalysisResponse, Exercise, RepScore


@pytest.fixture
def session(tmp_path):
    engine = build_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    with TestSession() as s:
        yield s
    engine.dispose()


def test_create_entry_persists_manual_fields(session: Session) -> None:
    data = ManualEntryCreate(
        exercise=Exercise.SQUAT, date=date(2026, 9, 1), sets=3, reps=8, weight=100.0
    )
    entry = service.create_entry(session, data)
    assert entry.id is not None
    assert entry.source == "manual"
    assert entry.exercise == "squat"
    assert entry.sets == 3


def test_list_entries_orders_newest_first(session: Session) -> None:
    older = ManualEntryCreate(exercise=Exercise.SQUAT, date=date(2026, 9, 1), sets=3, reps=8)
    newer = ManualEntryCreate(exercise=Exercise.ROW, date=date(2026, 9, 3), sets=4, reps=6)
    service.create_entry(session, older)
    service.create_entry(session, newer)

    entries = service.list_entries(session)
    assert [e.exercise for e in entries] == ["row", "squat"]


def test_delete_entry_removes_row_and_returns_true(session: Session) -> None:
    data = ManualEntryCreate(exercise=Exercise.SQUAT, date=date(2026, 9, 1), sets=3, reps=8)
    entry = service.create_entry(session, data)

    assert service.delete_entry(session, entry.id) is True
    assert service.list_entries(session) == []


def test_delete_entry_returns_false_when_not_found(session: Session) -> None:
    assert service.delete_entry(session, 999) is False


def test_log_video_entry_with_reps_computes_average(session: Session) -> None:
    response = AnalysisResponse(
        exercise=Exercise.PUSHUP,
        frame_count=100,
        frames=[],
        reps=[
            RepScore(rep_index=0, start_sec=0.0, end_sec=1.0, form_accuracy=0.8, faults=[]),
            RepScore(
                rep_index=1, start_sec=1.0, end_sec=2.0, form_accuracy=1.0, faults=["hip_sag"]
            ),
        ],
    )
    entry = service.log_video_entry(session, Exercise.PUSHUP, response)
    assert entry.source == "video"
    assert entry.rep_count == 2
    assert entry.avg_form_accuracy == pytest.approx(0.9)
    assert entry.rep_scores == [
        {"rep_index": 0, "start_sec": 0.0, "end_sec": 1.0, "form_accuracy": 0.8, "faults": []},
        {"rep_index": 1, "start_sec": 1.0, "end_sec": 2.0, "form_accuracy": 1.0, "faults": ["hip_sag"]},
    ]


def test_log_video_entry_with_no_reps_has_no_average(session: Session) -> None:
    response = AnalysisResponse(exercise=Exercise.SQUAT, frame_count=0, frames=[], reps=[])
    entry = service.log_video_entry(session, Exercise.SQUAT, response)
    assert entry.rep_count == 0
    assert entry.avg_form_accuracy is None
    assert entry.rep_scores == []


def test_update_entry_applies_only_provided_fields(session: Session) -> None:
    data = ManualEntryCreate(exercise=Exercise.SQUAT, date=date(2026, 9, 1), sets=3, reps=8)
    entry = service.create_entry(session, data)

    updated = service.update_entry(
        session, entry.id, ManualEntryUpdate(sets=5, notes="felt strong")
    )

    assert updated is not None
    assert updated.sets == 5
    assert updated.notes == "felt strong"
    assert updated.reps == 8  # untouched field keeps its original value
    assert updated.exercise == "squat"  # untouched field keeps its original value


def test_update_entry_returns_none_when_not_found(session: Session) -> None:
    assert service.update_entry(session, 999, ManualEntryUpdate(sets=5)) is None


def test_update_entry_rejects_video_entries(session: Session) -> None:
    response = AnalysisResponse(exercise=Exercise.SQUAT, frame_count=0, frames=[], reps=[])
    entry = service.log_video_entry(session, Exercise.SQUAT, response)

    with pytest.raises(ValueError, match="manual"):
        service.update_entry(session, entry.id, ManualEntryUpdate(sets=5))


def test_update_entry_can_change_exercise(session: Session) -> None:
    data = ManualEntryCreate(exercise=Exercise.SQUAT, date=date(2026, 9, 1), sets=3, reps=8)
    entry = service.create_entry(session, data)

    updated = service.update_entry(session, entry.id, ManualEntryUpdate(exercise=Exercise.ROW))

    assert updated is not None
    assert updated.exercise == "row"
