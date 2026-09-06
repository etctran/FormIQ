

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
  directly. `/analyze/{exercise}` returns real `frame_count` from the
  pipeline above; `reps` is still always `[]` — rep-segmentation and
  per-exercise form-accuracy scoring is not built yet (separate,
  not-yet-started sub-project). `backend/app/history/` (SQLite via
  SQLAlchemy — model, Pydantic schemas, service layer) plus the
  `/history` router give the app a durable, single-user workout log: every
  `/analyze` call auto-logs a `source="video"` entry (best-effort — a
  logging failure never turns a successful analysis into an error
  response) alongside `source="manual"` entries logged directly (sets,
  reps, weight, no video). DB file at `backend/data/formiq.db`
  (gitignored; `docker-compose.yml` mounts it as a named volume). See
  `docs/superpowers/specs/2026-09-05-workout-history-tracking-design.md`.
- `frontend/` — React + TypeScript, consumes the FastAPI backend. Real
  upload → results UI (not the raw-JSON scaffold): `UploadForm` →
  `AnalyzingView` → `ResultsView` (real client-side video playback via
  `URL.createObjectURL`, color-coded rep timeline, per-rep cards). A
  `'history'` state alongside `idle`/`analyzing`/`results` in `App.tsx`
  (no router) reaches `HistoryView` (list + delete) and `ManualEntryForm`
  (log a workout without a video).
  `frontend/src/mockReps.ts` is a deliberate, isolated mock-data fallback —
  `getReps()` returns the backend's real `reps` when non-empty, otherwise
  deterministic mock reps seeded from the video's real duration, so the UI
  could be built and reviewed against the real `RepScore` shape ahead of
  backend scoring existing. No other file branches on real-vs-mock; delete
  `mockReps.ts`/`mockReps.test.ts` and swap the one call site in
  `ResultsView.tsx` for `response.reps` once backend scoring ships. Note:
  `HistoryView` reads the real (always-empty) `reps` directly, so until
  that scoring work ships, the same analyzed video shows fabricated reps
  in `ResultsView` but "rep scoring not yet available" in History — a
  visible seam, not a bug, that closes automatically once `mockReps.ts` is
  deleted.
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
history tracking (`backend/app/history/`, `HistoryView`/`ManualEntryForm`)
is also built and merged — see `backend/` and `frontend/` above. Two
sub-projects remain, neither started:
- Backend rep-segmentation + per-exercise form-accuracy scoring (why
  `reps` is still always `[]`, and why `frontend/src/mockReps.ts` exists).
- AWS ECS deployment (design approved in conversation, never written down
  — needs its own spec pass before implementation). Note this now has a
  new hard requirement it didn't have before: `backend/data/formiq.db`
  needs durable storage across task recycles (Fargate's local disk is
  ephemeral) — an EFS mount or a managed DB, plus access control on the
  unauthenticated `DELETE /history/{id}`.
 
