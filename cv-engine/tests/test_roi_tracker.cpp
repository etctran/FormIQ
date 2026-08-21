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
