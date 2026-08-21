

Claude · MD
# FormIQ
 
## Project overview
FormIQ analyzes exercise form from video. A C++ engine (MediaPipe + OpenCV)
extracts 33 pose keypoints at 30fps; a FastAPI backend ingests video,
runs rep-level analysis across 8 exercises, and serves results to a
React/TypeScript frontend. Deployed to AWS ECS via Docker, built/released
with GitHub Actions.
 
## Architecture
- `cv-engine/` — C++ keypoint extraction (MediaPipe, OpenCV), exposed to
  Python via **pybind11** as an in-process extension module (no subprocess,
  no separate service). This is the perf-critical path — ingestion must
  stay under 3s per video.
- `backend/` — FastAPI. Imports the compiled `cv-engine` extension module
  directly, runs rep-segmentation + per-exercise form-accuracy scoring,
  returns rep-level JSON.
- `frontend/` — React + TypeScript, consumes the FastAPI backend.
- `infra/` — Dockerfiles, ECS task defs, GitHub Actions workflows.
## Contracts (do not change without updating all consumers)
- Keypoint output: 33 landmarks, each `{x, y, z, visibility}`, per frame.
  Defined in `cv-engine/include/keypoints.h` — treat this struct as the
  source of truth; Python bindings must mirror it exactly.
- API response shape for rep analysis: see `backend/app/schemas/`.
## Build & test
- C++: CMake + pybind11 + scikit-build-core. Build with
  `cmake --build cv-engine/build`. Run C++ tests: `ctest` from
  `cv-engine/build`.
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
Scaffolding phase — getting a minimal end-to-end path working
(empty pipeline → pybind11 binding → FastAPI stub endpoint → React fetch)
before implementing real CV/analysis logic.
 
