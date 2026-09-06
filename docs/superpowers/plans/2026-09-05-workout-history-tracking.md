# Workout History / Exercise Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, single-user workout history — auto-logged from every `/analyze/{exercise}` call and manually loggable without a video — replacing the app's current fully-ephemeral, single-result-at-a-time behavior.

**Architecture:** New `backend/app/history/` package (SQLite via SQLAlchemy: model, Pydantic schemas, a service layer, a `/history` router) wired into the existing `/analyze/{exercise}` handler as a best-effort side effect. Frontend extends the existing `App.tsx` status state machine (no router) with a `'history'` view composing a manual-entry form and a chronological list.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x (new dependency), Pydantic v2, pytest — React 19, TypeScript, Vitest + Testing Library.

**Spec:** [docs/superpowers/specs/2026-09-05-workout-history-tracking-design.md](../specs/2026-09-05-workout-history-tracking-design.md)

## Global Constraints

- Single-user, no auth — history is global, not scoped to any account.
- No changes to `AnalysisResponse`, `RepScore`, or the `/analyze/{exercise}` request/response shape (`backend/app/schemas/analysis.py`). History logging reads that response; it never alters it.
- A history-logging failure must never turn a successful `/analyze` call into an error response — always caught, logged, and swallowed.
- New backend dependency: `sqlalchemy>=2.0`. No `scipy`/async DB driver/Alembic — `Base.metadata.create_all()` is the only migration mechanism at this scale.
- SQLite file at `backend/data/formiq.db` (path derived as three parents up from `backend/app/history/database.py`, so it resolves correctly both locally and inside the Docker image, where `app/` is copied to `/app/app`).
- No router added to the frontend. Extend `App.tsx`'s existing `Status` union (`'idle' | 'analyzing' | 'results'`) with `'history'`.
- No entry editing (create + delete only), no pagination, no trend charts/analytics — a flat chronological list is the entire history UI.
- Ruff line-length is 100 (`backend/pyproject.toml`); run `ruff check backend` after backend tasks if convenient.
- Run backend tests from the repo root as `pytest backend/tests/...`. Run frontend tests from `frontend/` as `npm test`.

---

## File Structure

```
backend/app/history/
  __init__.py          # empty (package marker)
  database.py           # Base, build_engine, module-level engine/SessionLocal, init_db, get_session
  models.py              # WorkoutEntry ORM model
  schemas.py              # ManualEntryCreate, HistoryEntry Pydantic models
  service.py              # create_entry, list_entries, delete_entry, log_video_entry

backend/app/api/history.py   # POST/GET /history, DELETE /history/{id}
backend/app/api/routes.py    # modified: /analyze wires in log_video_entry
backend/app/main.py          # modified: lifespan calls init_db(); include history router

backend/tests/conftest.py         # autouse fixture: isolated per-test SQLite DB
backend/tests/history/
  __init__.py
  test_database.py
  test_models.py
  test_schemas.py
  test_service.py
  test_routes.py
backend/tests/test_main.py         # modified: two new tests for /analyze's auto-log side effect

backend/pyproject.toml       # modified: add sqlalchemy dependency
docker-compose.yml           # modified: named volume for backend/data
.gitignore                   # modified: ignore backend/data/*.db
backend/data/.gitkeep         # new: keeps the directory tracked

frontend/src/types.ts                       # modified: HistoryEntry, ManualEntryCreate types
frontend/src/api.ts                          # modified: getHistory, createHistoryEntry, deleteHistoryEntry
frontend/src/api.test.ts                     # new
frontend/src/components/HistoryView.tsx      # new
frontend/src/components/HistoryView.css      # new
frontend/src/components/HistoryView.test.tsx # new
frontend/src/components/ManualEntryForm.tsx      # new
frontend/src/components/ManualEntryForm.css      # new
frontend/src/components/ManualEntryForm.test.tsx # new
frontend/src/App.tsx        # modified: 'history' status + nav
frontend/src/App.css        # modified: nav styles
frontend/src/App.test.tsx   # modified: nav test
```

---

## Task 1: Database setup

**Files:**
- Modify: `backend/pyproject.toml` (add `sqlalchemy` to `dependencies`)
- Create: `backend/app/history/__init__.py` (empty)
- Create: `backend/app/history/database.py`
- Test: `backend/tests/history/__init__.py` (empty)
- Test: `backend/tests/history/test_database.py`

**Interfaces:**
- Produces (used by every later task): `class Base(DeclarativeBase)`; `build_engine(db_path: Path) -> Engine`; module-level `engine: Engine`, `SessionLocal: sessionmaker`; `init_db() -> None`; `get_session() -> Generator[Session, None, None]` (FastAPI dependency).

