// cv-engine/include/landmark_regressor.h
#pragma once

#include <memory>
#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <tensorflow/lite/interpreter.h>
#include <tensorflow/lite/model.h>

#include "keypoints.h"
#include "roi.h"

namespace formiq {

// Runs MediaPipe's published pose-landmark TFLite model via LiteRT's C++
// interpreter on a frame cropped to a Roi. Always returns kNumLandmarks (33)
// keypoints — per-keypoint confidence is carried in Keypoint::visibility,
// not a per-call optional (a low-confidence regression still returns 33
// keypoints with low visibility, unlike PoseDetector's per-frame miss).
class LandmarkRegressor {
public:
    explicit LandmarkRegressor(const std::string& model_path);

    std::vector<Keypoint> Regress(const cv::Mat& frame_bgr, const Roi& roi) const;

private:
    std::unique_ptr<tflite::FlatBufferModel> model_;
    std::unique_ptr<tflite::Interpreter> interpreter_;
};

}  // namespace formiq
