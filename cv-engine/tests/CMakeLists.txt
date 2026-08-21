# Every test here states its invariants with assert(), but the default build
# type is Release, whose CMAKE_CXX_FLAGS_RELEASE carries -DNDEBUG — which
# compiles assert() to a no-op and makes the whole suite pass vacuously.
# Undefine it for test targets only (it stays on for the library and the
# pybind11 module, which are the perf-critical path).
if(NOT MSVC)
  add_compile_options(-UNDEBUG)
else()
  add_compile_options(/UNDEBUG)
endif()

add_executable(test_extractor test_extractor.cpp)
target_link_libraries(test_extractor PRIVATE cv_engine_core)
add_test(NAME test_extractor COMMAND test_extractor
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

add_executable(test_roi_tracker test_roi_tracker.cpp)
target_link_libraries(test_roi_tracker PRIVATE cv_engine_core)
add_test(NAME test_roi_tracker COMMAND test_roi_tracker)

add_executable(test_pose_detector test_pose_detector.cpp)
target_link_libraries(test_pose_detector PRIVATE cv_engine_core ${OpenCV_LIBS})
target_include_directories(test_pose_detector PRIVATE ${OpenCV_INCLUDE_DIRS})
add_test(NAME test_pose_detector COMMAND test_pose_detector
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

add_executable(test_landmark_regressor test_landmark_regressor.cpp)
target_link_libraries(test_landmark_regressor PRIVATE cv_engine_core ${OpenCV_LIBS})
target_include_directories(test_landmark_regressor PRIVATE ${OpenCV_INCLUDE_DIRS})
add_test(NAME test_landmark_regressor COMMAND test_landmark_regressor
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
