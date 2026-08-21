// cv-engine/tests/test_extractor.cpp
#include <cassert>
#include <exception>

#include "extractor.h"
#include "keypoints.h"

int main() {
    assert(formiq::kNumLandmarks == 33);

    // Nonexistent video still returns empty, unchanged contract.
    {
        formiq::KeypointExtractor extractor;
        const std::vector<formiq::Frame> frames = extractor.Extract("nonexistent.mp4");
        assert(frames.empty());
    }

    // Real short clip produces a non-empty, correctly-shaped frame sequence.
    {
        formiq::KeypointExtractor extractor;
        const std::vector<formiq::Frame> frames =
            extractor.Extract("tests/fixtures/sample_clip.mp4");
        assert(!frames.empty());
        for (const auto& frame : frames) {
            // landmarks is either empty (no detection that frame) or exactly
            // kNumLandmarks — never a partial set.
            assert(frame.landmarks.empty() ||
                   frame.landmarks.size() == formiq::kNumLandmarks);
        }
        // The loop above passes vacuously if detection is dead on every frame,
        // so assert detection actually fired: the fixture clip has a real,
        // detectable person in it.
        int populated = 0;
        for (const auto& frame : frames) {
            if (!frame.landmarks.empty()) ++populated;
        }
        assert(populated > 0);
        // Timestamps must be non-decreasing and reflect real video time.
        for (std::size_t i = 1; i < frames.size(); ++i) {
            assert(frames[i].timestamp_sec >= frames[i - 1].timestamp_sec);
        }
    }

    // A bad model path must throw at construction time (fail fast), not
    // silently defer the failure into Extract().
    {
        bool threw = false;
        try {
            formiq::KeypointExtractor bad_extractor("nonexistent_detector.tflite",
                                                      "nonexistent_landmark.tflite");
        } catch (const std::exception&) {
            threw = true;
        }
        assert(threw);
    }

    return 0;
}
