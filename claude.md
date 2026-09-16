

Claude · MD
# FormIQ
 
## Project overview
FormIQ analyzes exercise form from video. A C++ engine (MediaPipe pose
models via LiteRT + OpenCV) extracts 33 pose keypoints at 30fps; a FastAPI
backend ingests video, runs rep-level analysis across 8 exercises, and
serves results to a React/TypeScript frontend. Deployed to AWS ECS via
Docker, built/released with GitHub Actions.
 
## Architecture
- `cv-engine/` — C++ keypoint extraction, exposed to Python via
  **pybind11** as an in-process extension module (no subprocess, no
  separate service). Real pipeline (not a stub): `VideoCapture` decodes +
  samples frames, `PoseDetector` (SSD anchor decode) finds a person,
  `RoiTracker` decides detect-vs-reuse, `LandmarkRegressor` regresses 33
  keypoints. Both models run via **LiteRT (TensorFlow Lite)'s C++
  interpreter** — not `cv::dnn`, which can't load MediaPipe's real
  detector model (unsupported `DENSIFY` op); OpenCV is still used for
  video/image ops and `NMSBoxes`. LiteRT is vendored via CMake
  `FetchContent` (pinned `v2.21.0`) — first configure/build is slow
  (10+ min, shallow-clones + compiles TensorFlow's `lite` subtree from
  source); subsequent builds reuse the built artifacts. This is the
  perf-critical path — ingestion must stay under 3s per video (typical-case
  target, not a hard gate — see
  `docs/superpowers/specs/2026-08-20-cv-engine-pose-extraction-design.md`).
