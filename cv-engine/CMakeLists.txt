cmake_minimum_required(VERSION 3.18)
project(cv_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)
find_package(OpenCV 4.8 REQUIRED COMPONENTS core imgproc videoio dnn)

set(CV_ENGINE_MODELS_DIR "${CMAKE_SOURCE_DIR}/models")

configure_file(
  "${CMAKE_SOURCE_DIR}/include/model_paths.h.in"
  "${CMAKE_BINARY_DIR}/generated/model_paths.h"
  @ONLY
)

add_custom_command(
  OUTPUT "${CV_ENGINE_MODELS_DIR}/pose_detection.tflite"
         "${CV_ENGINE_MODELS_DIR}/pose_landmark_lite.tflite"
  COMMAND bash "${CMAKE_SOURCE_DIR}/scripts/fetch_models.sh" "${CV_ENGINE_MODELS_DIR}"
  COMMENT "Fetching MediaPipe pose models"
  VERBATIM
)
add_custom_target(fetch_models ALL
  DEPENDS "${CV_ENGINE_MODELS_DIR}/pose_detection.tflite"
          "${CV_ENGINE_MODELS_DIR}/pose_landmark_lite.tflite"
)

add_library(cv_engine_core STATIC
  src/extractor.cpp
  src/roi_tracker.cpp
  src/pose_detector.cpp
  src/landmark_regressor.cpp
)
target_include_directories(cv_engine_core PUBLIC include)
target_include_directories(cv_engine_core PUBLIC "${CMAKE_BINARY_DIR}/generated")
target_link_libraries(cv_engine_core PUBLIC ${OpenCV_LIBS})
target_include_directories(cv_engine_core PUBLIC ${OpenCV_INCLUDE_DIRS})
add_dependencies(cv_engine_core fetch_models)

include(FetchContent)
FetchContent_Declare(
  tensorflow
  GIT_REPOSITORY https://github.com/tensorflow/tensorflow.git
  GIT_TAG v2.21.0
  GIT_SHALLOW TRUE
  SOURCE_SUBDIR tensorflow/lite
)
set(TFLITE_ENABLE_XNNPACK OFF CACHE BOOL "" FORCE)
set(TFLITE_ENABLE_GPU OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(tensorflow)

target_link_libraries(cv_engine_core PUBLIC tensorflow-lite)

pybind11_add_module(cv_engine src/bindings.cpp)
target_link_libraries(cv_engine PRIVATE cv_engine_core)
target_include_directories(cv_engine PRIVATE include)

install(TARGETS cv_engine LIBRARY DESTINATION .)

enable_testing()
add_subdirectory(tests)
