#!/usr/bin/env bash
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

# Toolchain ABI probe only: this does not execute CoreCLR or managed code.
# Usage: wasm-abi.sh [output-directory] [Node options...]
# Select a Node executable with WASM_ABI_NODE. Sysroot libraries are built in an
# isolated cache (WASM_ABI_CACHE_DIR or <output-directory>/emscripten-cache).
set -euo pipefail

scriptroot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
reporoot="$(cd "$scriptroot/../../.." && pwd -P)"
testroot="${1:-$reporoot/artifacts/obj/native-wasm-abi-tests}"
if [[ $# -gt 0 ]]; then shift; fi
node_args=("$@")
mkdir -p "$testroot"
testroot="$(cd "$testroot" && pwd -P)"

# Capture the requested Node before emsdk_env.sh changes PATH.
node_command="$(command -v "${WASM_ABI_NODE:-node}")"
if [[ -z "${EMSDK_PATH:-}" ]]; then
    source "$reporoot/eng/wasm/wasm-tool-cache.sh"
    EMSDK_PATH="$(wasm_tool_cache_dir emscripten "$reporoot/src/mono/browser/emscripten-version.txt" "$reporoot")"
fi
export EMSDK_PATH
source "$EMSDK_PATH/emsdk_env.sh"

# The official SDK can have a frozen wasm32-only cache. Keep that cache intact
# while allowing this probe to generate the selected toolchain's wasm64 libraries.
export EM_CACHE="${WASM_ABI_CACHE_DIR:-$testroot/emscripten-cache}"
export EM_FROZEN_CACHE=''
mkdir -p "$EM_CACHE"
EM_CACHE="$(cd "$EM_CACHE" && pwd -P)"
if [[ -d "$EMSDK_PATH/emscripten/cache" ]]; then
    stock_cache="$(cd "$EMSDK_PATH/emscripten/cache" && pwd -P)"
    case "$EM_CACHE" in
        "$stock_cache"|"$stock_cache"/*)
            echo "ERROR: WASM_ABI_CACHE_DIR must be separate from the SDK's stock cache."
            exit 1
            ;;
    esac
fi

echo "Emscripten: $(command -v emcc)"
emcc --version
echo "Node: $node_command"
"$node_command" --version
printf 'Node options:'
if [[ ${#node_args[@]} -gt 0 ]]; then
    printf ' %q' "${node_args[@]}"
else
    printf ' (none)'
fi
printf '\n'
echo "Generated sysroot cache: $EM_CACHE"

for arch in wasm wasm64; do
    arch_flags=()
    pointer_size=4
    if [[ "$arch" == "wasm64" ]]; then
        arch_flags=(-m64)
        pointer_size=8
    fi
    emcc "$scriptroot/wasm-target/abi.c" "${arch_flags[@]}" -O0 -UNDEBUG \
        "-DEXPECTED_POINTER_SIZE=$pointer_size" -sENVIRONMENT=node -sEXIT_RUNTIME=1 \
        -o "$testroot/$arch.cjs"
    "$EMSDK_PATH/bin/wasm-dis" "$testroot/$arch.wasm" -o "$testroot/$arch.wat"
    "$node_command" "${node_args[@]}" "$testroot/$arch.cjs"
done

echo "PASS: wasm32/wasm64 native toolchain scalar, aggregate, indirect call and callback ABI."
