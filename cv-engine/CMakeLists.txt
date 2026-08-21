cmake_minimum_required(VERSION 3.18)
project(cv_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

add_library(cv_engine_core STATIC
  src/extractor.cpp
)
target_include_directories(cv_engine_core PUBLIC include)

pybind11_add_module(cv_engine src/bindings.cpp)
target_link_libraries(cv_engine PRIVATE cv_engine_core)
target_include_directories(cv_engine PRIVATE include)

install(TARGETS cv_engine LIBRARY DESTINATION .)

enable_testing()
add_subdirectory(tests)
