# CV Engine Pose Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `KeypointExtractor::Extract`'s empty-frame stub with real pose
keypoint extraction, running MediaPipe's published pose-detector and
pose-landmark TFLite models through OpenCV's `cv::dnn` module.

**Architecture:** `KeypointExtractor` decodes video via OpenCV `VideoCapture`,
samples a subset of frames, and for each sampled frame runs a small pipeline:
`RoiTracker` decides whether to re-run `PoseDetector` (SSD-anchor-based person
detection) or reuse the last ROI, then `LandmarkRegressor` crops to that ROI
and regresses 33 keypoints. Detector and landmark models are fetched at build
time (not committed to git) into `cv-engine/models/`.

**Tech Stack:** C++17, CMake, OpenCV ≥ 4.8 (`cv::dnn::readNetFromTFLite`),
pybind11, MediaPipe's public `pose_detection.tflite` /
`pose_landmark_lite.tflite` model weights.

**Spec:** `docs/superpowers/specs/2026-08-20-cv-engine-pose-extraction-design.md`

## Global Constraints

- No subprocess, no separate service — extraction stays in-process inside the
  `cv_engine` pybind11 module (per `CLAUDE.md`).
- 33 landmarks, each `{x, y, z, visibility}`, matching
  `cv-engine/include/keypoints.h` exactly — do not change that struct.
- No new build system — stay inside CMake + pybind11 + scikit-build-core.
- Single-subject-in-frame, axis-aligned ROI crops (no rotation alignment) —
  accepted simplification per this plan, not full MediaPipe graph fidelity.
- `Frame.landmarks` is an empty vector when no pose is detected for a sampled
  frame — never zero-filled keypoints.
- Model `.tflite` files are never committed to git — always fetched at build
  time into `cv-engine/models/` (gitignored).
- No accuracy/ground-truth benchmarking in this plan — sanity-bounds testing
  only (box/keypoints land within frame, non-degenerate size).
- Model load failures throw at `KeypointExtractor` construction time (fail
  fast), never scattered per-frame inside `Extract`.

---

## Task 1: Model fetch script + CMake/OpenCV wiring

