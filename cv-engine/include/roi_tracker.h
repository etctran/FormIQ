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
