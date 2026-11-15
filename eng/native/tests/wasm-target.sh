#!/usr/bin/env bash
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

# Lightweight native target selection tests. Requires the repo-pinned Emscripten
# SDK (EMSDK_PATH or the shared Wasm tool cache), CMake and Ninja. These compile
# static objects, not a runtime or a managed application.
set -euo pipefail

scriptroot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
reporoot="$(cd "$scriptroot/../../.." && pwd -P)"
testroot="${1:-$reporoot/artifacts/obj/native-wasm-target-tests}"
mkdir -p "$testroot"
testroot="$(cd "$testroot" && pwd -P)"

for arch in wasm wasm64; do
    "$reporoot/eng/native/gen-buildsys.sh" "$scriptroot/wasm-target" "$testroot/$arch" \
        "$arch" browser default Release ninja \
        -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY "-DCLR_CMAKE_TARGET_ARCH=$arch"
    cmake --build "$testroot/$arch"
done

# A wasm32 compiler must not silently populate a wasm64 output directory.
if "$reporoot/eng/native/gen-buildsys.sh" "$scriptroot/wasm-target" "$testroot/mismatched-architecture" \
    wasm browser default Release ninja -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY \
    -DCLR_CMAKE_TARGET_ARCH=wasm64 > "$testroot/mismatched-architecture.log" 2>&1; then
    echo "ERROR: a wasm32 compiler was accepted for a wasm64 target."
    exit 1
fi
if ! grep -Fq "WebAssembly compiler target 'wasm' does not match 'wasm64'" "$testroot/mismatched-architecture.log"; then
    cat "$testroot/mismatched-architecture.log"
    exit 1
fi

echo "PASS: native wasm/wasm64 target selection, widths and mismatch rejection."
