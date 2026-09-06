# Workout history / exercise tracking over time

Status: Draft for review
Date: 2026-09-05

## Goal

FormIQ currently analyzes one uploaded video at a time and discards
everything afterward — the video is written to a temp file, processed,
and deleted before the response is returned (see
[backend/app/api/routes.py](../../../backend/app/api/routes.py)); nothing
is persisted anywhere, and the frontend holds one result in local
component state until it's reset. This spec adds a workout history: a
durable log of exercises performed over time, viewable as a list,
populated two ways —

1. **Automatically**, every time `/analyze/{exercise}` successfully
   processes a video.
2. **Manually**, when the user logs a workout directly (sets, reps,
   weight) without uploading a video.

Single-user, no login — there is no auth/account concept anywhere in
this repo today, and none is introduced here.

## Non-goals

- Auth / multi-user support. All history is global to the one deployment.
- Editing an existing entry (create + delete only).
- Persisting or replaying the original uploaded video. `/analyze` stays
  fully ephemeral otherwise — history stores derived stats, not media.
- Trend charts, aggregate analytics, or a dashboard. A chronological
  list is the entire UI surface this spec covers.
- Pagination. Single-user history is expected to stay small; add it
  later if it becomes a real problem.
- Populating `rep_count` / `avg_form_accuracy` with real values —
  `/analyze`'s `reps` field is always `[]` until the separate
  rep-segmentation/scoring sub-project
  ([2026-08-29-backend-rep-scoring-design.md](2026-08-29-backend-rep-scoring-design.md))
  ships. Auto-logged video entries will simply show 0 reps / no
  form-accuracy until then — no schema change needed once that ships,
  since the column already exists and starts getting populated by
  whatever `pipeline.analyze()` returns.
- AWS ECS deployment considerations for the new SQLite file (tracked
  separately in `CLAUDE.md`'s infra sub-project; this spec only adds a
  `docker-compose.yml` volume mount for local/dev use).

## Architecture

New package `backend/app/history/`:

```
backend/app/history/
  __init__.py
  database.py     # SQLAlchemy engine + session factory + init_db()
  models.py       # WorkoutEntry ORM model
  schemas.py      # Pydantic request/response models (from_attributes=True)
  service.py      # create_entry, list_entries, delete_entry, log_video_entry
```

