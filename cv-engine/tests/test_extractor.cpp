#include <cassert>

#include "extractor.h"
#include "keypoints.h"

int main() {
    assert(formiq::kNumLandmarks == 33);

    formiq::KeypointExtractor extractor;
    const std::vector<formiq::Frame> frames = extractor.Extract("nonexistent.mp4");
    assert(frames.empty());

    return 0;
}
