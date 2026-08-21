#pragma once

#include <cstddef>
#include <vector>

namespace formiq {

// MediaPipe Pose landmark count. Python bindings (src/bindings.cpp) and
// backend/app/schemas/keypoint.py must mirror this struct exactly.
inline constexpr std::size_t kNumLandmarks = 33;

struct Keypoint {
    float x = 0.0F;
    float y = 0.0F;
    float z = 0.0F;
    float visibility = 0.0F;
};

struct Frame {
    double timestamp_sec = 0.0;
    std::vector<Keypoint> landmarks;  // size() == kNumLandmarks when populated
};

}  // namespace formiq
