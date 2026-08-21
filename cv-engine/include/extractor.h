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