- `backend/` — FastAPI. Imports the compiled `cv-engine` extension module
  directly. `/analyze/{exercise}` returns real `frame_count` AND real
  `reps` — `backend/app/scoring/` (landmark geometry, per-video signal
  normalization, a 4-phase REST/DRIVE/PEAK/RECOVER state machine,
  declarative per-exercise fault rules, a registry of all 8
  `ExerciseProfile`s) turns cv-engine's per-frame keypoints into rep
  boundaries and named-fault `form_accuracy` scores. See
  `docs/superpowers/specs/2026-08-29-backend-rep-scoring-design.md`
  (including its "Implementation notes" section — one known limitation:
  `bench_press`/`pullup`'s lockout-completion faults use an absolute
  threshold that's sensitive to a video's actual rest angle, not yet
  fixed). `backend/app/history/` (SQLite via
  SQLAlchemy — model, Pydantic schemas, service layer) plus the
  `/history` router give the app a durable, single-user workout log: every
  `/analyze` call auto-logs a `source="video"` entry (best-effort — a
  logging failure never turns a successful analysis into an error
  response) alongside `source="manual"` entries logged directly (sets,
  reps, weight, no video). DB file at `backend/data/formiq.db`
  (gitignored; `docker-compose.yml` mounts it as a named volume). See
  `docs/superpowers/specs/2026-09-05-workout-history-tracking-design.md`.
  Manual entries are also editable (`PATCH /history/{id}`, scoped to
  `source="manual"` only — video entries' derived fields stay
  read-only) and the whole history is exportable as CSV or JSON
  (`GET /history/export?format=csv|json`, `/export` deliberately
  declared before the `/{entry_id}` routes so FastAPI doesn't capture
  "export" as an int id). `HistoryEntry.created_at` is coerced to a
  UTC-aware value on read (SQLite drops tzinfo on read-back regardless
  of the column's `DateTime(timezone=True)` flag) — both the JSON and
  CSV export paths share this same `HistoryEntry` serialization, so
  their `created_at` formatting agrees. Alembic is set up
  (`backend/alembic/`) for future schema migrations, but nothing
  deploys `alembic upgrade head` yet — local dev/tests still use
  `init_db()`'s `Base.metadata.create_all()`; see
  `docs/superpowers/plans/2026-09-15-history-bounded-enhancements.md`.
- `frontend/` — React + TypeScript, consumes the FastAPI backend. Real
  upload → results UI (not the raw-JSON scaffold): `UploadForm` →
  `AnalyzingView` → `ResultsView` (real client-side video playback via
  `URL.createObjectURL`, color-coded rep timeline, per-rep cards). A
  `'history'` state alongside `idle`/`analyzing`/`results` in `App.tsx`
  (no router) reaches `HistoryView` (list, edit, delete, and an
  "Export CSV" link) and `ManualEntryForm` (log a workout without a
  video, or edit an existing manual entry in place).
  `ResultsView.tsx` renders `response.reps` directly — the old
  `mockReps.ts` mock-data fallback (used before backend scoring existed)
  has been deleted along with `mockReps.test.ts`, now that backend scoring
  is real. `HistoryView` already read `response.reps` directly, so both
  views now agree on the same real data with no mock layer anywhere.
- `infra/` — Dockerfiles, ECS task defs, GitHub Actions workflows. AWS
  ECS/Terraform/CI-CD deployment was fully designed (backend-only scope,
  Terraform applied manually, GitHub OIDC, Fargate w/ public IP, no ALB)
  but the design was never written to a spec file or implemented — treat
  `infra/ecs/backend-task-def.json` as still placeholder
  (`<ACCOUNT_ID>`/`<REGION>`), not deployed anywhere yet.
## Contracts (do not change without updating all consumers)
- Keypoint output: 33 landmarks, each `{x, y, z, visibility}`, per frame.
  Defined in `cv-engine/include/keypoints.h` — treat this struct as the
  source of truth; Python bindings must mirror it exactly.
- API response shape for rep analysis: see `backend/app/schemas/`.
## Build & test
- C++: CMake + pybind11 + scikit-build-core. Build with
  `cmake --build cv-engine/build`. Run C++ tests: `ctest` from
  `cv-engine/build`. If `find_package(pybind11 CONFIG REQUIRED)` fails at
  configure time, the ambient Python has no discoverable pybind11 CMake
  config — pass `-Dpybind11_DIR=$(python3 -m pybind11 --cmakedir)`
  explicitly (CI's `cv-engine` and `backend` jobs already do this; it's
  only a local-dev gotcha). First configure/build also fetches+compiles
  LiteRT from source (10+ min) — see Architecture above.
- Python: `uv` (or `pip install -e .`) from `backend/`. Run tests:
  `pytest backend/tests`.
- Frontend: `npm run dev` / `npm test` from `frontend/`.
- Full stack locally: `docker compose up`.
## Conventions
- C++: header/source split under `include/`/`src/`, RAII, no raw `new`.
- Python: type hints required, Pydantic models for all API I/O, ruff for lint.
- TypeScript: strict mode on, functional components only.
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`...).
## Boundaries
- Never hand-edit generated pybind11 stub files.
- `.env` holds AWS creds and DB URL — never read/print it, never commit it.
- Don't touch `infra/` GitHub Actions secrets or AWS credentials directly.
## Current focus
Scaffolding phase is done — cv-engine's real pose extraction and the
frontend's real upload/results UI are both built and merged. Workout
history tracking and backend rep-segmentation + form-accuracy scoring are
also both built and merged — see `backend/` above, including the frontend
cleanup (`mockReps.ts` deleted, `ResultsView.tsx` reads `response.reps`
directly). A follow-up batch of five bounded history enhancements is also
built and merged: `created_at`'s timezone handling, editing existing
manual entries (backend + frontend), CSV/JSON export (backend +
frontend), Alembic migration tooling, and a frontend analyze→history
integration test — see `backend/`/`frontend/` above and
`docs/superpowers/plans/2026-09-15-history-bounded-enhancements.md`.
Remaining work:
- A known scoring limitation: `bench_press`/`pullup`'s lockout-completion
  faults use an absolute angle threshold sensitive to a video's actual
  rest angle, not just rep depth — see the rep-scoring spec's
  "Implementation notes" section for the fix approach (a percentile-
  relative threshold, not a constant).
- AWS ECS deployment (design approved in conversation, never written down
  — needs its own spec pass before implementation). Note this now has a
  new hard requirement it didn't have before: `backend/data/formiq.db`
  needs durable storage across task recycles (Fargate's local disk is
  ephemeral) — an EFS mount or a managed DB, plus access control on the
  unauthenticated `DELETE /history/{id}`.

Other scoped-but-not-started enhancements (no spec/plan yet for either):
trends/progress charts; auth/multi-user support (a likely prerequisite
for both trends-per-user and the ECS deployment's access-control needs).

Lower-priority, parked during the rep-scoring review: row's two dedicated
fault tests cross-fire each other's fault (target still fires correctly,
just not cleanly isolated); lunge's `knee_over_toe` uses `max_of` where
the spec says "working knee" (untested asymmetric case, latent not proven
broken); several horizontal-offset metrics can't express fault direction
(unsigned); `landmarks.py` isn't guarded against a malformed short
(&lt;33) landmark list.
 
