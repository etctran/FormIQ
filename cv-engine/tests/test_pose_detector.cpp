// cv-engine/tests/test_pose_detector.cpp
#include <cassert>
#include <opencv2/opencv.hpp>

#include "pose_detector.h"

int main() {
    formiq::PoseDetector detector("models/pose_detection.tflite");

    // A blank black frame has no person — must return nullopt, not a
    // fabricated box.
    cv::Mat blank = cv::Mat::zeros(480, 640, CV_8UC3);
    auto blank_result = detector.Detect(blank);
    assert(!blank_result.has_value());

    // A real photo of a person must return a plausible, in-bounds box.
    cv::Mat person = cv::imread("tests/fixtures/person.jpg");
    assert(!person.empty());  // fixture must exist and be readable
    auto person_result = detector.Detect(person);
    assert(person_result.has_value());
    const formiq::Roi& roi = *person_result;
    assert(roi.width > 0.0F && roi.height > 0.0F);
    assert(roi.x_center - roi.width / 2 >= -1.0F);   // small tolerance
    assert(roi.y_center - roi.height / 2 >= -1.0F);
    assert(roi.x_center + roi.width / 2 <= person.cols + 1.0F);
    assert(roi.y_center + roi.height / 2 <= person.rows + 1.0F);

    return 0;
}