**Files:**
- Create: `cv-engine/scripts/fetch_models.sh`
- Modify: `cv-engine/CMakeLists.txt`
- Modify: `cv-engine/.gitignore` (create if it doesn't exist)

**Interfaces:**
- Produces: `cv-engine/models/pose_detection.tflite`,
  `cv-engine/models/pose_landmark_lite.tflite` on disk after the script runs.
  Later tasks read these paths.
- Produces: CMake variable `CV_ENGINE_MODELS_DIR` (set to
  `${CMAKE_SOURCE_DIR}/models`), consumed by Task 5's `configure_file` step.

This task has no unit test of its own (it's a shell script + build wiring) —
its test is "run it, the files land, and CMake configures successfully."

- [ ] **Step 1: Write the fetch script**

```bash
#!/usr/bin/env bash
# cv-engine/scripts/fetch_models.sh
#
# Downloads MediaPipe's published pose-detector and pose-landmark TFLite
# models into cv-engine/models/. Pinned to MediaPipe's public model asset
# bucket. Idempotent — skips files that already exist so repeated local
# builds don't re-download.
set -euo pipefail

MODELS_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models}"
mkdir -p "$MODELS_DIR"

fetch() {
  local url="$1" dest="$2"
  if [[ -s "$dest" ]]; then
    echo "already present: $dest"
    return 0
  fi
  echo "fetching $url -> $dest"
  curl -fSL --retry 3 -o "$dest.tmp" "$url"
  mv "$dest.tmp" "$dest"
}

fetch "https://storage.googleapis.com/mediapipe-assets/pose_detection.tflite" \
  "$MODELS_DIR/pose_detection.tflite"
fetch "https://storage.googleapis.com/mediapipe-assets/pose_landmark_lite.tflite" \
  "$MODELS_DIR/pose_landmark_lite.tflite"

echo "models ready in $MODELS_DIR"
```

```bash
chmod +x cv-engine/scripts/fetch_models.sh
```

- [ ] **Step 2: Run it manually and verify the files land**

Run: `bash cv-engine/scripts/fetch_models.sh`
Expected: two files appear under `cv-engine/models/`, each non-empty
(`ls -la cv-engine/models/` shows sizes > 0). If either `curl` call 404s, the
MediaPipe asset bucket path has changed since this plan was written — find
the current URL from `mediapipe/modules/pose_detection/BUILD` and
`mediapipe/modules/pose_landmark/BUILD` in the
`google-ai-edge/mediapipe` repo (look for the `model_path`/`http_file` rule
for `pose_detection.tflite` and `pose_landmark_lite.tflite`) and update the
script before continuing.

- [ ] **Step 3: Add `cv-engine/.gitignore`**

```
models/
build/
```

- [ ] **Step 4: Wire OpenCV and the fetch step into CMakeLists.txt**

Edit `cv-engine/CMakeLists.txt` — add after the existing `find_package`
calls:

```cmake
find_package(OpenCV 4.8 REQUIRED COMPONENTS core imgproc videoio dnn)

set(CV_ENGINE_MODELS_DIR "${CMAKE_SOURCE_DIR}/models")

add_custom_command(
  OUTPUT "${CV_ENGINE_MODELS_DIR}/pose_detection.tflite"
         "${CV_ENGINE_MODELS_DIR}/pose_landmark_lite.tflite"
  COMMAND bash "${CMAKE_SOURCE_DIR}/scripts/fetch_models.sh" "${CV_ENGINE_MODELS_DIR}"
  COMMENT "Fetching MediaPipe pose models"
  VERBATIM
)
add_custom_target(fetch_models ALL
  DEPENDS "${CV_ENGINE_MODELS_DIR}/pose_detection.tflite"
          "${CV_ENGINE_MODELS_DIR}/pose_landmark_lite.tflite"
)
```

Then edit the existing `cv_engine_core` target definition (the
`add_library(cv_engine_core STATIC ...)` block already in the file) to add
three lines directly below it:

```cmake
target_link_libraries(cv_engine_core PUBLIC ${OpenCV_LIBS})
target_include_directories(cv_engine_core PUBLIC ${OpenCV_INCLUDE_DIRS})
add_dependencies(cv_engine_core fetch_models)
```

- [ ] **Step 5: Verify CMake configures and builds cleanly**

Run: `cmake -S cv-engine -B cv-engine/build -GNinja && cmake --build cv-engine/build`
Expected: configure succeeds (OpenCV found — install it first if missing:
`brew install opencv` on macOS, `apt-get install libopencv-dev` on Linux),
build succeeds, and `cv-engine/models/*.tflite` exist after the build.

- [ ] **Step 6: Commit**

```bash
git add cv-engine/scripts/fetch_models.sh cv-engine/CMakeLists.txt cv-engine/.gitignore
git commit -m "build: fetch MediaPipe pose models at build time, link OpenCV"
```

---

## Task 2: Roi struct + RoiTracker

**Files:**
- Create: `cv-engine/include/roi.h`
- Create: `cv-engine/include/roi_tracker.h`
- Create: `cv-engine/src/roi_tracker.cpp`
- Test: `cv-engine/tests/test_roi_tracker.cpp`
- Modify: `cv-engine/tests/CMakeLists.txt`
- Modify: `cv-engine/CMakeLists.txt` (add `roi_tracker.cpp` to `cv_engine_core`)

**Interfaces:**
- Produces: `struct formiq::Roi { float x_center, y_center, width, height; };`
  (all in original-frame pixel coordinates).
- Produces: `class formiq::RoiTracker` with `bool ShouldRedetect() const`,
  `void OnDetection(std::optional<Roi> detected)`, `std::optional<Roi>
  Current() const`. No OpenCV dependency — pure logic, consumed by Task 5's
  orchestration loop and by Task 3's tests.

Pure logic, no OpenCV/model dependency — straightforward TDD.

- [ ] **Step 1: Write `roi.h`**

```cpp
// cv-engine/include/roi.h
#pragma once

namespace formiq {

// A person's region of interest in original-frame pixel coordinates.
// Axis-aligned — no rotation, per this plan's single-subject-upright
// simplification (see spec).
struct Roi {
    float x_center = 0.0F;
    float y_center = 0.0F;
    float width = 0.0F;
    float height = 0.0F;
};

}  // namespace formiq
```

- [ ] **Step 2: Write the failing test for RoiTracker**

```cpp
// cv-engine/tests/test_roi_tracker.cpp
#include <cassert>
#include <optional>

#include "roi.h"
#include "roi_tracker.h"

int main() {
    using formiq::Roi;
    using formiq::RoiTracker;

    // Fresh tracker with no ROI yet must ask to redetect.
    RoiTracker tracker;
    assert(tracker.ShouldRedetect());
    assert(!tracker.Current().has_value());

    // A successful detection is stored and reused without redetecting.
    Roi first{100.0F, 100.0F, 50.0F, 80.0F};
    tracker.OnDetection(first);
    assert(!tracker.ShouldRedetect());
    assert(tracker.Current().has_value());
    assert(tracker.Current()->x_center == 100.0F);

    // After kRedetectInterval reuse calls without a new detection, it asks
    // to redetect again.
    for (int i = 0; i < formiq::RoiTracker::kRedetectInterval; ++i) {
        tracker.OnDetection(std::nullopt);  // reuse call: no new detection
    }
    assert(tracker.ShouldRedetect());

    // A detector miss with no prior ROI clears Current().
    RoiTracker tracker2;
    tracker2.OnDetection(std::nullopt);
    assert(!tracker2.Current().has_value());
    assert(tracker2.ShouldRedetect());

    return 0;
}
```

- [ ] **Step 3: Add the test target and run to verify it fails**

Add to `cv-engine/tests/CMakeLists.txt`:

```cmake
add_executable(test_roi_tracker test_roi_tracker.cpp)
target_link_libraries(test_roi_tracker PRIVATE cv_engine_core)
add_test(NAME test_roi_tracker COMMAND test_roi_tracker)
```

Run: `cmake --build cv-engine/build`
Expected: FAIL — `roi_tracker.h` doesn't exist yet.

- [ ] **Step 4: Write `roi_tracker.h` and `roi_tracker.cpp`**

```cpp
// cv-engine/include/roi_tracker.h
#pragma once

#include <optional>

#include "roi.h"

namespace formiq {

// Tracks the last-known person ROI across sampled frames so the (expensive)
// PoseDetector doesn't need to run on every sampled frame. Reuses the last
// detected ROI until kRedetectInterval frames have passed with no fresh
// detection, or until a detection attempt comes back empty.
class RoiTracker {
public:
    static constexpr int kRedetectInterval = 10;

    // True when the next sampled frame should run PoseDetector rather than
    // reuse Current().
    bool ShouldRedetect() const;

    // Call once per sampled frame with the PoseDetector's result for that
    // frame (std::nullopt if the detector didn't run this frame, i.e. this
    // frame is reusing the tracked ROI rather than a fresh detection).
    void OnDetection(std::optional<Roi> detected);

    std::optional<Roi> Current() const { return current_; }

private:
    std::optional<Roi> current_;
    int frames_since_detect_ = 0;
};

}  // namespace formiq
```

```cpp
// cv-engine/src/roi_tracker.cpp
#include "roi_tracker.h"

namespace formiq {

bool RoiTracker::ShouldRedetect() const {
    return !current_.has_value() || frames_since_detect_ >= kRedetectInterval;
}

void RoiTracker::OnDetection(std::optional<Roi> detected) {
    if (detected.has_value()) {
        current_ = detected;
        frames_since_detect_ = 0;
    } else if (ShouldRedetect()) {
        // A redetection attempt came back empty — nothing to track anymore.
        current_.reset();
        frames_since_detect_ = 0;
    } else {
        // Reuse call (detector didn't run this frame) — age the ROI.
        ++frames_since_detect_;
    }
}

}  // namespace formiq
```

Add `src/roi_tracker.cpp` to the `cv_engine_core` sources in
`cv-engine/CMakeLists.txt`:

```cmake
add_library(cv_engine_core STATIC
  src/extractor.cpp
  src/roi_tracker.cpp
)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cmake --build cv-engine/build && ctest --test-dir cv-engine/build -R test_roi_tracker --output-on-failure`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add cv-engine/include/roi.h cv-engine/include/roi_tracker.h \
        cv-engine/src/roi_tracker.cpp cv-engine/tests/test_roi_tracker.cpp \
        cv-engine/tests/CMakeLists.txt cv-engine/CMakeLists.txt
git commit -m "feat: add Roi struct and RoiTracker"
```

---

## Task 3: PoseDetector (SSD anchor decode + NMS)

**Files:**
- Create: `cv-engine/include/pose_detector.h`
- Create: `cv-engine/src/pose_detector.cpp`
- Test: `cv-engine/tests/test_pose_detector.cpp`
- Test fixture: `cv-engine/tests/fixtures/person.jpg`
- Modify: `cv-engine/tests/CMakeLists.txt`
- Modify: `cv-engine/CMakeLists.txt` (add `pose_detector.cpp` to `cv_engine_core`)

**Interfaces:**
- Consumes: `formiq::Roi` from Task 2.
- Produces: `class formiq::PoseDetector` with constructor
  `PoseDetector(const std::string& model_path)` and method
  `std::optional<Roi> Detect(const cv::Mat& frame_bgr) const`. Consumed by
  Task 5's orchestration loop.

Anchor generation and score/box decoding use values verified against
MediaPipe's public `pose_detection_cpu.pbtxt`
(`SsdAnchorsCalculatorOptions` / `TensorsToDetectionsCalculatorOptions`):
`num_layers=5`, `min_scale=0.1484375`, `max_scale=0.75`, input `224x224`,
`strides=[8,16,32,32,32]`, `aspect_ratios=[1.0]`, `fixed_anchor_size=true`,
`num_boxes=2254`, `num_coords=12`, `sigmoid_score=true`,
`score_clipping_thresh=100.0`, `min_score_thresh=0.5`, all four scales
`=224.0`, `reverse_output_order=true` (raw box values ordered `x,y,w,h`).
NMS IoU threshold (`0.3`) is our own choice, not pulled from MediaPipe config.

- [ ] **Step 1: Add a test fixture image**

Add a small JPEG with one clearly-visible person, roughly upright, to
`cv-engine/tests/fixtures/person.jpg` (a few hundred KB is fine — any royalty-free
stock photo of someone standing works). This is a real binary asset committed
to the repo (small, needed for every future test run — unlike the
multi-megabyte models, this is fine to vendor).

- [ ] **Step 2: Write the failing test**

```cpp
// cv-engine/tests/test_pose_detector.cpp
#include <cassert>
#include <opencv2/opencv.hpp>

#include "pose_detector.h"

int main() {
    formiq::PoseDetector detector("models/pose_detection.tflite");

    // A blank black frame has no person — must return nullopt, not a
    // fabricated box.
    cv::Mat blank = cv::Mat::zeros(480, 640, CV_8UC3);
    auto blank_result = detector.Detect(blank);
    assert(!blank_result.has_value());

    // A real photo of a person must return a plausible, in-bounds box.
    cv::Mat person = cv::imread("tests/fixtures/person.jpg");
    assert(!person.empty());  // fixture must exist and be readable
    auto person_result = detector.Detect(person);
    assert(person_result.has_value());
    const formiq::Roi& roi = *person_result;
    assert(roi.width > 0.0F && roi.height > 0.0F);
    assert(roi.x_center - roi.width / 2 >= -1.0F);   // small tolerance
    assert(roi.y_center - roi.height / 2 >= -1.0F);
    assert(roi.x_center + roi.width / 2 <= person.cols + 1.0F);
    assert(roi.y_center + roi.height / 2 <= person.rows + 1.0F);

    return 0;
}
```

- [ ] **Step 3: Add the test target and run to verify it fails**

Add to `cv-engine/tests/CMakeLists.txt`:

```cmake
add_executable(test_pose_detector test_pose_detector.cpp)
target_link_libraries(test_pose_detector PRIVATE cv_engine_core ${OpenCV_LIBS})
target_include_directories(test_pose_detector PRIVATE ${OpenCV_INCLUDE_DIRS})
add_test(NAME test_pose_detector COMMAND test_pose_detector
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
```

Run: `cmake --build cv-engine/build`
Expected: FAIL — `pose_detector.h` doesn't exist yet.

- [ ] **Step 4: Write `pose_detector.h`**

```cpp
// cv-engine/include/pose_detector.h
#pragma once

#include <optional>
#include <string>

#include <opencv2/dnn.hpp>

#include "roi.h"

namespace formiq {

// Runs MediaPipe's published pose-detection TFLite model (SSD-style,
// 2254 anchors) via OpenCV's DNN module to find a single person's bounding
// box in a frame. Returns std::nullopt if no box clears min_score_thresh.
class PoseDetector {
public:
    explicit PoseDetector(const std::string& model_path);

    std::optional<Roi> Detect(const cv::Mat& frame_bgr) const;

private:
    mutable cv::dnn::Net net_;
};

}  // namespace formiq
```

- [ ] **Step 5: Write `pose_detector.cpp`**

```cpp
// cv-engine/src/pose_detector.cpp
#include "pose_detector.h"

#include <algorithm>
#include <cmath>
#include <vector>

#include <opencv2/imgproc.hpp>

namespace formiq {
namespace {

constexpr int kInputSize = 224;
constexpr int kNumLayers = 5;
constexpr float kMinScale = 0.1484375F;
constexpr float kMaxScale = 0.75F;
constexpr int kStrides[kNumLayers] = {8, 16, 32, 32, 32};
constexpr float kAnchorOffset = 0.5F;
constexpr int kNumBoxes = 2254;
constexpr float kScoreClippingThresh = 100.0F;
constexpr float kMinScoreThresh = 0.5F;
constexpr float kBoxScale = 224.0F;
constexpr float kNmsIouThreshold = 0.3F;  // our own choice, not from MediaPipe config

struct Anchor {
    float x_center;
    float y_center;
};

float ScaleForLayer(int layer_index) {
    if (kNumLayers == 1) return kMinScale;
    return kMinScale +
           (kMaxScale - kMinScale) * static_cast<float>(layer_index) /
               static_cast<float>(kNumLayers - 1);
}

// Reproduces MediaPipe's SsdAnchorsCalculator with fixed_anchor_size=true
// and a single aspect_ratio of 1.0 (which yields 2 anchors per grid cell,
// matching num_boxes=2254). fixed_anchor_size means every anchor's
// width/height is 1.0 in normalized space — only x_center/y_center vary.
std::vector<Anchor> GenerateAnchors() {
    std::vector<Anchor> anchors;
    anchors.reserve(kNumBoxes);
    for (int layer = 0; layer < kNumLayers; ++layer) {
        const int stride = kStrides[layer];
        const int feature_size =
            static_cast<int>(std::ceil(static_cast<float>(kInputSize) / stride));
        for (int y = 0; y < feature_size; ++y) {
            for (int x = 0; x < feature_size; ++x) {
                const float x_center = (x + kAnchorOffset) / feature_size;
                const float y_center = (y + kAnchorOffset) / feature_size;
                // aspect_ratios = [1.0] yields 2 anchors per cell (the
                // standard extra scale-interpolated anchor for ratio 1.0).
                anchors.push_back({x_center, y_center});
                anchors.push_back({x_center, y_center});
            }
        }
    }
    return anchors;
}

float Sigmoid(float x) {
    x = std::clamp(x, -kScoreClippingThresh, kScoreClippingThresh);
    return 1.0F / (1.0F + std::exp(-x));
}

// Square-pads frame_bgr to a square (letterbox) then resizes to
// kInputSize x kInputSize, matching MediaPipe's ImageToTensorCalculator
// FIT scaling. Returns the square side length used (in original pixels)
// and the top/left padding, so detected boxes can be mapped back.
cv::Mat PrepareInput(const cv::Mat& frame_bgr, int& square_side, int& pad_x, int& pad_y) {
    square_side = std::max(frame_bgr.cols, frame_bgr.rows);
    pad_x = (square_side - frame_bgr.cols) / 2;
    pad_y = (square_side - frame_bgr.rows) / 2;

    cv::Mat square = cv::Mat::zeros(square_side, square_side, frame_bgr.type());
    frame_bgr.copyTo(square(cv::Rect(pad_x, pad_y, frame_bgr.cols, frame_bgr.rows)));

    cv::Mat resized;
    cv::resize(square, resized, cv::Size(kInputSize, kInputSize));

    cv::Mat rgb;
    cv::cvtColor(resized, rgb, cv::COLOR_BGR2RGB);
    cv::Mat blob = cv::dnn::blobFromImage(rgb, 1.0 / 127.5, cv::Size(), cv::Scalar(), false, false, CV_32F);
    // blobFromImage scales to [0, 2/127.5*255]; shift into MediaPipe's
    // expected [-1, 1] input range.
    blob -= 1.0;
    return blob;
}

}  // namespace

PoseDetector::PoseDetector(const std::string& model_path) {
    net_ = cv::dnn::readNetFromTFLite(model_path);
}

std::optional<Roi> PoseDetector::Detect(const cv::Mat& frame_bgr) const {
    int square_side = 0;
    int pad_x = 0;
    int pad_y = 0;
    cv::Mat blob = PrepareInput(frame_bgr, square_side, pad_x, pad_y);

    net_.setInput(blob);
    std::vector<cv::Mat> outputs;
    net_.forward(outputs, net_.getUnconnectedOutLayersNames());
    // Expect two outputs: regressors [1, 2254, 12] and scores [1, 2254, 1],
    // in the order OpenCV's DNN reports the model's output layers.
    if (outputs.size() < 2) return std::nullopt;
    const cv::Mat& regressors = outputs[0].total() > outputs[1].total() ? outputs[0] : outputs[1];
    const cv::Mat& scores = outputs[0].total() > outputs[1].total() ? outputs[1] : outputs[0];

    static const std::vector<Anchor> anchors = GenerateAnchors();
    const float* reg = reinterpret_cast<const float*>(regressors.data);
    const float* sc = reinterpret_cast<const float*>(scores.data);

    std::vector<cv::Rect2f> boxes;
    std::vector<float> confidences;
    for (int i = 0; i < kNumBoxes && i < static_cast<int>(anchors.size()); ++i) {
        const float score = Sigmoid(sc[i]);
        if (score < kMinScoreThresh) continue;

        const float* box = reg + (i * 12);
        // reverse_output_order=true -> raw order is x, y, w, h.
        const float cx = box[0] / kBoxScale + anchors[i].x_center;
        const float cy = box[1] / kBoxScale + anchors[i].y_center;
        const float w = box[2] / kBoxScale;
        const float h = box[3] / kBoxScale;

        boxes.emplace_back(cx - w / 2, cy - h / 2, w, h);
        confidences.push_back(score);
    }

    if (boxes.empty()) return std::nullopt;

    std::vector<int> keep;
    cv::dnn::NMSBoxes(boxes, confidences, kMinScoreThresh, kNmsIouThreshold, keep);
    if (keep.empty()) return std::nullopt;

    // Highest-confidence surviving box, mapped from normalized square-input
    // space back to original frame pixel coordinates.
    int best = keep[0];
    for (int idx : keep) {
        if (confidences[idx] > confidences[best]) best = idx;
    }

    const cv::Rect2f& box = boxes[best];
    Roi roi;
    roi.x_center = (box.x + box.width / 2) * square_side - pad_x;
    roi.y_center = (box.y + box.height / 2) * square_side - pad_y;
    roi.width = box.width * square_side;
    roi.height = box.height * square_side;
    return roi;
}

}  // namespace formiq
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cmake --build cv-engine/build && ctest --test-dir cv-engine/build -R test_pose_detector --output-on-failure`
Expected: PASS. If the person-photo assertion fails, print `roi.x_center,
roi.y_center, roi.width, roi.height` and sanity-check by eye against the
fixture image dimensions — a wrong output-tensor-order guess (regressors vs.
scores swapped) is the most likely bug; the `outputs[0].total() >
outputs[1].total()` heuristic picks the larger tensor (2254×12) as
regressors, but confirm this against `net_.getUnconnectedOutLayersNames()`
if it fails.

- [ ] **Step 7: Commit**

```bash
git add cv-engine/include/pose_detector.h cv-engine/src/pose_detector.cpp \
        cv-engine/tests/test_pose_detector.cpp cv-engine/tests/fixtures/person.jpg \
        cv-engine/tests/CMakeLists.txt cv-engine/CMakeLists.txt
git commit -m "feat: add PoseDetector (SSD anchor decode over MediaPipe model)"
```

---

## Task 4: LandmarkRegressor

**Files:**
- Create: `cv-engine/include/landmark_regressor.h`
- Create: `cv-engine/src/landmark_regressor.cpp`
- Test: `cv-engine/tests/test_landmark_regressor.cpp`
- Modify: `cv-engine/tests/CMakeLists.txt`
- Modify: `cv-engine/CMakeLists.txt` (add `landmark_regressor.cpp` to `cv_engine_core`)

**Interfaces:**
- Consumes: `formiq::Roi` from Task 2, reuses `tests/fixtures/person.jpg`
  from Task 3.
- Produces: `class formiq::LandmarkRegressor` with constructor
  `LandmarkRegressor(const std::string& model_path)` and method
  `std::vector<Keypoint> Regress(const cv::Mat& frame_bgr, const Roi& roi)
  const` returning exactly `kNumLandmarks` (33) `Keypoint`s. Consumed by
  Task 5.

The pose-landmark model's exact output tensor layout (which of its output
tensors is the 33-landmark tensor, and its value ordering) isn't in the
public `.pbtxt` graph configs — it's implemented in a compiled MediaPipe
calculator. Rather than guess, Step 1 introspects the actual downloaded
model file to confirm shapes before writing decode logic.

- [ ] **Step 1: Introspect the model's real input/output tensor shapes**

Run (after Task 1's fetch has populated `cv-engine/models/`):

```bash
pip install --quiet tensorflow  # or: pip install tflite-runtime
python3 - <<'EOF'
import tensorflow as tf
interp = tf.lite.Interpreter(model_path="cv-engine/models/pose_landmark_lite.tflite")
interp.allocate_tensors()
print("INPUTS:")
for d in interp.get_input_details():
    print(" ", d["name"], d["shape"], d["dtype"])
print("OUTPUTS:")
for d in interp.get_output_details():
    print(" ", d["name"], d["shape"], d["dtype"])
EOF
```

Expected (record the actual output for the next step — this is the
well-known MediaPipe Lite pose landmark layout, confirm it matches): one
input `[1, 256, 256, 3]` float32, and outputs including a landmarks tensor
shaped `[1, 195]` (39 landmarks × 5 values: x, y, z, visibility, presence —
the first 33 of the 39 are the body landmarks this project uses; the
remaining 6 are auxiliary points MediaPipe uses for ROI rotation, which this
plan's axis-aligned-crop simplification ignores) and a separate pose-presence
score tensor shaped `[1, 1]`. **If the actual printed shapes differ from
this, use the real printed shapes and adjust Step 3's constants —
correctness depends on what the model file actually reports, not this
comment.**

- [ ] **Step 2: Write the failing test**

```cpp
// cv-engine/tests/test_landmark_regressor.cpp
#include <cassert>
#include <opencv2/opencv.hpp>

#include "keypoints.h"
#include "landmark_regressor.h"
#include "roi.h"

int main() {
    formiq::LandmarkRegressor regressor("models/pose_landmark_lite.tflite");

    cv::Mat person = cv::imread("tests/fixtures/person.jpg");
    assert(!person.empty());

    // Whole-image ROI is a reasonable stand-in for a detector-provided box
    // in this fixture-driven test.
    formiq::Roi roi{
        static_cast<float>(person.cols) / 2.0F,
        static_cast<float>(person.rows) / 2.0F,
        static_cast<float>(person.cols),
        static_cast<float>(person.rows),
    };

    std::vector<formiq::Keypoint> keypoints = regressor.Regress(person, roi);
    assert(keypoints.size() == formiq::kNumLandmarks);

    // At least some keypoints should report meaningful visibility for a
    // real photo of a person — this is a sanity bound, not an accuracy
    // check (see spec non-goals).
    int visible_count = 0;
    for (const auto& kp : keypoints) {
        if (kp.visibility > 0.5F) ++visible_count;
    }
    assert(visible_count > 0);

    return 0;
}
```

- [ ] **Step 3: Add the test target and run to verify it fails**

Add to `cv-engine/tests/CMakeLists.txt`:

```cmake
add_executable(test_landmark_regressor test_landmark_regressor.cpp)
target_link_libraries(test_landmark_regressor PRIVATE cv_engine_core ${OpenCV_LIBS})
target_include_directories(test_landmark_regressor PRIVATE ${OpenCV_INCLUDE_DIRS})
add_test(NAME test_landmark_regressor COMMAND test_landmark_regressor
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
```

Run: `cmake --build cv-engine/build`
Expected: FAIL — `landmark_regressor.h` doesn't exist yet.

- [ ] **Step 4: Write `landmark_regressor.h`**

```cpp
// cv-engine/include/landmark_regressor.h
#pragma once

#include <string>
#include <vector>

#include <opencv2/dnn.hpp>

#include "keypoints.h"
#include "roi.h"

namespace formiq {

// Runs MediaPipe's published pose-landmark TFLite model via OpenCV's DNN
// module on a frame cropped to a Roi. Always returns kNumLandmarks (33)
// keypoints — per-keypoint confidence is carried in Keypoint::visibility,
// not a per-call optional (a low-confidence regression still returns 33
// keypoints with low visibility, unlike PoseDetector's per-frame miss).
class LandmarkRegressor {
public:
    explicit LandmarkRegressor(const std::string& model_path);

    std::vector<Keypoint> Regress(const cv::Mat& frame_bgr, const Roi& roi) const;

private:
    mutable cv::dnn::Net net_;
};

}  // namespace formiq
```

- [ ] **Step 5: Write `landmark_regressor.cpp`**

Use the shapes confirmed in Step 1. This implementation assumes the
well-known MediaPipe Lite layout confirmed there (`[1,256,256,3]` input,
`[1,195]` landmarks output = 39 × 5 values, first 33 used) — if Step 1's
actual output differed, adjust `kInputSize`/`kNumRawLandmarks`/output-index
selection accordingly before treating this step as done.

```cpp
// cv-engine/src/landmark_regressor.cpp
#include "landmark_regressor.h"

#include <algorithm>
#include <cmath>

#include <opencv2/imgproc.hpp>

namespace formiq {
namespace {

constexpr int kInputSize = 256;
constexpr int kNumRawLandmarks = 39;  // 33 body + 6 auxiliary (unused here)
constexpr int kValuesPerLandmark = 5; // x, y, z, visibility, presence

float Sigmoid(float x) { return 1.0F / (1.0F + std::exp(-x)); }

cv::Rect ClampedCropRect(const Roi& roi, const cv::Mat& frame) {
    const int x0 = static_cast<int>(std::round(roi.x_center - roi.width / 2));
    const int y0 = static_cast<int>(std::round(roi.y_center - roi.height / 2));
    cv::Rect rect(x0, y0, static_cast<int>(std::round(roi.width)),
                  static_cast<int>(std::round(roi.height)));
    return rect & cv::Rect(0, 0, frame.cols, frame.rows);
}

}  // namespace

LandmarkRegressor::LandmarkRegressor(const std::string& model_path) {
    net_ = cv::dnn::readNetFromTFLite(model_path);
}

std::vector<Keypoint> LandmarkRegressor::Regress(const cv::Mat& frame_bgr, const Roi& roi) const {
    cv::Rect crop_rect = ClampedCropRect(roi, frame_bgr);
    std::vector<Keypoint> result(kNumLandmarks);
    if (crop_rect.width <= 0 || crop_rect.height <= 0) {
        return result;  // all-zero, visibility 0 — degenerate ROI
    }

    cv::Mat cropped = frame_bgr(crop_rect);
    cv::Mat rgb;
    cv::cvtColor(cropped, rgb, cv::COLOR_BGR2RGB);
    cv::Mat blob = cv::dnn::blobFromImage(rgb, 1.0 / 127.5, cv::Size(kInputSize, kInputSize),
                                           cv::Scalar(), false, false, CV_32F);
    blob -= 1.0;  // shift blobFromImage's [0, ~2] scale into MediaPipe's [-1, 1]

    net_.setInput(blob);
    std::vector<cv::Mat> outputs;
    net_.forward(outputs, net_.getUnconnectedOutLayersNames());
    if (outputs.empty()) return result;

    // The 195-value landmarks tensor is the largest output; select it by
    // element count rather than assuming index 0 (matches the introspection
    // approach used for PoseDetector).
    const cv::Mat* landmarks_tensor = &outputs[0];
    for (const auto& out : outputs) {
        if (out.total() > landmarks_tensor->total()) landmarks_tensor = &out;
    }
    if (static_cast<int>(landmarks_tensor->total()) < kNumRawLandmarks * kValuesPerLandmark) {
        return result;
    }

    const float* raw = reinterpret_cast<const float*>(landmarks_tensor->data);
    const float sx = static_cast<float>(crop_rect.width) / kInputSize;
    const float sy = static_cast<float>(crop_rect.height) / kInputSize;

    for (std::size_t i = 0; i < kNumLandmarks; ++i) {
        const float* lm = raw + (i * kValuesPerLandmark);
        Keypoint kp;
        kp.x = crop_rect.x + lm[0] * sx;
        kp.y = crop_rect.y + lm[1] * sy;
        kp.z = lm[2] * sx;  // z shares x's scale, matching MediaPipe's convention
        kp.visibility = Sigmoid(lm[3]);
        result[i] = kp;
    }
    return result;
}

}  // namespace formiq
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cmake --build cv-engine/build && ctest --test-dir cv-engine/build -R test_landmark_regressor --output-on-failure`
Expected: PASS. If `visible_count == 0` for a real photo, the most likely
bug is a mismatched output tensor selection or an off-by-one in
`kValuesPerLandmark`/`kNumRawLandmarks` versus what Step 1 actually printed —
re-check against the recorded introspection output before changing the
sigmoid/scale math.

- [ ] **Step 7: Commit**

```bash
git add cv-engine/include/landmark_regressor.h cv-engine/src/landmark_regressor.cpp \
        cv-engine/tests/test_landmark_regressor.cpp cv-engine/tests/CMakeLists.txt \
        cv-engine/CMakeLists.txt
git commit -m "feat: add LandmarkRegressor"
```

---

## Task 5: Rewire KeypointExtractor to orchestrate the full pipeline

**Files:**
- Modify: `cv-engine/include/extractor.h`
- Modify: `cv-engine/src/extractor.cpp`
- Create: `cv-engine/include/model_paths.h.in`
- Modify: `cv-engine/CMakeLists.txt` (add `configure_file` step)
- Test: `cv-engine/tests/test_extractor.cpp` (extend existing)
- Test fixture: `cv-engine/tests/fixtures/sample_clip.mp4`

**Interfaces:**
- Consumes: `formiq::RoiTracker` (Task 2), `formiq::PoseDetector` (Task 3),
  `formiq::LandmarkRegressor` (Task 4).
- Produces: `KeypointExtractor(const std::string& detector_model_path =
  kDefaultPoseDetectorModelPath, const std::string& landmark_model_path =
  kDefaultPoseLandmarkModelPath)` and unchanged signature
  `std::vector<Frame> Extract(const std::string& video_path) const`.
  Consumed by Task 6's bindings (default-constructible, so
  `cv_engine.KeypointExtractor()` in `backend/app/api/routes.py` keeps
  working unmodified).

- [ ] **Step 1: Add a short sample video fixture**

Add a 3-5 second video (one person doing anything, upright, visible) to
`cv-engine/tests/fixtures/sample_clip.mp4`, kept small (a phone clip
trimmed short, well under 5MB).

- [ ] **Step 2: Extend the failing test**

Replace `cv-engine/tests/test_extractor.cpp` with:

```cpp
// cv-engine/tests/test_extractor.cpp
#include <cassert>
#include <exception>

#include "extractor.h"
#include "keypoints.h"

int main() {
    assert(formiq::kNumLandmarks == 33);

    // Nonexistent video still returns empty, unchanged contract.
    {
        formiq::KeypointExtractor extractor;
        const std::vector<formiq::Frame> frames = extractor.Extract("nonexistent.mp4");
        assert(frames.empty());
    }

    // Real short clip produces a non-empty, correctly-shaped frame sequence.
    {
        formiq::KeypointExtractor extractor;
        const std::vector<formiq::Frame> frames =
            extractor.Extract("tests/fixtures/sample_clip.mp4");
        assert(!frames.empty());
        for (const auto& frame : frames) {
            // landmarks is either empty (no detection that frame) or exactly
            // kNumLandmarks — never a partial set.
            assert(frame.landmarks.empty() ||
                   frame.landmarks.size() == formiq::kNumLandmarks);
        }
        // Timestamps must be non-decreasing and reflect real video time.
        for (std::size_t i = 1; i < frames.size(); ++i) {
            assert(frames[i].timestamp_sec >= frames[i - 1].timestamp_sec);
        }
    }

    // A bad model path must throw at construction time (fail fast), not
    // silently defer the failure into Extract().
    {
        bool threw = false;
        try {
            formiq::KeypointExtractor bad_extractor("nonexistent_detector.tflite",
                                                      "nonexistent_landmark.tflite");
        } catch (const std::exception&) {
            threw = true;
        }
        assert(threw);
    }

    return 0;
}
```

- [ ] **Step 3: Run to verify it fails**

Run: `cmake --build cv-engine/build && ctest --test-dir cv-engine/build -R test_extractor --output-on-failure`
Expected: FAIL — `Extract` still returns `{}` unconditionally (stub
behavior), so the second block's `!frames.empty()` assertion fails.

- [ ] **Step 4: Generate default model paths via CMake**

```cpp
// cv-engine/include/model_paths.h.in
#pragma once

namespace formiq {

inline constexpr const char* kDefaultPoseDetectorModelPath =
    "@CV_ENGINE_MODELS_DIR@/pose_detection.tflite";
inline constexpr const char* kDefaultPoseLandmarkModelPath =
    "@CV_ENGINE_MODELS_DIR@/pose_landmark_lite.tflite";

}  // namespace formiq
```

Add to `cv-engine/CMakeLists.txt`, after `CV_ENGINE_MODELS_DIR` is set
(Task 1):

```cmake
configure_file(
  "${CMAKE_SOURCE_DIR}/include/model_paths.h.in"
  "${CMAKE_BINARY_DIR}/generated/model_paths.h"
  @ONLY
)
target_include_directories(cv_engine_core PUBLIC "${CMAKE_BINARY_DIR}/generated")
```

This bakes an absolute path to `cv-engine/models/` at configure time — valid
for both local `cmake --build cv-engine/build` (source tree stays put) and
the Docker builder stage (Task 8 copies `models/` to the same absolute path
in the final image).

- [ ] **Step 5: Rewrite `extractor.h`**

```cpp
// cv-engine/include/extractor.h
#pragma once

#include <string>
#include <vector>

#include "keypoints.h"
#include "landmark_regressor.h"
#include "model_paths.h"
#include "pose_detector.h"

namespace formiq {

// Extracts per-frame pose keypoints from a video file by running MediaPipe's
// published pose-detector and pose-landmark models (see PoseDetector,
// LandmarkRegressor) over a downsampled subset of frames. Both models load
// at construction time, so a missing/corrupt model file throws immediately
// here rather than partway through a later Extract() call.
class KeypointExtractor {
public:
    explicit KeypointExtractor(
        const std::string& detector_model_path = kDefaultPoseDetectorModelPath,
        const std::string& landmark_model_path = kDefaultPoseLandmarkModelPath);

    std::vector<Frame> Extract(const std::string& video_path) const;

private:
    PoseDetector detector_;
    LandmarkRegressor regressor_;
};

}  // namespace formiq
```

- [ ] **Step 6: Rewrite `extractor.cpp`**

```cpp
// cv-engine/src/extractor.cpp
#include "extractor.h"

#include <opencv2/videoio.hpp>

#include "roi_tracker.h"

namespace formiq {
namespace {

// Run pose inference on roughly every 4th decoded frame (~7.5fps effective
// at native 30fps) rather than every frame — the primary lever for landing
// near the spec's typical-case latency target on 30-90s clips. Tunable, not
// a hard contract.
constexpr int kFrameSampleInterval = 4;

}  // namespace

// Both models load here, at construction — a missing/corrupt model file
// throws immediately (propagated from PoseDetector/LandmarkRegressor's own
// constructors via cv::dnn::readNetFromTFLite), not partway through a later
// Extract() call.
KeypointExtractor::KeypointExtractor(const std::string& detector_model_path,
                                      const std::string& landmark_model_path)
    : detector_(detector_model_path), regressor_(landmark_model_path) {}

std::vector<Frame> KeypointExtractor::Extract(const std::string& video_path) const {
    cv::VideoCapture capture(video_path);
    if (!capture.isOpened()) return {};

    const double fps = capture.get(cv::CAP_PROP_FPS);
    if (fps <= 0.0) return {};

    RoiTracker tracker;

    std::vector<Frame> frames;
    cv::Mat raw_frame;
    int frame_index = 0;
    while (capture.read(raw_frame)) {
        if (frame_index % kFrameSampleInterval == 0) {
            Frame frame;
            frame.timestamp_sec = static_cast<double>(frame_index) / fps;

            if (tracker.ShouldRedetect()) {
                tracker.OnDetection(detector_.Detect(raw_frame));
            } else {
                tracker.OnDetection(std::nullopt);  // reuse: age the tracked ROI
            }

            if (tracker.Current().has_value()) {
                frame.landmarks = regressor_.Regress(raw_frame, *tracker.Current());
            }
            // else: no ROI available this frame -> frame.landmarks stays empty

            frames.push_back(std::move(frame));
        }
        ++frame_index;
    }

    return frames;
}

}  // namespace formiq
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cmake --build cv-engine/build && ctest --test-dir cv-engine/build -R test_extractor --output-on-failure`
Expected: PASS

- [ ] **Step 8: Run the full suite**

Run: `ctest --test-dir cv-engine/build --output-on-failure`
Expected: all tests (`test_extractor`, `test_roi_tracker`,
`test_pose_detector`, `test_landmark_regressor`) PASS.

- [ ] **Step 9: Commit**

```bash
git add cv-engine/include/extractor.h cv-engine/src/extractor.cpp \
        cv-engine/include/model_paths.h.in cv-engine/CMakeLists.txt \
        cv-engine/tests/test_extractor.cpp cv-engine/tests/fixtures/sample_clip.mp4
git commit -m "feat: wire KeypointExtractor to real pose extraction pipeline"
```

---

## Task 6: Update pybind11 bindings for the new constructor

**Files:**
- Modify: `cv-engine/src/bindings.cpp`

**Interfaces:**
- Consumes: `KeypointExtractor`'s new constructor from Task 5.
- Produces: unchanged Python-visible behavior for
  `cv_engine.KeypointExtractor()` (default args), plus a new optional
  explicit-paths overload for testability from Python.

- [ ] **Step 1: Update the binding**

In `cv-engine/src/bindings.cpp`, replace:

```cpp
    py::class_<formiq::KeypointExtractor>(m, "KeypointExtractor")
        .def(py::init<>())
        .def("extract", &formiq::KeypointExtractor::Extract, py::arg("video_path"));
```

with:

```cpp
    py::class_<formiq::KeypointExtractor>(m, "KeypointExtractor")
        .def(py::init<std::string, std::string>(),
             py::arg("detector_model_path") = formiq::kDefaultPoseDetectorModelPath,
             py::arg("landmark_model_path") = formiq::kDefaultPoseLandmarkModelPath)
        .def("extract", &formiq::KeypointExtractor::Extract, py::arg("video_path"));
```

And add `#include <string>` and `#include "model_paths.h"` to the top of
`bindings.cpp` alongside the existing includes.

- [ ] **Step 2: Rebuild and smoke-test from Python**

Run:
```bash
cmake --build cv-engine/build
python3 -c "
import sys; sys.path.insert(0, 'cv-engine/build')
import cv_engine
e = cv_engine.KeypointExtractor()
frames = e.extract('cv-engine/tests/fixtures/sample_clip.mp4')
print(len(frames), 'frames, first landmark count:',
      len(frames[0].landmarks) if frames else 'n/a')
"
```

Expected: prints a frame count > 0 with no exception. This is a manual smoke
check (not a `ctest` target) confirming `backend/app/api/routes.py`'s
`cv_engine.KeypointExtractor()` call keeps working unmodified — backend
integration itself is out of this plan's scope per the spec.

- [ ] **Step 3: Run full ctest suite once more**

Run: `ctest --test-dir cv-engine/build --output-on-failure`
Expected: all tests PASS (bindings change shouldn't affect C++ tests, this
just confirms nothing broke).

- [ ] **Step 4: Commit**

```bash
git add cv-engine/src/bindings.cpp
git commit -m "feat: expose configurable model paths in KeypointExtractor bindings"
```

---

## Task 7: CI — install OpenCV, run the model fetch before tests

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:** None — infra-only change.

- [ ] **Step 1: Add OpenCV install to the `cv-engine` CI job**

In `.github/workflows/ci.yml`, update the `cv-engine` job's "Install build
tools" step:

```yaml
      - name: Install build tools
        run: |
          sudo apt-get update
          sudo apt-get install -y cmake ninja-build libopencv-dev
```

(The model fetch itself needs no separate CI step — Task 1 wired it into the
CMake `configure`/`build` step via `add_custom_target(fetch_models ALL ...)`,
so `cmake --build cv-engine/build` in CI's existing "Build" step fetches
automatically.)

- [ ] **Step 2: Validate the workflow file**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" `
(or any YAML linter available) to confirm the edit didn't break the YAML.
Expected: no error. A real CI run happens on push to confirm end-to-end (not
reproducible locally without `act` or similar).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: install OpenCV for the cv-engine build"
```

---

## Task 8: Docker — install OpenCV, ship the models directory

**Files:**
- Modify: `infra/docker/backend.Dockerfile`

**Interfaces:** None — infra-only change.

- [ ] **Step 1: Update the builder stage**

In `infra/docker/backend.Dockerfile`, update the `apt-get install` line in
the builder stage:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build libopencv-dev curl \
    && rm -rf /var/lib/apt/lists/*
```

(`curl` is needed by `fetch_models.sh`.)

- [ ] **Step 2: Copy the fetched models into the final stage**

After the existing `COPY --from=builder /src/backend/.venv /app/.venv` line,
add:

```dockerfile
COPY --from=builder /src/cv-engine/models /src/cv-engine/models
```

This must land at the same absolute path (`/src/cv-engine/models`) that
Task 5's `configure_file` baked into the compiled extension at build time —
the builder stage's `WORKDIR /src` plus `COPY cv-engine ./cv-engine` already
makes `/src/cv-engine` the `CMAKE_SOURCE_DIR` seen during that build, so this
path is consistent by construction; don't change the builder's `WORKDIR` or
copy destination without re-checking this.

- [ ] **Step 3: Add `libopencv-dev`'s runtime shared libs to the final stage**

The final stage is `python:3.12-slim`, which doesn't have OpenCV's runtime
`.so` files. Add before the existing `ENV PATH` line:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopencv-core406 libopencv-imgproc406 libopencv-videoio406 libopencv-dnn406 \
    && rm -rf /var/lib/apt/lists/*
```

(Package name suffix (`406`) tracks the OpenCV version `apt` resolves for
`libopencv-dev` in the builder stage — check `apt-cache policy libopencv-dev`
in the builder image if the build fails with a missing-package error, and
adjust the suffix to match.)

- [ ] **Step 4: Build the image and smoke-test it**

Run: `docker build -f infra/docker/backend.Dockerfile -t formiq-backend-test .`
then:
```bash
docker run --rm formiq-backend-test python -c "import cv_engine; print(cv_engine.NUM_LANDMARKS)"
```
Expected: image builds successfully; the smoke command prints `33` with no
import error (confirms OpenCV runtime libs and the models directory are both
present and correctly wired at the compiled path).

- [ ] **Step 5: Commit**

```bash
git add infra/docker/backend.Dockerfile
git commit -m "docker: install OpenCV and ship pose models in the backend image"
```

---

## Post-plan state

After Task 8, `POST /analyze/{exercise}` returns real per-frame keypoint
counts (`frame_count`) reflecting actual pose extraction — `reps` still
returns `[]` since rep-segmentation/scoring is explicitly out of this plan's
scope (separate spec, per the brainstorming decomposition). The frontend's
raw-JSON dump will visibly show non-zero `frame_count` for a real upload,
which is the observable end-to-end signal this plan is done.
