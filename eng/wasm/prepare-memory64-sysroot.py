#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Prepare and verify Emscripten system libraries for a browser wasm64 native link."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


# configureplatform.cmake uses -nostdlib and names these seven inputs explicitly.
# Emscripten's -lmalloc alias selects the libdlmalloc archive for this recipe.
SYSROOT_TARGETS = ("libstubs", "libc", "libdlmalloc", "libclang_rt.builtins-wasmsjlj",
                   "libc++-wasmexcept", "libc++abi-wasmexcept", "libunwind-wasmexcept")


def sdk_tool(sdk, name):
    tool = sdk / "bin" / name
    if not tool.is_file():
        raise RuntimeError(f"Required Emscripten tool is missing: {tool}")
    return tool


def sdk_environment(sdk, cache, jobs):
    node = sdk / "node/bin/node"
    if not node.is_file():
        node = sdk / "bin/node"
    if not node.is_file():
        raise RuntimeError(f"The selected Emscripten SDK has no Node executable: {sdk}")
    if cache.resolve() == (sdk / "emscripten/cache").resolve():
        raise RuntimeError("Use a separate Memory64 system-library cache; the frozen SDK cache must not be overwritten.")
    for name in ("EMCC_CFLAGS", "EMMAKEN_CFLAGS", "EM_COMPILER_WRAPPER"):
        if os.environ.get(name):
            raise RuntimeError(f"Unset {name}: the Memory64 sysroot recipe uses fixed target compiler flags.")
    environment = os.environ.copy()
    environment.update({"EMSDK_PATH": str(sdk), "EM_CACHE": str(cache), "EM_FROZEN_CACHE": "",
                        "EMCC_CORES": str(jobs), "DOTNET_EMSCRIPTEN_LLVM_ROOT": str(sdk / "bin") + "/",
                        "DOTNET_EMSCRIPTEN_NODE_JS": str(node), "DOTNET_EMSCRIPTEN_BINARYEN_ROOT": str(sdk) + "/"})
    return environment


def verify_archives(directory, sdk, names):
    result = {}
    for name in names:
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty Memory64 dependency archive: {path}")
        members = subprocess.check_output([sdk_tool(sdk, "llvm-ar"), "t", path], text=True).splitlines()
        headers = subprocess.check_output([sdk_tool(sdk, "llvm-readobj"), "--file-header", path], text=True)
        formats = re.findall(r"^Format:\s*(\S+)\s*$", headers, re.MULTILINE)
        architectures = re.findall(r"^Arch:\s*(\S+)\s*$", headers, re.MULTILINE)
        # llvm-readobj silently ignores bitcode and unknown archive members.
        # Compare against the real inventory so a partial inspection cannot
        # certify a mixed archive containing unrecognized files.
        if (not formats or len(formats) != len(architectures) or len(formats) != len(members) or
                set(formats) != {"WASM"} or set(architectures) != {"wasm64"}):
            found = ", ".join(sorted(set(architectures))) or "no recognized objects"
            raise RuntimeError(f"{path}: expected only wasm64 archive members, found {found} (recognized {len(formats)} of {len(members)} members). Rebuild this dependency with -m64; wasm32 objects cannot be linked into the wasm64 runtime.")
        result[name] = {"bytes": path.stat().st_size, "wasm64_members": len(architectures)}
    return result


def prepare_sysroot(options):
    sdk = options.emsdk.resolve()
    environment = sdk_environment(sdk, options.emscripten_cache, options.jobs)
    builder = sdk / "emscripten/embuilder.py"
    if not builder.is_file():
        raise RuntimeError(f"The selected Emscripten SDK has no official system-library builder: {builder}")
    command = [sys.executable, str(builder), "--wasm64", "build", *SYSROOT_TARGETS]
    print("Running: " + " ".join(command), flush=True)
    # embuilder owns its cache lock and skips completed targets. The explicit
    # -nostdlib link cannot request these missing variants through emcc itself.
    subprocess.run(command, env=environment, check=True)
    libraries = verify_archives(options.emscripten_cache / "sysroot/lib/wasm64-emscripten",
                                sdk, [name + ".a" for name in SYSROOT_TARGETS])
    print(json.dumps({"target": "wasm64-emscripten", "files": libraries}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emsdk", type=Path, required=True, help="Provisioned .NET Emscripten SDK directory")
    parser.add_argument("--emscripten-cache", type=Path, required=True, help="Separate writable Memory64 cache")
    parser.add_argument("--jobs", type=int, default=2)
    options = parser.parse_args()
    if options.jobs < 1:
        parser.error("--jobs must be positive")
    options.emscripten_cache = options.emscripten_cache.resolve()
    try:
        prepare_sysroot(options)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