- [ ] **Step 1: Add sqlalchemy to backend dependencies**

Edit `backend/pyproject.toml`'s `dependencies` list:

```toml
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "python-multipart>=0.0.12",
  "sqlalchemy>=2.0",
  "cv-engine",
]
```

Run: `cd backend && uv sync` (or `pip install -e .` if not using uv)
Expected: installs sqlalchemy into the backend environment without error.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/history/__init__.py` (empty file).

Create `backend/tests/history/test_database.py`:

```python
from sqlalchemy import text

from app.history.database import build_engine


def test_build_engine_creates_missing_parent_directory(tmp_path) -> None:
    db_path = tmp_path / "nested" / "sub" / "test.db"
    assert not db_path.parent.exists()

    engine = build_engine(db_path)

    assert db_path.parent.exists()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    engine.dispose()


def test_build_engine_works_with_already_existing_directory(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    engine = build_engine(db_path)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    engine.dispose()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backend/tests/history/test_database.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.history'`.

- [ ] **Step 4: Write the implementation**

Create `backend/app/history/__init__.py` (empty).

Create `backend/app/history/database.py`:

```python
"""SQLite-backed persistence for workout history. One engine/session
factory, module-level for reuse across requests; get_session() is a
FastAPI dependency yielding one Session per request.

DEFAULT_DB_PATH is computed relative to this file so it resolves
correctly both locally (backend/data/formiq.db) and inside the Docker
image, where backend/app is copied to /app/app (three parents up from
here is /app, giving /app/data/formiq.db — see
infra/docker/backend.Dockerfile).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "formiq.db"


class Base(DeclarativeBase):
    pass


def build_engine(db_path: Path) -> Engine:
    """Create a SQLite engine at db_path, creating its parent directory
    if missing (SQLite requires the directory to exist before it can
    open/create the file)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


engine = build_engine(DEFAULT_DB_PATH)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables that don't already exist. Called once at app
    startup (see app.main's lifespan)."""
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: one Session per request, closed afterward."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backend/tests/history/test_database.py -v`
Expected: PASS (2 tests). Note: importing `app.history.database` creates `backend/data/` locally as a side effect (the module-level `engine = build_engine(DEFAULT_DB_PATH)` line) — this is expected per the design (Task 7 gitignores the `.db` file).

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/history backend/tests/history
git commit -m "feat: add SQLite database setup for workout history"
```

---

## Task 2: WorkoutEntry model

**Files:**
- Create: `backend/app/history/models.py`
- Test: `backend/tests/history/test_models.py`

**Interfaces:**
- Consumes: `app.history.database.Base` (Task 1).
- Produces (used by Tasks 3–6): `class WorkoutEntry(Base)` with columns `id, exercise, date, source, created_at, sets, reps, weight, notes, rep_count, avg_form_accuracy, rep_scores`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/history/test_models.py`:

```python
from datetime import date, datetime, timezone

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
            created_at=datetime.now(timezone.utc),
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
            created_at=datetime.now(timezone.utc),
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/history/test_models.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.history.models'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/history/models.py`:

```python
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
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # manual entries only
    sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    # video entries only
    rep_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_form_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    rep_scores: Mapped[list | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/history/test_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/history/models.py backend/tests/history/test_models.py
git commit -m "feat: add WorkoutEntry ORM model"
```

---

## Task 3: Pydantic schemas

**Files:**
- Create: `backend/app/history/schemas.py`
- Test: `backend/tests/history/test_schemas.py`

**Interfaces:**
- Consumes: `app.schemas.analysis.Exercise, RepScore`.
- Produces (used by Tasks 4–6): `class ManualEntryCreate(BaseModel)` (`exercise, date, sets, reps, weight=None, notes=None`, `sets`/`reps` require `>= 1`); `class HistoryEntry(BaseModel)` (`from_attributes=True`; all `WorkoutEntry` columns, `rep_scores: list[RepScore] | None`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/history/test_schemas.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/history/test_schemas.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.history.schemas'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/history/schemas.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/history/test_schemas.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/history/schemas.py backend/tests/history/test_schemas.py
git commit -m "feat: add ManualEntryCreate/HistoryEntry schemas"
```

---

## Task 4: Service layer

**Files:**
- Create: `backend/app/history/service.py`
- Test: `backend/tests/history/test_service.py`

**Interfaces:**
- Consumes: `app.history.models.WorkoutEntry` (Task 2); `app.history.schemas.ManualEntryCreate` (Task 3); `app.schemas.analysis.AnalysisResponse, Exercise`.
- Produces (used by Task 5's router and Task 6's `/analyze` wiring): `create_entry(session, data: ManualEntryCreate) -> WorkoutEntry`; `list_entries(session) -> list[WorkoutEntry]`; `delete_entry(session, entry_id: int) -> bool`; `log_video_entry(session, exercise: Exercise, response: AnalysisResponse) -> WorkoutEntry`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/history/test_service.py`:

```python
from datetime import date

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.history import service
from app.history.database import Base, build_engine
from app.history.schemas import ManualEntryCreate
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/history/test_service.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'app.history.service'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/history/service.py`:

```python
"""Business logic for reading/writing workout history — kept separate
from the API routes so it can be unit-tested without spinning up
FastAPI, and reused by both the manual-entry endpoints and /analyze's
auto-log side effect.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

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
        created_at=datetime.now(timezone.utc),
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
        date=date.today(),
        source="video",
        created_at=datetime.now(timezone.utc),
        rep_count=rep_count,
        avg_form_accuracy=avg_form_accuracy,
        rep_scores=[rep.model_dump(mode="json") for rep in response.reps],
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/history/test_service.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/history/service.py backend/tests/history/test_service.py
git commit -m "feat: add workout history service layer"
```

---

## Task 5: History router + wired into the app

**Files:**
- Create: `backend/app/api/history.py`
- Create: `backend/tests/conftest.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/history/test_routes.py`

**Interfaces:**
- Consumes: `app.history.service` (Task 4); `app.history.database.get_session, build_engine, Base` (Task 1); `app.history.schemas.HistoryEntry, ManualEntryCreate` (Task 3); `app.history.models.WorkoutEntry` (Task 2).
- Produces (used by Task 6): `router: APIRouter` with `POST/GET /history`, `DELETE /history/{entry_id}`, mounted in `app.main.app`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/conftest.py` (shared fixture — this is not itself a "failing test" but is required before `test_routes.py` can run against an isolated DB; write it now so Step 3 below fails for the *right* reason, a missing router, not a missing fixture):

```python
"""Shared pytest fixtures: gives every test an isolated, per-test-function
SQLite DB by overriding the app's real history.database.get_session
dependency, so no test ever touches backend/data/formiq.db."""

import pytest
from sqlalchemy.orm import sessionmaker

from app.history.database import Base, build_engine, get_session
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_history_db(tmp_path):
    engine = build_engine(tmp_path / "test_history.db")
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_session():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    yield
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()
```

Create `backend/tests/history/test_routes.py`:

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_list_and_delete_round_trip() -> None:
    create_response = client.post(
        "/history",
        json={"exercise": "squat", "date": "2026-09-01", "sets": 3, "reps": 8, "weight": 100.0},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["exercise"] == "squat"
    assert created["source"] == "manual"
    entry_id = created["id"]

    list_response = client.get("/history")
    assert list_response.status_code == 200
    assert any(e["id"] == entry_id for e in list_response.json())

    delete_response = client.delete(f"/history/{entry_id}")
    assert delete_response.status_code == 204

    list_after_delete = client.get("/history")
    assert all(e["id"] != entry_id for e in list_after_delete.json())


def test_create_rejects_invalid_body() -> None:
    response = client.post(
        "/history", json={"exercise": "squat", "date": "2026-09-01", "sets": 0, "reps": 8}
    )
    assert response.status_code == 422


def test_delete_nonexistent_entry_returns_404() -> None:
    response = client.delete("/history/999999")
    assert response.status_code == 404


def test_list_is_empty_when_no_entries_exist() -> None:
    response = client.get("/history")
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/history/test_routes.py -v`
Expected: FAIL — `404 Not Found` for `/history` (no such router yet).

- [ ] **Step 3: Write the implementation**

Create `backend/app/api/history.py`:

```python
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
```

Modify `backend/app/main.py` to mount it and initialize the DB at startup:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.history import router as history_router
from app.api.routes import router
from app.history.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="FormIQ API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(history_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/history/test_routes.py -v`
Expected: PASS (4 tests).

Run the full backend suite to confirm the new `conftest.py` fixture doesn't break anything existing: `pytest backend/tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/history.py backend/app/main.py backend/tests/conftest.py backend/tests/history/test_routes.py
git commit -m "feat: add /history CRUD endpoints"
```

---

## Task 6: Auto-log video analyses

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_main.py` (add two tests)

**Interfaces:**
- Consumes: `app.history.service.log_video_entry` (Task 4); `app.history.database.get_session` (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_main.py` (below the existing tests):

```python
def test_analyze_auto_logs_history_entry() -> None:
    video_bytes = b"not a real video, scaffolding stub"
    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", video_bytes, "video/mp4")},
    )
    assert response.status_code == 200

    history_response = client.get("/history")
    assert history_response.status_code == 200
    entries = history_response.json()
    assert any(e["exercise"] == "squat" and e["source"] == "video" for e in entries)


def test_analyze_still_succeeds_if_history_logging_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import routes as routes_module

    def _raise(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(routes_module.service, "log_video_entry", _raise)

    response = client.post(
        "/analyze/squat",
        files={"video": ("clip.mp4", b"not a real video", "video/mp4")},
    )
    assert response.status_code == 200
    assert response.json()["exercise"] == "squat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_main.py -v`
Expected: `test_analyze_auto_logs_history_entry` FAILS (no entry created — `/analyze` doesn't log yet). `test_analyze_still_succeeds_if_history_logging_fails` FAILS at `monkeypatch.setattr` — `routes_module` has no attribute `service` yet.

- [ ] **Step 3: Write the implementation**

Modify `backend/app/api/routes.py`:

```python
import logging
import tempfile
from pathlib import Path

import cv_engine
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.history import service
from app.history.database import get_session
from app.schemas.analysis import AnalysisResponse, Exercise

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze/{exercise}", response_model=AnalysisResponse)
async def analyze(
    exercise: Exercise, video: UploadFile, session: Session = Depends(get_session)
) -> AnalysisResponse:
    suffix = Path(video.filename or "video.mp4").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await video.read())
        tmp.flush()
        frames = cv_engine.KeypointExtractor().extract(tmp.name)

    response = AnalysisResponse(exercise=exercise, frame_count=len(frames), reps=[], frames=frames)

    try:
        service.log_video_entry(session, exercise, response)
    except Exception:
        logger.warning(
            "Failed to auto-log history entry for %s analysis", exercise.value, exc_info=True
        )

    return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_main.py -v`
Expected: PASS (all tests, including the two new ones).

Run the full backend suite: `pytest backend/tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes.py backend/tests/test_main.py
git commit -m "feat: auto-log every analyzed video to workout history"
```

---

## Task 7: Docker volume + gitignore

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.gitignore`
- Create: `backend/data/.gitkeep`

- [ ] **Step 1: Add a named volume for backend data**

Modify `docker-compose.yml`:

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: infra/docker/backend.Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - backend_data:/app/data

  frontend:
    build:
      context: .
      dockerfile: infra/docker/frontend.Dockerfile
    ports:
      - "5173:80"
    depends_on:
      - backend

volumes:
  backend_data:
```

(`/app/data` matches `DEFAULT_DB_PATH` from Task 1: `infra/docker/backend.Dockerfile` copies `backend/app` to `/app/app`, so three parents up from `/app/app/history/database.py` is `/app`.)

- [ ] **Step 2: Verify the compose file is valid**

Run: `docker compose config > /dev/null`
Expected: exits `0` with no error output.

- [ ] **Step 3: Gitignore the SQLite file, keep the directory tracked**

Add to `.gitignore`, under the existing `# Python` section:

```
backend/data/*.db
```

Create `backend/data/.gitkeep` (empty file).

- [ ] **Step 4: Verify the DB file is ignored but .gitkeep is tracked**

Run: `git status --porcelain backend/data`
Expected: only `backend/data/.gitkeep` shows as untracked/new (the `.db` file created by earlier tasks' test/import runs does not appear).

Run: `git check-ignore backend/data/formiq.db`
Expected: prints `backend/data/formiq.db` (confirms it's ignored). If the file doesn't exist yet in your checkout, this step is a no-op — the pattern still applies once it's created.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .gitignore backend/data/.gitkeep
git commit -m "chore: persist workout history DB across container restarts"
```

---

## Task 8: Frontend types + API client

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Test: `frontend/src/api.test.ts`

**Interfaces:**
- Produces (used by Tasks 9–10): types `HistoryEntry`, `ManualEntryCreate`; functions `getHistory(): Promise<HistoryEntry[]>`, `createHistoryEntry(data: ManualEntryCreate): Promise<HistoryEntry>`, `deleteHistoryEntry(id: number): Promise<void>`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/api.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest'
import { createHistoryEntry, deleteHistoryEntry, getHistory } from './api'
import type { HistoryEntry, ManualEntryCreate } from './types'

const sampleEntry: HistoryEntry = {
  id: 1,
  exercise: 'squat',
  date: '2026-09-01',
  source: 'manual',
  created_at: '2026-09-01T12:00:00Z',
  sets: 3,
  reps: 8,
  weight: 100,
  notes: null,
  rep_count: null,
  avg_form_accuracy: null,
  rep_scores: null,
}

describe('getHistory', () => {
  it('returns parsed history entries on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => [sampleEntry] }),
    )
    const entries = await getHistory()
    expect(entries).toEqual([sampleEntry])
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: 'Server Error' }),
    )
    await expect(getHistory()).rejects.toThrow('Failed to load history')
  })
})

describe('createHistoryEntry', () => {
  it('posts the payload and returns the created entry', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => sampleEntry })
    vi.stubGlobal('fetch', fetchMock)

    const payload: ManualEntryCreate = { exercise: 'squat', date: '2026-09-01', sets: 3, reps: 8 }
    const result = await createHistoryEntry(payload)

    expect(result).toEqual(sampleEntry)
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/history'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 422, statusText: 'Unprocessable Entity' }),
    )
    await expect(
      createHistoryEntry({ exercise: 'squat', date: '2026-09-01', sets: 3, reps: 8 }),
    ).rejects.toThrow('Failed to save entry')
  })
})

describe('deleteHistoryEntry', () => {
  it('sends a DELETE request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    await deleteHistoryEntry(1)

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/history/1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('throws when the response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 404, statusText: 'Not Found' }),
    )
    await expect(deleteHistoryEntry(999)).rejects.toThrow('Failed to delete entry')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- api.test.ts`
Expected: FAIL — `HistoryEntry`/`ManualEntryCreate` types and `getHistory`/`createHistoryEntry`/`deleteHistoryEntry` don't exist yet (TypeScript/import error).

- [ ] **Step 3: Write the implementation**

Add to `frontend/src/types.ts` (after the existing `AnalysisResponse` interface):

```typescript
export interface HistoryEntry {
  id: number
  exercise: Exercise
  date: string
  source: 'manual' | 'video'
  created_at: string
  sets: number | null
  reps: number | null
  weight: number | null
  notes: string | null
  rep_count: number | null
  avg_form_accuracy: number | null
  rep_scores: RepScore[] | null
}

export interface ManualEntryCreate {
  exercise: Exercise
  date: string
  sets: number
  reps: number
  weight?: number | null
  notes?: string | null
}
```

Rewrite `frontend/src/api.ts`:

```typescript
import type { AnalysisResponse, Exercise, HistoryEntry, ManualEntryCreate } from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export async function checkHealth(): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/health`)
  return response.ok
}

export async function analyzeVideo(exercise: Exercise, video: File): Promise<AnalysisResponse> {
  const formData = new FormData()
  formData.append('video', video)

  const response = await fetch(`${API_BASE_URL}/analyze/${exercise}`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    throw new Error(`Analysis failed: ${response.status} ${response.statusText}`)
  }

  return (await response.json()) as AnalysisResponse
}

export async function getHistory(): Promise<HistoryEntry[]> {
  const response = await fetch(`${API_BASE_URL}/history`)
  if (!response.ok) {
    throw new Error(`Failed to load history: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as HistoryEntry[]
}

export async function createHistoryEntry(data: ManualEntryCreate): Promise<HistoryEntry> {
  const response = await fetch(`${API_BASE_URL}/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error(`Failed to save entry: ${response.status} ${response.statusText}`)
  }
  return (await response.json()) as HistoryEntry
}

export async function deleteHistoryEntry(id: number): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/history/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Failed to delete entry: ${response.status} ${response.statusText}`)
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- api.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat: add history types and API client functions"
```

---

## Task 9: HistoryView component

**Files:**
- Create: `frontend/src/components/HistoryView.tsx`
- Create: `frontend/src/components/HistoryView.css`
- Test: `frontend/src/components/HistoryView.test.tsx`

**Interfaces:**
- Consumes: `getHistory, deleteHistoryEntry` (Task 8); `ManualEntryForm` (Task 10 — written first as a stub-free real component in Task 10, but `HistoryView` imports it here, so implement Task 10 immediately after this task, before running `HistoryView`'s own suite standalone if it fails to resolve the import. Both are done within this plan before either is committed as "final" — see Step 3's note.).
- Produces: `export function HistoryView()`.

> **Note on task ordering:** `HistoryView` composes `ManualEntryForm`. Do Task 10 (`ManualEntryForm`) before running this task's test, or write both files' implementations before the "verify it passes" step of either. The plan lists them as separate tasks for review granularity, not strict sequencing — the executor should treat Tasks 9 and 10 as a pair.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/HistoryView.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HistoryView } from './HistoryView'
import type { HistoryEntry } from '../types'

const manualEntry: HistoryEntry = {
  id: 1,
  exercise: 'squat',
  date: '2026-09-01',
  source: 'manual',
  created_at: '2026-09-01T12:00:00Z',
  sets: 3,
  reps: 8,
  weight: 100,
  notes: null,
  rep_count: null,
  avg_form_accuracy: null,
  rep_scores: null,
}

const videoEntry: HistoryEntry = {
  id: 2,
  exercise: 'pushup',
  date: '2026-09-02',
  source: 'video',
  created_at: '2026-09-02T12:00:00Z',
  sets: null,
  reps: null,
  weight: null,
  notes: null,
  rep_count: 5,
  avg_form_accuracy: 0.85,
  rep_scores: [],
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => [manualEntry, videoEntry] }),
  )
})

