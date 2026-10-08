# ==============================================================================
# Reaktar - Reactive Actor Framework for AUTOSAR Adaptive
# Part of the Pyarx project: https://github.com/pyarxlab/reaktar
#
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Pyarx Lab
# ==============================================================================

cmake_minimum_required(VERSION 3.16)
project(reaktar VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Threads REQUIRED)

# Interface library for consumer applications (pure Reaktar headers)
add_library(reaktar INTERFACE)
target_include_directories(reaktar INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(reaktar INTERFACE Threads::Threads)

# Smoke Testing
enable_testing()

# Test harness helper interface (supplies mock AUTOSAR environment for tests only)
add_library(reaktar_test_mock INTERFACE)
target_include_directories(reaktar_test_mock INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/mock
)

add_executable(reaktar_smoke_tests
    tests/test_smoke.cpp
)
target_link_libraries(reaktar_smoke_tests PRIVATE reaktar reaktar_test_mock)
add_test(NAME core_smoke_tests COMMAND reaktar_smoke_tests)

