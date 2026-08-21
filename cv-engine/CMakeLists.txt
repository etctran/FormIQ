cmake_minimum_required(VERSION 3.18)
project(cv_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)
find_package(OpenCV 4.8 REQUIRED COMPONENTS core imgproc videoio dnn)

set(CV_ENGINE_MODELS_DIR "${CMAKE_SOURCE_DIR}/models")

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
)
target_include_directories(cv_engine_core PUBLIC include)
target_link_libraries(cv_engine_core PUBLIC ${OpenCV_LIBS})
target_include_directories(cv_engine_core PUBLIC ${OpenCV_INCLUDE_DIRS})
add_dependencies(cv_engine_core fetch_models)

pybind11_add_module(cv_engine src/bindings.cpp)
target_link_libraries(cv_engine PRIVATE cv_engine_core)
target_include_directories(cv_engine PRIVATE include)

install(TARGETS cv_engine LIBRARY DESTINATION .)

enable_testing()
add_subdirectory(tests)
