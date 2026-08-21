// cv-engine/include/pose_detector.h
#pragma once

#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <opencv2/core.hpp>
#include <tensorflow/lite/interpreter.h>
#include <tensorflow/lite/model.h>

#include "roi.h"

namespace formiq {

namespace detail {

// One SSD anchor. fixed_anchor_size=true in MediaPipe's config means every
// anchor's width/height is 1.0 in normalized space, so only the center varies.
struct Anchor {
    float x_center;
    float y_center;
};

// Reproduces MediaPipe's SsdAnchorsCalculator for the pose-detection model
// (2254 anchors). Declared here so tests can pin the anchor layout directly;
// the implementation lives in pose_detector.cpp.
std::vector<Anchor> GenerateAnchors();

}  // namespace detail

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
