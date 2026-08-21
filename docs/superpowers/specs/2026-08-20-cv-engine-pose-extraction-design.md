# CV Engine: Real Pose Keypoint Extraction

**Status:** Approved for planning
**Date:** 2026-08-20
**Scope:** `cv-engine/` only — replaces the `KeypointExtractor::Extract` stub with
real MediaPipe-model-based pose extraction. Backend rep-segmentation/scoring and
AWS deployment/CI are explicitly out of scope for this spec (separate sub-projects).

## Background

FormIQ's scaffolding phase wired an empty end-to-end path: `KeypointExtractor::Extract`
in `cv-engine/include/extractor.h` currently returns an empty frame sequence for any
input, so the FastAPI `/analyze/{exercise}` endpoint always responds with `reps: []`.
This spec designs the real extraction logic that produces the 33-landmark-per-frame
`Frame` sequence the rest of the pipeline (not yet built) will consume.

## Goals

- Real per-frame pose keypoint extraction from an uploaded video file, in-process
  (no subprocess, no separate service), matching the existing `Frame`/`Keypoint`
  contract in `cv-engine/include/keypoints.h`.
- Stay inside the existing CMake + pybind11 + scikit-build-core toolchain — no
  second build system.
- Typical-case latency in the low single-digit seconds for realistic inputs,
  without hard-gating on it in code.

## Non-goals

- Accuracy benchmarking / ground-truth validation harness (the "96% form accuracy"
  figure). Follow-up spec once extraction is working end-to-end.
- Rep segmentation or per-exercise form scoring (backend concern, separate spec).
- GPU inference. CPU-only for this pass.
- Multi-person handling. Single subject in frame is assumed, matching MediaPipe
  Pose's default single-person behavior.

## Key decisions

1. **Video input assumption:** clips of roughly 30–90 seconds at 30fps
   (900–2,700 native frames), e.g. a full exercise set rather than a single rep.
2. **Performance strategy:** use MediaPipe's lightest pose models, at a
   downsampled effective frame rate (see "Frame sampling" below). The ~3s
   ingestion figure (from `CLAUDE.md`) is treated as a typical-case target that
   this design aims for, **not** a hard deadline enforced in code — CPU pose
   inference on 900+ frames cannot be reliably gated to a hard 3s cap without
   GPU acceleration, which is out of scope here.
3. **Missing detection handling:** when no pose is detected in a sampled frame,
   that `Frame`'s `landmarks` is an **empty vector** (not zero-filled
   keypoints). Downstream consumers must explicitly handle gaps; this keeps the
   contract honest rather than fabricating visibility=0 data.
4. **MediaPipe integration path:** MediaPipe's official C++ library is built
   with Bazel, which has no clean interop with this repo's CMake/pybind11
   toolchain. Rather than vendoring a second build system, this design runs
   MediaPipe's **published pose-detector and pose-landmark TFLite models**
   directly through `cv::dnn` (OpenCV ≥ 4.8's TFLite import support,
   `cv::dnn::readNetFromTFLite`). We reimplement the orchestration MediaPipe's
   graph normally provides — detect → crop to ROI → regress landmarks → track
   ROI across frames — ourselves in C++. This runs Google's actual trained
   weights without linking Google's mediapipe library.
5. **Model asset acquisition:** the two `.tflite` model files (a few MB each)
   are fetched at build time from Google's model zoo (pinned version/URL), not
   committed to git. Fetched in both the Docker builder stage and local
   `cmake --build` (via the same script), so `ctest` and local dev work
   identically without requiring the files to be vendored.

## Architecture

```
video file (OpenCV VideoCapture)
   │  decode frames, sample every Nth frame (downsample from 30fps)
   ▼
PoseDetector          — cv::dnn net running MediaPipe's pose-detector model
   │                     outputs a person bounding box per sampled frame,
   │                     or nothing if no person detected
   ▼
RoiTracker             — holds last-known ROI; reuses/extrapolates it when a
   │                     sampled frame is skipped for re-detection, so we
   │                     don't re-run the (more expensive) detector every frame
   ▼
LandmarkRegressor      — cv::dnn net running MediaPipe's pose-landmark model,
   │                     cropped to the ROI → 33 {x,y,z,visibility} keypoints
   ▼
Frame{timestamp_sec, landmarks}   — landmarks empty if detection failed
```

### Frame sampling

Native decode stays at the video's real frame rate for accurate timestamps, but
pose inference runs on a fixed subset — roughly every 3rd–5th frame (~6–10fps
effective) rather than all 30fps. This is the primary lever that makes the
lightest model land near the 3s typical-case target on 30–90s clips.
`Frame.timestamp_sec` always reflects real video time regardless of which
frames were skipped for inference, so downstream rep-segmentation (a later
spec) isn't affected by the sampling strategy.

