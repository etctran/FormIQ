// cv-engine/src/pose_detector.cpp
#include "pose_detector.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <vector>

#include <opencv2/dnn.hpp>
#include <opencv2/imgproc.hpp>
#include <tensorflow/lite/kernels/register.h>

namespace formiq {
namespace {

// Constants verified against MediaPipe's public pose_detection_cpu.pbtxt
// (SsdAnchorsCalculatorOptions / TensorsToDetectionsCalculatorOptions).
constexpr int kInputSize = 224;
constexpr int kNumLayers = 5;
constexpr float kMinScale = 0.1484375F;
constexpr float kMaxScale = 0.75F;
constexpr int kStrides[kNumLayers] = {8, 16, 32, 32, 32};
constexpr float kAnchorOffset = 0.5F;
constexpr int kNumBoxes = 2254;
constexpr int kNumCoords = 12;
constexpr float kScoreClippingThresh = 100.0F;
constexpr float kMinScoreThresh = 0.5F;
constexpr float kBoxScale = 224.0F;
constexpr float kNmsIouThreshold = 0.3F;  // our own choice, not from MediaPipe config

struct Anchor {
    float x_center;
    float y_center;
};

float ScaleForLayer(int layer_index) {
    if (kNumLayers == 1) return kMinScale;
    return kMinScale +
           (kMaxScale - kMinScale) * static_cast<float>(layer_index) /
               static_cast<float>(kNumLayers - 1);
}

// Reproduces MediaPipe's SsdAnchorsCalculator with fixed_anchor_size=true
// and a single aspect_ratio of 1.0 (which yields 2 anchors per grid cell,
// matching num_boxes=2254). fixed_anchor_size means every anchor's
// width/height is 1.0 in normalized space — only x_center/y_center vary.
std::vector<Anchor> GenerateAnchors() {
    std::vector<Anchor> anchors;
    anchors.reserve(kNumBoxes);
    for (int layer = 0; layer < kNumLayers; ++layer) {
        const int stride = kStrides[layer];
        const int feature_size =
            static_cast<int>(std::ceil(static_cast<float>(kInputSize) / stride));
        for (int y = 0; y < feature_size; ++y) {
            for (int x = 0; x < feature_size; ++x) {
                const float x_center = (x + kAnchorOffset) / feature_size;
                const float y_center = (y + kAnchorOffset) / feature_size;
                // aspect_ratios = [1.0] yields 2 anchors per cell (the
                // standard extra scale-interpolated anchor for ratio 1.0).
                anchors.push_back({x_center, y_center});
                anchors.push_back({x_center, y_center});
            }
        }
    }
    return anchors;
}

float Sigmoid(float x) {
    x = std::clamp(x, -kScoreClippingThresh, kScoreClippingThresh);
    return 1.0F / (1.0F + std::exp(-x));
}

// Square-pads frame_bgr to a square (letterbox) then resizes to
// kInputSize x kInputSize, matching MediaPipe's ImageToTensorCalculator
// FIT scaling, converts to RGB float32 in [-1, 1]. Returns an HxWx3
// CV_32FC3 cv::Mat whose row-major byte layout matches the interpreter's
// expected NHWC input tensor exactly (safe to memcpy directly). Also
// returns the square side length used (in original pixels) and the
// top/left padding, so detected boxes can be mapped back.
cv::Mat PrepareInput(const cv::Mat& frame_bgr, int& square_side, int& pad_x, int& pad_y) {
    square_side = std::max(frame_bgr.cols, frame_bgr.rows);
    pad_x = (square_side - frame_bgr.cols) / 2;
    pad_y = (square_side - frame_bgr.rows) / 2;

    cv::Mat square = cv::Mat::zeros(square_side, square_side, frame_bgr.type());
    frame_bgr.copyTo(square(cv::Rect(pad_x, pad_y, frame_bgr.cols, frame_bgr.rows)));

    cv::Mat resized;
    cv::resize(square, resized, cv::Size(kInputSize, kInputSize));

    cv::Mat rgb;
    cv::cvtColor(resized, rgb, cv::COLOR_BGR2RGB);

    cv::Mat float_image;
    rgb.convertTo(float_image, CV_32FC3, 1.0 / 127.5, -1.0);  // [0,255] -> [-1,1]
    return float_image;
}

}  // namespace

PoseDetector::PoseDetector(const std::string& model_path) {
    model_ = tflite::FlatBufferModel::BuildFromFile(model_path.c_str());
    if (!model_) {
        throw std::runtime_error("PoseDetector: failed to load model at " + model_path);
    }
    tflite::ops::builtin::BuiltinOpResolver resolver;
    tflite::InterpreterBuilder builder(*model_, resolver);
    builder(&interpreter_);
    if (!interpreter_ || interpreter_->AllocateTensors() != kTfLiteOk) {
        throw std::runtime_error("PoseDetector: failed to build interpreter for " + model_path);
    }
}

std::optional<Roi> PoseDetector::Detect(const cv::Mat& frame_bgr) const {
    int square_side = 0;
    int pad_x = 0;
    int pad_y = 0;
    cv::Mat input_image = PrepareInput(frame_bgr, square_side, pad_x, pad_y);

    float* input_tensor = interpreter_->typed_input_tensor<float>(0);
    std::memcpy(input_tensor, input_image.ptr<float>(0), input_image.total() * input_image.elemSize());

    if (interpreter_->Invoke() != kTfLiteOk) return std::nullopt;

    // Select outputs by element count, not index — export order isn't
    // guaranteed. Same approach as the original cv::dnn version used.
    int regressors_idx = -1;
    int scores_idx = -1;
    for (std::size_t i = 0; i < interpreter_->outputs().size(); ++i) {
        const TfLiteTensor* t = interpreter_->output_tensor(static_cast<int>(i));
        int count = 1;
        for (int d = 0; d < t->dims->size; ++d) count *= t->dims->data[d];
        if (count == kNumBoxes * kNumCoords) regressors_idx = static_cast<int>(i);
        else if (count == kNumBoxes) scores_idx = static_cast<int>(i);
    }
    if (regressors_idx < 0 || scores_idx < 0) return std::nullopt;

    const float* reg = interpreter_->typed_output_tensor<float>(regressors_idx);
    const float* sc = interpreter_->typed_output_tensor<float>(scores_idx);

    static const std::vector<Anchor> anchors = GenerateAnchors();

    std::vector<cv::Rect2d> boxes;
    std::vector<float> confidences;
    for (int i = 0; i < kNumBoxes && i < static_cast<int>(anchors.size()); ++i) {
        const float score = Sigmoid(sc[i]);
        if (score < kMinScoreThresh) continue;

        const float* box = reg + (i * kNumCoords);
        // reverse_output_order=true -> raw order is x, y, w, h.
        const float cx = box[0] / kBoxScale + anchors[i].x_center;
        const float cy = box[1] / kBoxScale + anchors[i].y_center;
        const float w = box[2] / kBoxScale;
        const float h = box[3] / kBoxScale;

        boxes.emplace_back(cx - w / 2, cy - h / 2, w, h);
        confidences.push_back(score);
    }

    if (boxes.empty()) return std::nullopt;

    std::vector<int> keep;
    cv::dnn::NMSBoxes(boxes, confidences, kMinScoreThresh, kNmsIouThreshold, keep);
    if (keep.empty()) return std::nullopt;

    // Highest-confidence surviving box, mapped from normalized square-input
    // space back to original frame pixel coordinates.
    int best = keep[0];
    for (int idx : keep) {
        if (confidences[idx] > confidences[best]) best = idx;
    }

    const cv::Rect2d& box = boxes[best];
    Roi roi;
    roi.x_center = static_cast<float>((box.x + box.width / 2) * square_side) - pad_x;
    roi.y_center = static_cast<float>((box.y + box.height / 2) * square_side) - pad_y;
    roi.width = static_cast<float>(box.width * square_side);
    roi.height = static_cast<float>(box.height * square_side);
    return roi;
}

}  // namespace formiq
