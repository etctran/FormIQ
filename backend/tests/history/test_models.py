from datetime import UTC, date, datetime

from sqlalchemy.orm import sessionmaker

from app.history.database import Base, build_engine
from app.history.models import WorkoutEntry


def _session_factory(tmp_path):
    engine = build_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_manual_entry_round_trip(tmp_path) -> None:
    Session = _session_factory(tmp_path)
    with Session() as session:
        entry = WorkoutEntry(
            exercise="squat",
            date=date(2026, 9, 1),
            source="manual",
            created_at=datetime.now(UTC),
            sets=3,
            reps=8,
            weight=100.0,
            notes="felt good",
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        entry_id = entry.id

    with Session() as session:
        fetched = session.get(WorkoutEntry, entry_id)
        assert fetched is not None
        assert fetched.exercise == "squat"
        assert fetched.source == "manual"
        assert fetched.sets == 3
        assert fetched.reps == 8
        assert fetched.weight == 100.0
        assert fetched.notes == "felt good"
        assert fetched.rep_count is None
        assert fetched.avg_form_accuracy is None
        assert fetched.rep_scores is None


def test_video_entry_round_trip(tmp_path) -> None:
    Session = _session_factory(tmp_path)
    with Session() as session:
        entry = WorkoutEntry(
            exercise="pushup",
            date=date(2026, 9, 2),
            source="video",
            created_at=datetime.now(UTC),
            rep_count=5,
            avg_form_accuracy=0.85,
            rep_scores=[
                {"rep_index": 0, "start_sec": 0.0, "end_sec": 1.0, "form_accuracy": 0.85, "faults": []}
            ],
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        entry_id = entry.id

    with Session() as session:
        fetched = session.get(WorkoutEntry, entry_id)
        assert fetched is not None
        assert fetched.source == "video"
        assert fetched.rep_count == 5
        assert fetched.avg_form_accuracy == 0.85
        assert fetched.rep_scores == [
            {"rep_index": 0, "start_sec": 0.0, "end_sec": 1.0, "form_accuracy": 0.85, "faults": []}
        ]
        assert fetched.sets is None
        assert fetched.reps is None
        assert fetched.weight is None
        assert fetched.notes is None
