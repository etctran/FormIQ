#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>

#include "extractor.h"
#include "keypoints.h"
#include "model_paths.h"

namespace py = pybind11;

PYBIND11_MODULE(cv_engine, m) {
    m.doc() = "FormIQ pose keypoint extraction (MediaPipe + OpenCV, pybind11 bindings)";

    m.attr("NUM_LANDMARKS") = formiq::kNumLandmarks;

    py::class_<formiq::Keypoint>(m, "Keypoint")
        .def(py::init<>())
        .def_readwrite("x", &formiq::Keypoint::x)
        .def_readwrite("y", &formiq::Keypoint::y)
        .def_readwrite("z", &formiq::Keypoint::z)
        .def_readwrite("visibility", &formiq::Keypoint::visibility);

    py::class_<formiq::Frame>(m, "Frame")
        .def(py::init<>())
        .def_readwrite("timestamp_sec", &formiq::Frame::timestamp_sec)
        .def_readwrite("landmarks", &formiq::Frame::landmarks);

    py::class_<formiq::KeypointExtractor>(m, "KeypointExtractor")
        .def(py::init<std::string, std::string>(),
             py::arg("detector_model_path") = formiq::kDefaultPoseDetectorModelPath,
             py::arg("landmark_model_path") = formiq::kDefaultPoseLandmarkModelPath)
        .def("extract", &formiq::KeypointExtractor::Extract, py::arg("video_path"));
}
