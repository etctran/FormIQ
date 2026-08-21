// cv-engine/tests/test_pose_detector.cpp
#include <cassert>
#include <cmath>
#include <cstddef>
#include <vector>

#include <opencv2/opencv.hpp>

#include "pose_detector.h"

namespace {

bool Near(float a, float b) { return std::fabs(a - b) < 1e-5F; }

// Asserts anchor `index` sits at grid cell (cell_x, cell_y) of a
// feature_size x feature_size grid, i.e. center ((x+0.5)/F, (y+0.5)/F).
void AssertAnchorAt(const std::vector<formiq::detail::Anchor>& anchors, std::size_t index,
                    int cell_x, int cell_y, int feature_size) {
    const float f = static_cast<float>(feature_size);
    assert(index < anchors.size());
    assert(Near(anchors[index].x_center, (static_cast<float>(cell_x) + 0.5F) / f));
    assert(Near(anchors[index].y_center, (static_cast<float>(cell_y) + 0.5F) / f));
}

// MediaPipe's SsdAnchorsCalculator merges CONSECUTIVE layers sharing a stride
// into ONE grid pass whose per-cell anchor count is the sum of the merged
// layers' counts, emitted in cell-major order. With kStrides = {8,16,32,32,32}
// and 2 anchors per cell per layer, that gives three passes:
//
//   Pass A  layer {0}      stride  8  F=ceil(224/8)=28  2/cell  28*28*2 = 1568
//           -> anchor indices [   0, 1568)
//   Pass B  layer {1}      stride 16  F=ceil(224/16)=14 2/cell  14*14*2 =  392
//           -> anchor indices [1568, 1960)
//   Pass C  layers {2,3,4} stride 32  F=ceil(224/32)=7  6/cell   7*7*6  =  294
//           -> anchor indices [1960, 2254)
//
//   total = 1568 + 392 + 294 = 2254 = kNumBoxes (the model's box-count dim).
//
// Within a pass starting at base index B, grid F x F, A anchors per cell:
//   cell = (i - B) / A ;  y = cell / F ;  x = cell % F ;
//   center = ((x + 0.5) / F, (y + 0.5) / F)
//
// The regression this guards: the old code ran layers 2, 3, 4 as three
// INDEPENDENT 7x7 passes of 2 anchors each. Same 294 total, but a different
// index -> center mapping for 288 of those 294 anchors. Since the regressor
// output is indexed by anchor, that decodes boxes against the wrong grid cell.
void TestAnchorLayout() {
    const std::vector<formiq::detail::Anchor> anchors = formiq::detail::GenerateAnchors();

    // Total must match the model's num_boxes exactly, or Detect() silently
    // truncates its scan of the score/regressor tensors.
    assert(anchors.size() == 2254);

    // --- Pass A: stride 8, F=28, base 0, 2 anchors/cell -------------------
    // i=0    -> cell (0-0)/2 = 0    -> x=0,  y=0
    AssertAnchorAt(anchors, 0, 0, 0, 28);
    // i=1567 -> cell 1567/2 = 783   -> x=783%28=27, y=783/28=27  (last of A)
    AssertAnchorAt(anchors, 1567, 27, 27, 28);

    // --- Pass B: stride 16, F=14, base 1568, 2 anchors/cell ---------------
    // i=1568 -> cell 0              -> x=0,  y=0   (first of B)
    AssertAnchorAt(anchors, 1568, 0, 0, 14);
    // i=1959 -> cell (1959-1568)/2 = 195 -> x=195%14=13, y=195/14=13 (last of B)
    AssertAnchorAt(anchors, 1959, 13, 13, 14);

    // --- Pass C: stride 32, F=7, base 1960, 6 anchors/cell ----------------
    // These are the indices the merge bug moves. Old (three independent
    // 2-per-cell passes) vs. new (one merged 6-per-cell pass) values are
    // noted where they disagree.
    //
    // i=1960 -> cell 0 -> x=0, y=0. (Old agrees here by coincidence: it is
    // index 0 of layer 2's own pass, also cell (0,0). Hence the later pins.)
    AssertAnchorAt(anchors, 1960, 0, 0, 7);
    // i=1965 -> offset 5,  cell 5/6 = 0   -> x=0, y=0  (still cell 0: a cell
    //           owns 6 consecutive anchors, 1960..1965).
    //           Old: offset 5, cell 5/2 = 2 -> x=2, y=0. DIFFERS.
    AssertAnchorAt(anchors, 1965, 0, 0, 7);
    // i=1966 -> offset 6,  cell 6/6 = 1   -> x=1, y=0  (first anchor of the
    //           second cell).
    //           Old: offset 6, cell 3 -> x=3, y=0. DIFFERS.
    AssertAnchorAt(anchors, 1966, 1, 0, 7);
    // i=2000 -> offset 40, cell 40/6 = 6  -> x=6%7=6, y=6/7=0.
    //           Old: offset 40, cell 20 -> x=6, y=2. DIFFERS in y.
    AssertAnchorAt(anchors, 2000, 6, 0, 7);
    // i=2100 -> offset 140, cell 140/6 = 23 -> x=23%7=2, y=23/7=3.
    //           Old: 2100 fell in layer 3's pass [2058,2156), offset 42,
    //           cell 21 -> x=0, y=3. DIFFERS in x.
    AssertAnchorAt(anchors, 2100, 2, 3, 7);
    // i=2253 -> offset 293, cell 293/6 = 48 -> x=48%7=6, y=48/7=6 (last
    //           anchor overall; old agrees here by coincidence too).
    AssertAnchorAt(anchors, 2253, 6, 6, 7);

    // Every anchor in a cell shares one center, and cells advance in
    // cell-major (row-major) order. Verified exhaustively for pass C, the
    // only pass the merge affects.
    for (std::size_t i = 1960; i < 2254; ++i) {
        const std::size_t cell = (i - 1960) / 6;
        AssertAnchorAt(anchors, i, static_cast<int>(cell % 7), static_cast<int>(cell / 7), 7);
    }
}

}  // namespace

int main() {
    TestAnchorLayout();

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
