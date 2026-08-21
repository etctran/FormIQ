add_executable(test_extractor test_extractor.cpp)
target_link_libraries(test_extractor PRIVATE cv_engine_core)
add_test(NAME test_extractor COMMAND test_extractor)

add_executable(test_roi_tracker test_roi_tracker.cpp)
target_link_libraries(test_roi_tracker PRIVATE cv_engine_core)
add_test(NAME test_roi_tracker COMMAND test_roi_tracker)

add_executable(test_pose_detector test_pose_detector.cpp)
target_link_libraries(test_pose_detector PRIVATE cv_engine_core ${OpenCV_LIBS})
target_include_directories(test_pose_detector PRIVATE ${OpenCV_INCLUDE_DIRS})
add_test(NAME test_pose_detector COMMAND test_pose_detector
         WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