New router `backend/app/api/history.py`, mounted in `backend/app/main.py`
alongside the existing router:

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/history` | `ManualEntryCreate` | `HistoryEntry` |
| `GET` | `/history` | — | `list[HistoryEntry]` |
| `DELETE` | `/history/{entry_id}` | — | `204 No Content` |

`backend/app/api/routes.py`'s `/analyze/{exercise}` handler gains one
call after building `AnalysisResponse`: `history.service.log_video_entry(exercise,
response)`. This call is wrapped in try/except and logged on failure —
**a history-logging failure must never turn a successful analysis into
an error response**, mirroring the fail-soft convention already
established for `pipeline.analyze()` in the rep-scoring spec.

New dependency: `sqlalchemy>=2.0`, added to `backend/pyproject.toml`.
No async driver needed — SQLite + the sync `sqlalchemy` engine is
sufficient at this scale; FastAPI runs sync route bodies (or DB calls
within them) in a thread pool automatically.

### Storage

SQLite file at `backend/data/formiq.db`. The `backend/data/` directory
is created by `database.py` on startup if missing; the `.db` file inside
it is gitignored (add `backend/data/*.db` to `.gitignore`) while the
directory itself is tracked via a `.gitkeep`. It is also mounted as a
named Docker volume in `docker-compose.yml`'s `backend` service, so
entries survive `docker compose down`/`up` cycles.

`database.py` exposes `init_db()` (creates tables if they don't exist —
called once from `main.py`'s startup) and a `get_session()` FastAPI
dependency (`yield`s a session, closes it after the request), matching
the standard SQLAlchemy + FastAPI dependency-injection pattern. No
migration tool (Alembic, etc.) — one table, `init_db()`'s
`create_all()` is sufficient for this scope.

## Data model

```python
class WorkoutEntry(Base):
    __tablename__ = "workout_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise: Mapped[str]          # Exercise enum value, e.g. "squat"
    date: Mapped[date]
    source: Mapped[str]            # "manual" | "video"
    created_at: Mapped[datetime]   # server-set, UTC, on insert

    # manual entries only (NULL for source="video")
    sets: Mapped[int | None]
    reps: Mapped[int | None]       # reps per set
    weight: Mapped[float | None]   # NULL for bodyweight exercises
    notes: Mapped[str | None]

    # video entries only (NULL for source="manual")
    rep_count: Mapped[int | None]
    avg_form_accuracy: Mapped[float | None]
    rep_scores: Mapped[list | None] = mapped_column(JSON)  # RepScore[]-shaped dicts
```

One table for both sources (rather than two tables or a
polymorphic/inheritance model) because the two sources share the same
identity/list semantics (exercise, date, "how did it go") and the list
view renders them side by side — a `source` discriminator with nullable
columns is simpler than a join for a dataset this small, and avoids
premature schema complexity for a single-user log.

### Pydantic schemas (`backend/app/history/schemas.py`)

```python
class ManualEntryCreate(BaseModel):
    exercise: Exercise             # reuse existing enum from app.schemas.analysis
    date: date
    sets: int
    reps: int
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

`ManualEntryCreate` validates `sets >= 1` and `reps >= 1` (Pydantic
`Field(ge=1)`) — a manual entry describing zero sets or reps isn't a
meaningful log entry.

## Service layer (`backend/app/history/service.py`)

- `create_entry(session, data: ManualEntryCreate) -> WorkoutEntry` —
  inserts a `source="manual"` row from validated input.
- `list_entries(session) -> list[WorkoutEntry]` — all rows, `ORDER BY
  date DESC, created_at DESC`.
- `delete_entry(session, entry_id: int) -> bool` — deletes by id,
  returns whether a row was found (route maps `False` to `404`).
- `log_video_entry(session, exercise: Exercise, response: AnalysisResponse)
  -> WorkoutEntry` — inserts a `source="video"` row: `date=today`,
  `rep_count=len(response.reps)`,
  `avg_form_accuracy=mean(r.form_accuracy for r in response.reps) if
  response.reps else None`, `rep_scores=[r.model_dump() for r in
  response.reps]`.

Keeping DB logic in a `service.py` (rather than inline in the route
handlers) matches this codebase's existing separation of routing from
logic (`routes.py` already delegates to `scoring.pipeline.analyze(...)`
per the rep-scoring spec) and keeps the routes thin enough to unit-test
the service functions directly against an in-memory DB without spinning
up FastAPI.

## API error handling

- `POST /history` with invalid body (e.g. `sets: 0`): FastAPI/Pydantic's
  standard `422` — no custom handling needed.
- `DELETE /history/{entry_id}` for a nonexistent id: `404`.
- `GET /history` never errors (empty DB → `[]`).
- `log_video_entry` failure (DB unavailable, disk full, etc.): caught in
  `routes.py`, logged at `warning` level, **the analysis response is
  still returned normally** — see Architecture above.

## Frontend

No router is introduced. `frontend/src/App.tsx`'s existing `Status`
union (`'idle' | 'analyzing' | 'results'`) gains a fourth value,
`'history'`, following the same pattern already used for the other
three views.

New components:

- `HistoryView.tsx` — on mount, `GET /history`; renders a chronological
  list. Each row shows date + exercise, then source-specific detail:
  manual rows show `sets × reps @ weight` (or just `sets × reps` if
  `weight` is null) plus `notes` if present; video rows show `rep_count`
  reps and `avg_form_accuracy` (formatted as a percentage) if present,
  otherwise "no reps detected" (matching `/analyze`'s existing
  zero-reps semantics). Each row has a delete action calling `DELETE
  /history/{id}` and removing it from local state on success.
- `ManualEntryForm.tsx` — controlled form: exercise `<select>` (reuse
  the same exercise list `UploadForm.tsx` already renders), date input
  (defaults to today), sets/reps number inputs, optional weight/notes.
  Submits via a new `createHistoryEntry()` call; on success, clears the
  form and prepends the new entry to `HistoryView`'s list (or triggers a
  refetch — implementation detail for the plan).
- A small header/nav (new `NavBar.tsx` or inline in `App.tsx`) with two
  actions: "New Analysis" (→ `'idle'`) and "History" (→ `'history'`),
  visible from every view.

`frontend/src/api.ts` gains:

```typescript
getHistory(): Promise<HistoryEntry[]>
createHistoryEntry(data: ManualEntryCreate): Promise<HistoryEntry>
deleteHistoryEntry(id: number): Promise<void>
```

New types (`frontend/src/types.ts` or wherever `RepScore`/
`AnalysisResponse` types currently live) mirroring the backend
`HistoryEntry`/`ManualEntryCreate` shapes exactly, matching this
codebase's existing convention of frontend types tracking backend
Pydantic schemas 1:1.

## Testing

Backend (`backend/tests/history/`):
- `test_service.py` — `create_entry`, `list_entries` ordering,
  `delete_entry` (found/not-found), `log_video_entry` (with reps present
  and with `reps=[]`), all against a temp/in-memory SQLite session
  (pytest fixture overriding `database.get_session`).
- `test_routes.py` — the three endpoints via FastAPI's `TestClient`:
  create → appears in list → delete → gone; `422` on invalid body;
  `404` on deleting a nonexistent id.
- `test_main.py` (existing file, extended) — one new test asserting that
  a successful `POST /analyze/{exercise}` produces a new `source="video"`
  row in history, and one test asserting a simulated `log_video_entry`
  failure (monkeypatched to raise) still returns a normal `200`
  `AnalysisResponse`.

Frontend: component tests for `HistoryView` (renders fetched entries,
delete removes a row) and `ManualEntryForm` (submits expected payload,
clears on success), matching the existing test style (e.g.
`mockReps.test.ts`).

## Summary of contract impact

No changes to `AnalysisResponse`, `RepScore`, or the `/analyze/{exercise}`
route's request/response shape — `log_video_entry` reads the existing
response, it doesn't alter it. New, additive contract: `POST|GET
/history`, `DELETE /history/{id}`, and the `HistoryEntry`/
`ManualEntryCreate` schemas defined above. New backend dependency:
`sqlalchemy`. New `docker-compose.yml` volume for `backend/data/`.
