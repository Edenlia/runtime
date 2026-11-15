# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

cmake_minimum_required(VERSION 3.26)
project(WasmTargetTests C CXX)

include(../../configurepaths.cmake)
include(${CLR_ENG_NATIVE_DIR}/configurecompiler.cmake)

if(NOT CLR_CMAKE_TARGET_ARCH_WASM OR NOT CLR_CMAKE_HOST_ARCH_WASM)
    message(FATAL_ERROR "This test requires a native WebAssembly compiler.")
endif()
if(NOT ARCH_HOST_NAME STREQUAL CLR_CMAKE_TARGET_ARCH OR NOT ARCH_TARGET_NAME STREQUAL CLR_CMAKE_TARGET_ARCH)
    message(FATAL_ERROR "Native host and target architecture names must match the selected Wasm target.")
endif()
if(NOT ARCH_SOURCES_DIR STREQUAL "wasm")
    message(FATAL_ERROR "Both Wasm targets must use the shared wasm source directory.")
endif()

add_library(wasm_target_tests STATIC target.c target.cpp)
if(CLR_CMAKE_TARGET_ARCH STREQUAL "wasm64")
    target_compile_definitions(wasm_target_tests PRIVATE EXPECTED_POINTER_SIZE=8)
else()
    target_compile_definitions(wasm_target_tests PRIVATE EXPECTED_POINTER_SIZE=4)
endif()
