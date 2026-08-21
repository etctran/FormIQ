// cv-engine/src/landmark_regressor.cpp
#include "landmark_regressor.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <stdexcept>

#include <opencv2/imgproc.hpp>
#include <tensorflow/lite/kernels/register.h>

namespace formiq {
namespace {

constexpr int kInputSize = 256;
constexpr int kNumRawLandmarks = 39;  // 33 body + 6 auxiliary (unused here)
constexpr int kValuesPerLandmark = 5; // x, y, z, visibility, presence

float Sigmoid(float x) { return 1.0F / (1.0F + std::exp(-x)); }

cv::Rect ClampedCropRect(const Roi& roi, const cv::Mat& frame) {
    const int x0 = static_cast<int>(std::round(roi.x_center - roi.width / 2));
    const int y0 = static_cast<int>(std::round(roi.y_center - roi.height / 2));
    cv::Rect rect(x0, y0, static_cast<int>(std::round(roi.width)),
                  static_cast<int>(std::round(roi.height)));
    return rect & cv::Rect(0, 0, frame.cols, frame.rows);
}

}  // namespace

LandmarkRegressor::LandmarkRegressor(const std::string& model_path) {
    model_ = tflite::FlatBufferModel::BuildFromFile(model_path.c_str());
    if (!model_) {
        throw std::runtime_error("LandmarkRegressor: failed to load model at " + model_path);
    }
    tflite::ops::builtin::BuiltinOpResolver resolver;
    tflite::InterpreterBuilder builder(*model_, resolver);
    builder(&interpreter_);
    if (!interpreter_ || interpreter_->AllocateTensors() != kTfLiteOk) {
        throw std::runtime_error("LandmarkRegressor: failed to build interpreter for " + model_path);
    }
}

std::vector<Keypoint> LandmarkRegressor::Regress(const cv::Mat& frame_bgr, const Roi& roi) const {
    cv::Rect crop_rect = ClampedCropRect(roi, frame_bgr);
    std::vector<Keypoint> result(kNumLandmarks);
    if (crop_rect.width <= 0 || crop_rect.height <= 0) {
        return result;  // all-zero, visibility 0 — degenerate ROI
    }

    cv::Mat cropped = frame_bgr(crop_rect);
    cv::Mat resized;
    cv::resize(cropped, resized, cv::Size(kInputSize, kInputSize));
    cv::Mat rgb;
    cv::cvtColor(resized, rgb, cv::COLOR_BGR2RGB);
    cv::Mat float_image;
    rgb.convertTo(float_image, CV_32FC3, 1.0 / 127.5, -1.0);  // [0,255] -> [-1,1]

    float* input_tensor = interpreter_->typed_input_tensor<float>(0);
    std::memcpy(input_tensor, float_image.ptr<float>(0), float_image.total() * float_image.elemSize());

    if (interpreter_->Invoke() != kTfLiteOk) return result;

    // The model has multiple outputs (landmarks, presence score,
    // segmentation mask, heatmap, world landmarks — confirmed via Step 1
    // introspection). Select the landmarks tensor by exact element count
    // (39 landmarks x 5 values = 195), not by "largest" — the heatmap
    // output ([1,64,64,39] = 159744 elements) is larger than the landmarks
    // tensor, so a largest-wins selection would pick the wrong tensor.
    // Same exact-match-by-count approach Task 3's PoseDetector uses.
    int landmarks_idx = -1;
    for (std::size_t i = 0; i < interpreter_->outputs().size(); ++i) {
        const TfLiteTensor* t = interpreter_->output_tensor(static_cast<int>(i));
        int count = 1;
        for (int d = 0; d < t->dims->size; ++d) count *= t->dims->data[d];
        if (count == kNumRawLandmarks * kValuesPerLandmark) {
            landmarks_idx = static_cast<int>(i);
            break;
        }
    }
    if (landmarks_idx < 0) {
        return result;
    }

    const float* raw = interpreter_->typed_output_tensor<float>(landmarks_idx);
    const float sx = static_cast<float>(crop_rect.width) / kInputSize;
    const float sy = static_cast<float>(crop_rect.height) / kInputSize;

    for (std::size_t i = 0; i < kNumLandmarks; ++i) {
        const float* lm = raw + (i * kValuesPerLandmark);
        Keypoint kp;
        kp.x = crop_rect.x + lm[0] * sx;
        kp.y = crop_rect.y + lm[1] * sy;
        kp.z = lm[2] * sx;  // z shares x's scale, matching MediaPipe's convention
        kp.visibility = Sigmoid(lm[3]);
        result[i] = kp;
    }
    return result;
}

}  // namespace formiq
