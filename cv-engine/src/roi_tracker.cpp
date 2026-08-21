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