## Components (new/changed under `cv-engine/`)

- `include/pose_detector.h` / `src/pose_detector.cpp` — wraps a `cv::dnn::Net`
  loaded from the pose-detector TFLite model. Input: a frame (`cv::Mat`).
  Output: an optional ROI (bounding box), `std::nullopt` if nothing detected.
- `include/landmark_regressor.h` / `src/landmark_regressor.cpp` — wraps a
  `cv::dnn::Net` loaded from the pose-landmark TFLite model. Input: a frame
  cropped to an ROI. Output: 33 `Keypoint`s (may include low-visibility points
  if the model itself reports low confidence — that's a per-keypoint
  `visibility` value, not a per-frame miss).
- `include/roi_tracker.h` / `src/roi_tracker.cpp` — holds the last-known ROI
  across sampled frames and decides, per frame, whether to re-run the detector
  or reuse/extrapolate the existing ROI.
- `src/extractor.cpp` (rewritten) / `include/extractor.h` (changed) —
  `KeypointExtractor` gains a constructor that takes model file paths
  (defaulting to a fixed install location the fetch script populates) and owns
  the pipeline above; `Extract` becomes the orchestration loop:
  decode → sample → detect/track → regress → emit `Frame`s.
- `models/` — gitignored directory where fetched `.tflite` files land at build
  time. Not committed to git.
- `scripts/fetch_models.sh` — downloads the two pinned-version model files into
  `models/`. Invoked from `CMakeLists.txt` as a build step (so both
  `cmake --build cv-engine/build` locally and the Docker builder stage run
  the identical fetch), and from CI before `ctest`.

## Error handling

- Video fails to open, or has zero decodable frames → `Extract` returns `{}`,
  matching the current stub's contract (no throw). This preserves backward
  compatibility for the FastAPI route, which already handles an empty frame
  list.
- No person detected in a sampled frame (detector finds nothing, and the
  tracker has no ROI to fall back on) → that `Frame` gets `landmarks = {}`,
  `timestamp_sec` still recorded accurately.
- Model files missing or fail to load at `KeypointExtractor` construction time
  → throw a C++ exception immediately (fail fast at startup/construction, not
  scattered per-frame). pybind11 translates this to a Python exception; the
  FastAPI route surfaces it as a 500 rather than silently returning empty
  results.

## Testing

- `ctest` (`cv-engine/tests/`):
  - Unit tests for `PoseDetector` and `LandmarkRegressor` in isolation, fed a
    synthetic all-black frame to verify "no person → no detection / empty
    result" without needing a real person in frame.
  - Unit test for `RoiTracker`'s reuse/expire logic with synthetic ROIs.
  - Integration test for `KeypointExtractor::Extract` against a small
    (few-second) checked-in sample video — not the 30-90s real-world case,
    just enough to exercise the full pipeline and assert frame count / that
    landmarks are populated.
  - Existing test (`kNumLandmarks == 33`, empty-input contract) continues to
    pass as-is.
- Model files are required for tests, so CI (and local `ctest` runs) depend on
  `scripts/fetch_models.sh` having already run as part of the CMake build step.
- **Explicitly not covered by this spec's tests:** extraction accuracy against
  ground truth. That's the deferred accuracy-benchmarking follow-up.

## Build / Docker changes

- `cv-engine/CMakeLists.txt`:
  - Add `find_package(OpenCV REQUIRED)` (requires OpenCV ≥ 4.8 for
    `cv::dnn::readNetFromTFLite`), link into `cv_engine_core`.
  - Add a build step invoking `scripts/fetch_models.sh` before compiling
    tests/the module, so `models/` is populated for both build and `ctest`.
- `infra/docker/backend.Dockerfile`:
  - Builder stage: install OpenCV dev libraries (`apt-get install
    libopencv-dev` or equivalent) alongside the existing build toolchain.
  - Builder stage: model fetch runs as part of the `cv-engine` build (via the
    CMake step above), landing in `models/`.
  - Final stage: `COPY` the populated `models/` directory alongside the
    compiled extension so it's present at runtime — the extractor loads
    models from a fixed path in the built image, not the network, at
    inference time.

## Open questions for the implementation plan

- Exact pinned model URLs/versions for the pose-detector and pose-landmark
  TFLite files (MediaPipe's Lite variants) — to be resolved during
  implementation, pinned in `scripts/fetch_models.sh`.
- Exact sampling interval (every 3rd vs. 5th frame) — start with a reasonable
  default and treat as tunable; not a hard contract.
