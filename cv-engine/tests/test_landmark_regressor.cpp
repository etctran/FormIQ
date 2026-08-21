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
