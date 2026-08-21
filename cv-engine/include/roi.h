// cv-engine/include/roi.h
#pragma once

namespace formiq {

// A person's region of interest in original-frame pixel coordinates.
// Axis-aligned — no rotation, per this plan's single-subject-upright
// simplification (see spec).
struct Roi {
    float x_center = 0.0F;
    float y_center = 0.0F;
    float width = 0.0F;
    float height = 0.0F;
};

}  // namespace formiq
