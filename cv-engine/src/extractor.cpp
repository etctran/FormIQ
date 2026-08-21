#include "extractor.h"

#include <opencv2/videoio.hpp>

#include "roi_tracker.h"

namespace formiq {
namespace {

// Run pose inference on roughly every 4th decoded frame (~7.5fps effective
// at native 30fps) rather than every frame — the primary lever for landing
// near the spec's typical-case latency target on 30-90s clips. Tunable, not
// a hard contract.
constexpr int kFrameSampleInterval = 4;

}  // namespace

// Both models load here, at construction — a missing/corrupt model file
// throws immediately (propagated from PoseDetector/LandmarkRegressor's own
// constructors, which fail via LiteRT's FlatBufferModel/InterpreterBuilder),
// not partway through a later Extract() call.
KeypointExtractor::KeypointExtractor(const std::string& detector_model_path,
                                      const std::string& landmark_model_path)
    : detector_(detector_model_path), regressor_(landmark_model_path) {}

std::vector<Frame> KeypointExtractor::Extract(const std::string& video_path) const {
    cv::VideoCapture capture(video_path);
    if (!capture.isOpened()) return {};

    const double fps = capture.get(cv::CAP_PROP_FPS);
    if (fps <= 0.0) return {};

    RoiTracker tracker;

    std::vector<Frame> frames;
    cv::Mat raw_frame;
    int frame_index = 0;
    while (capture.read(raw_frame)) {
        if (frame_index % kFrameSampleInterval == 0) {
            Frame frame;
            frame.timestamp_sec = static_cast<double>(frame_index) / fps;

            if (tracker.ShouldRedetect()) {
                tracker.OnDetection(detector_.Detect(raw_frame));
            } else {
                tracker.OnDetection(std::nullopt);  // reuse: age the tracked ROI
            }

            if (tracker.Current().has_value()) {
                frame.landmarks = regressor_.Regress(raw_frame, *tracker.Current());
            }
            // else: no ROI available this frame -> frame.landmarks stays empty

            frames.push_back(std::move(frame));
        }
        ++frame_index;
    }

    return frames;
}

}  // namespace formiq
