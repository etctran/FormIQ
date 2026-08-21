#pragma once

#include <string>
#include <vector>

#include "keypoints.h"

namespace formiq {

// Extracts per-frame pose keypoints from a video file.
//
// Scaffolding phase: returns an empty frame sequence for any input. Real
// MediaPipe + OpenCV extraction lands once the end-to-end path (this
// binding -> FastAPI -> React) is verified.
class KeypointExtractor {
public:
    std::vector<Frame> Extract(const std::string& video_path) const;
};

}  // namespace formiq
