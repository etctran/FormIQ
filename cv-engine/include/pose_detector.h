// cv-engine/include/pose_detector.h
#pragma once

#include <memory>
#include <optional>
#include <string>

#include <opencv2/core.hpp>
#include <tensorflow/lite/interpreter.h>
#include <tensorflow/lite/model.h>

#include "roi.h"

namespace formiq {

// Runs MediaPipe's published pose-detection TFLite model (SSD-style,
// 2254 anchors) via LiteRT's C++ interpreter to find a single person's
// bounding box in a frame. Returns std::nullopt if no box clears
// min_score_thresh.
class PoseDetector {
public:
    explicit PoseDetector(const std::string& model_path);

    std::optional<Roi> Detect(const cv::Mat& frame_bgr) const;

private:
    std::unique_ptr<tflite::FlatBufferModel> model_;
    std::unique_ptr<tflite::Interpreter> interpreter_;
};

}  // namespace formiq