describe('HistoryView', () => {
  it('renders fetched manual and video entries with formatted detail', async () => {
    render(<HistoryView />)

    await waitFor(() => expect(screen.getByText('3 × 8 @ 100')).toBeInTheDocument())
    expect(screen.getByText('5 reps · 85% avg form')).toBeInTheDocument()
  })

  it('shows an empty message when there are no entries', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    render(<HistoryView />)
    await waitFor(() => expect(screen.getByText(/no workouts logged yet/i)).toBeInTheDocument())
  })

  it('removes an entry from the list when its delete button is clicked', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [manualEntry, videoEntry] })
      .mockResolvedValueOnce({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    render(<HistoryView />)
    await waitFor(() => expect(screen.getByText('3 × 8 @ 100')).toBeInTheDocument())

    fireEvent.click(screen.getByLabelText('Delete entry from 2026-09-01'))

    await waitFor(() => expect(screen.queryByText('3 × 8 @ 100')).not.toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- HistoryView.test.tsx`
Expected: FAIL — `./HistoryView` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/HistoryView.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { deleteHistoryEntry, getHistory } from '../api'
import type { HistoryEntry } from '../types'
import { ManualEntryForm } from './ManualEntryForm'
import './HistoryView.css'

function formatEntry(entry: HistoryEntry): string {
  if (entry.source === 'manual') {
    const setsReps = `${entry.sets} × ${entry.reps}`
    return entry.weight != null ? `${setsReps} @ ${entry.weight}` : setsReps
  }
  if (entry.rep_count === null || entry.rep_count === 0) {
    return 'no reps detected'
  }
  const accuracy =
    entry.avg_form_accuracy != null ? `${Math.round(entry.avg_form_accuracy * 100)}%` : null
  return accuracy ? `${entry.rep_count} reps · ${accuracy} avg form` : `${entry.rep_count} reps`
}

export function HistoryView() {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refetch = useCallback(() => {
    getHistory()
      .then(setEntries)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load history'))
  }, [])

  useEffect(() => {
    refetch()
  }, [refetch])

  const handleDelete = async (id: number) => {
    await deleteHistoryEntry(id)
    setEntries((prev) => (prev ? prev.filter((entry) => entry.id !== id) : prev))
  }

  const handleCreated = (entry: HistoryEntry) => {
    setEntries((prev) => (prev ? [entry, ...prev] : [entry]))
  }

  return (
    <div className="history-view">
      <ManualEntryForm onCreated={handleCreated} />

      {error && <p className="error">{error}</p>}
      {entries === null && !error && <p className="history-view__loading">Loading history…</p>}
      {entries !== null && entries.length === 0 && (
        <p className="history-view__empty">No workouts logged yet.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <ul className="history-view__list">
          {entries.map((entry) => (
            <li key={entry.id} className="history-view__row">
              <span className="history-view__date">{entry.date}</span>
              <span className="history-view__exercise">{entry.exercise.replace('_', ' ')}</span>
              <span className="history-view__detail">{formatEntry(entry)}</span>
              <span className="history-view__source">{entry.source}</span>
              <button
                type="button"
                className="history-view__delete"
                onClick={() => handleDelete(entry.id)}
                aria-label={`Delete entry from ${entry.date}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

Create `frontend/src/components/HistoryView.css`:

```css
.history-view {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.history-view__loading,
.history-view__empty {
  color: var(--text-muted);
  font-size: 14px;
}

.history-view__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-view__row {
  display: grid;
  grid-template-columns: auto auto 1fr auto auto;
  align-items: center;
  gap: 12px;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 14px;
}

.history-view__date {
  color: var(--text-muted);
  font-size: 12px;
}

.history-view__exercise {
  font-weight: 600;
  text-transform: capitalize;
}

.history-view__source {
  color: var(--text-muted);
  font-size: 12px;
  text-transform: uppercase;
}

.history-view__delete {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.history-view__delete:hover {
  color: var(--danger);
}
```

(`ManualEntryForm` is implemented in Task 10 — write that file now too, before running the test below, since this component imports it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- HistoryView.test.tsx`
Expected: PASS (3 tests) — once Task 10's `ManualEntryForm.tsx` also exists.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/HistoryView.tsx frontend/src/components/HistoryView.css frontend/src/components/HistoryView.test.tsx
git commit -m "feat: add HistoryView component"
```

---

## Task 10: ManualEntryForm component

**Files:**
- Create: `frontend/src/components/ManualEntryForm.tsx`
- Create: `frontend/src/components/ManualEntryForm.css`
- Test: `frontend/src/components/ManualEntryForm.test.tsx`

**Interfaces:**
- Consumes: `createHistoryEntry` (Task 8); `EXERCISES` (existing, `frontend/src/types.ts`).
- Produces (consumed by Task 9's `HistoryView`): `export function ManualEntryForm({ onCreated }: { onCreated: (entry: HistoryEntry) => void })`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ManualEntryForm.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ManualEntryForm } from './ManualEntryForm'
import type { HistoryEntry } from '../types'

const createdEntry: HistoryEntry = {
  id: 1,
  exercise: 'squat',
  date: '2026-09-01',
  source: 'manual',
  created_at: '2026-09-01T12:00:00Z',
  sets: 3,
  reps: 8,
  weight: 100,
  notes: null,
  rep_count: null,
  avg_form_accuracy: null,
  rep_scores: null,
}

describe('ManualEntryForm', () => {
  it('submits the form values and calls onCreated with the new entry', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => createdEntry })
    vi.stubGlobal('fetch', fetchMock)
    const onCreated = vi.fn()

    render(<ManualEntryForm onCreated={onCreated} />)

    fireEvent.change(screen.getByLabelText('Sets'), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText('Reps'), { target: { value: '8' } })
    fireEvent.change(screen.getByLabelText('Weight'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: /add entry/i }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(createdEntry))

    const [, requestInit] = fetchMock.mock.calls[0]
    const body = JSON.parse(requestInit.body as string)
    expect(body).toMatchObject({ sets: 3, reps: 8, weight: 100 })
  })

  it('shows an error message when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 422, statusText: 'Unprocessable Entity' }),
    )
    render(<ManualEntryForm onCreated={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /add entry/i }))

    await waitFor(() => expect(screen.getByText(/failed to save entry/i)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- ManualEntryForm.test.tsx`
Expected: FAIL — `./ManualEntryForm` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/ManualEntryForm.tsx`:

```tsx
import { useState } from 'react'
import type { FormEvent } from 'react'
import { createHistoryEntry } from '../api'
import { EXERCISES } from '../types'
import type { Exercise, HistoryEntry } from '../types'
import './ManualEntryForm.css'

interface ManualEntryFormProps {
  onCreated: (entry: HistoryEntry) => void
}

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function ManualEntryForm({ onCreated }: ManualEntryFormProps) {
  const [exercise, setExercise] = useState<Exercise>(EXERCISES[0])
  const [date, setDate] = useState(today())
  const [sets, setSets] = useState('3')
  const [reps, setReps] = useState('8')
  const [weight, setWeight] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    try {
      const entry = await createHistoryEntry({
        exercise,
        date,
        sets: Number(sets),
        reps: Number(reps),
        weight: weight === '' ? null : Number(weight),
        notes: notes === '' ? null : notes,
      })
      onCreated(entry)
      setWeight('')
      setNotes('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save entry')
    }
  }

  return (
    <form onSubmit={handleSubmit} className="manual-entry-form">
      <div className="manual-entry-form__label">Log a workout</div>

      <select
        aria-label="Exercise"
        value={exercise}
        onChange={(event) => setExercise(event.target.value as Exercise)}
      >
        {EXERCISES.map((option) => (
          <option key={option} value={option}>
            {option.replace('_', ' ')}
          </option>
        ))}
      </select>

      <input
        aria-label="Date"
        type="date"
        value={date}
        onChange={(event) => setDate(event.target.value)}
      />
      <input
        aria-label="Sets"
        type="number"
        min={1}
        value={sets}
        onChange={(event) => setSets(event.target.value)}
      />
      <input
        aria-label="Reps"
        type="number"
        min={1}
        value={reps}
        onChange={(event) => setReps(event.target.value)}
      />
      <input
        aria-label="Weight"
        type="number"
        placeholder="Weight (optional)"
        value={weight}
        onChange={(event) => setWeight(event.target.value)}
      />
      <input
        aria-label="Notes"
        type="text"
        placeholder="Notes (optional)"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
      />

      <button type="submit" className="manual-entry-form__submit">
        Add entry
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
```

Create `frontend/src/components/ManualEntryForm.css`:

```css
.manual-entry-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
}

.manual-entry-form__label {
  flex-basis: 100%;
  font-weight: 600;
  color: var(--text-h);
  margin-bottom: 4px;
}

.manual-entry-form input,
.manual-entry-form select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 8px;
  font-size: 13px;
}

.manual-entry-form__submit {
  background: var(--accent-gradient);
  border: none;
  border-radius: 6px;
  color: var(--bg);
  font-weight: 600;
  padding: 6px 14px;
  cursor: pointer;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- ManualEntryForm.test.tsx`
Expected: PASS (2 tests).

Now also run Task 9's suite, since `HistoryView` depends on this file: `cd frontend && npm test -- HistoryView.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ManualEntryForm.tsx frontend/src/components/ManualEntryForm.css frontend/src/components/ManualEntryForm.test.tsx
git commit -m "feat: add ManualEntryForm component"
```

---

## Task 11: Wire history into App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.css`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `HistoryView` (Task 9).

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/App.test.tsx`, inside the existing `describe('App', ...)` block:

```tsx
  it('switches to the History view and back to idle via the nav', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (typeof url === 'string' && url.includes('/history')) {
          return Promise.resolve({ ok: true, json: async () => [] })
        }
        return Promise.resolve({ ok: true, json: async () => mockAnalysisResponse })
      }),
    )

    render(<App />)
    await waitFor(() => expect(screen.getByText(/Backend: online/)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    await screen.findByText(/no workouts logged yet/i)

    fireEvent.click(screen.getByRole('button', { name: 'New Analysis' }))
    expect(screen.getByLabelText(/drop a video/i)).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- App.test.tsx`
Expected: FAIL — no button named `History`/`New Analysis` exists yet.

- [ ] **Step 3: Write the implementation**

Modify `frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { analyzeVideo, checkHealth } from './api'
import type { AnalysisResponse, Exercise } from './types'
import { UploadForm } from './components/UploadForm'
import { AnalyzingView } from './components/AnalyzingView'
import { ResultsView } from './components/ResultsView'
import { HistoryView } from './components/HistoryView'
import './App.css'

type Status = 'idle' | 'analyzing' | 'results' | 'history'

function App() {
  const [backendHealthy, setBackendHealthy] = useState<boolean | null>(null)
  const [status, setStatus] = useState<Status>('idle')
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [video, setVideo] = useState<File | null>(null)
  const [result, setResult] = useState<AnalysisResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    checkHealth()
      .then(setBackendHealthy)
      .catch(() => setBackendHealthy(false))
  }, [])

  const handleSubmit = async (selectedExercise: Exercise, selectedVideo: File) => {
    setExercise(selectedExercise)
    setVideo(selectedVideo)
    setStatus('analyzing')
    setError(null)
    try {
      const response = await analyzeVideo(selectedExercise, selectedVideo)
      setResult(response)
      setStatus('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setStatus('idle')
      setResult(null)
      setVideo(null)
    }
  }

  const handleReset = () => {
    setStatus('idle')
    setResult(null)
    setVideo(null)
    setExercise(null)
    setError(null)
  }

  return (
    <main className="app">
      <h1>FormIQ</h1>
      <nav className="app__nav">
        <button
          type="button"
          className={`app__nav-link ${status !== 'history' ? 'app__nav-link--active' : ''}`.trim()}
          onClick={handleReset}
        >
          New Analysis
        </button>
        <button
          type="button"
          className={`app__nav-link ${status === 'history' ? 'app__nav-link--active' : ''}`.trim()}
          onClick={() => setStatus('history')}
        >
          History
        </button>
      </nav>
      <p className="status">
        Backend: {backendHealthy === null ? 'checking…' : backendHealthy ? 'online' : 'offline'}
      </p>

      {status === 'idle' && <UploadForm onSubmit={handleSubmit} />}
      {status === 'analyzing' && exercise && <AnalyzingView exercise={exercise} />}
      {status === 'results' && result && video && (
        <ResultsView response={result} video={video} onReset={handleReset} />
      )}
      {status === 'history' && <HistoryView />}

      {error && <p className="error">{error}</p>}
    </main>
  )
}

export default App
```

Add to `frontend/src/App.css`:

```css
.app__nav {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.app__nav-link {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-muted);
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
}

.app__nav-link--active {
  color: var(--text-h);
  border-color: var(--accent-cyan);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- App.test.tsx`
Expected: PASS (all tests, including the new one).

Run the full frontend suite: `cd frontend && npm test`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.css frontend/src/App.test.tsx
git commit -m "feat: add History nav and view to App"
```

---

## Final verification

- [ ] `pytest backend/tests -v` — all backend tests pass.
- [ ] `ruff check backend` — clean.
- [ ] `cd frontend && npm test` — all frontend tests pass.
- [ ] `docker compose up` — manually: submit a manual entry via the History view, confirm it appears; upload/analyze a video, switch to History, confirm a video-sourced row appears automatically; delete an entry and confirm it's gone; restart the containers and confirm entries persisted.
