#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Build the runtime-pinned ICU with the stock Emscripten Memory64 compiler.

The existing ICU transport contains only wasm32 libraries. This recipe preserves
dotnet/icu's browser feature/data filters, adds -m64 to every target compilation
and link, and keeps generated system libraries outside the frozen SDK cache.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import uuid
import xml.etree.ElementTree as ET


ICU_COMMIT = "c6131fd7b7cebcef44c17f381b2fe325cb331964"
ICU_VERSION = "72.1.0.4"
ICU_ARCHIVE_SHA256 = "32e27462769c6c63e5afb719695aa57dec82185c0960da823028264dd6c7b4a8"
ICU_URL = f"https://codeload.github.com/dotnet/icu/tar.gz/{ICU_COMMIT}"
ARCHIVES = ("libicui18n.a", "libicuuc.a", "libicudata.a")
DATA = ("icudt.dat", "icudt_CJK.dat", "icudt_EFIGS.dat", "icudt_no_CJK.dat")
# configureplatform.cmake uses -nostdlib and names these seven inputs explicitly.
# Emscripten's -lmalloc alias selects the libdlmalloc archive for this recipe.
SYSROOT_TARGETS = ("libstubs", "libc", "libdlmalloc", "libclang_rt.builtins-wasmsjlj",
                   "libc++-wasmexcept", "libc++abi-wasmexcept", "libunwind-wasmexcept")
RECIPE_VERSION = 1


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command, *, cwd=None, env=None, log=None):
    command = list(map(str, command))
    print("Running: " + " ".join(command), flush=True)
    if log is None:
        return subprocess.run(command, cwd=cwd, env=env, check=True,
                              text=True, capture_output=True).stdout
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run(command, cwd=cwd, env=env, check=True,
                       stdout=stream, stderr=subprocess.STDOUT)


def check_runtime_pin(repo):
    root = ET.parse(repo / "eng/Version.Details.xml").getroot()
    dependency = root.find("./ProductDependencies/Dependency[@Name='Microsoft.NETCore.Runtime.ICU.Transport']")
    if dependency is None or dependency.findtext("Sha") != ICU_COMMIT:
        raise RuntimeError("The runtime ICU source pin changed. Update this recipe and its archive SHA256 together.")


def fetch_source(cache):
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / f"dotnet-icu-{ICU_COMMIT}.tar.gz"
    if not archive.exists():
        temporary = archive.with_suffix(".download-" + uuid.uuid4().hex)
        try:
            with urllib.request.urlopen(ICU_URL) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            if sha256(temporary) != ICU_ARCHIVE_SHA256:
                raise RuntimeError("Downloaded ICU archive has an unexpected SHA256.")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if sha256(archive) != ICU_ARCHIVE_SHA256:
        raise RuntimeError(f"ICU archive checksum mismatch: {archive}")
    return archive


def extract_source(archive, destination):
    destination.mkdir(parents=True)
    with tarfile.open(archive) as source:
        # The pinned archive contains regular files and directories only. Reject
        # links/devices as well as escaping paths, including on Python versions
        # that predate tarfile's extraction filters.
        members = source.getmembers()
        for member in members:
            resolved = (destination / member.name).resolve()
            if (not (member.isfile() or member.isdir()) or
                    destination.resolve() not in resolved.parents):
                raise RuntimeError(f"Unexpected ICU archive member: {member.name}")
        source.extractall(destination, members=members)
    root = destination / f"icu-{ICU_COMMIT}"
    version = re.search(r"^ICU_version\s*=\s*(\S+)\s*$", (root / "version.txt").read_text(), re.MULTILINE)
    if version is None or version.group(1) != ICU_VERSION:
        raise RuntimeError("The pinned ICU source has an unexpected version.")
    return root


def prepare_recipe(source):
    recipe = source / "eng/icu.mk"
    text = recipe.read_text()
    if text.count("$(MAKE) -j8") != 2 or text.count("ifeq ($(TARGET_ARCHITECTURE),wasm)") != 1:
        raise RuntimeError("The pinned ICU make recipe no longer matches the Memory64 adaptation.")
    text = text.replace("TARGET_ARCHITECTURE ?= wasm\n", "TARGET_ARCHITECTURE ?= wasm\nICU_BUILD_JOBS ?= 2\n")
    text = text.replace("$(MAKE) -j8", "$(MAKE) -j$(ICU_BUILD_JOBS)")
    text = text.replace("ifeq ($(TARGET_ARCHITECTURE),wasm)",
                        "ifneq ($(filter wasm wasm64,$(TARGET_ARCHITECTURE)),)")
    recipe.write_text(text)
    browser = source / "eng/icu.browser.mk"
    text = browser.read_text()
    if text.count('CFLAGS="-Oz ') != 1 or text.count('CXXFLAGS="-Oz ') != 1:
        raise RuntimeError("The pinned ICU browser flags no longer match the Memory64 adaptation.")
    text = text.replace('CFLAGS="-Oz ', 'CFLAGS="-Oz $(MEMORY64_FLAG) ')
    text = text.replace('CXXFLAGS="-Oz ', 'CXXFLAGS="-Oz $(MEMORY64_FLAG) ')
    text += '\nifeq ($(TARGET_ARCHITECTURE),wasm64)\nMEMORY64_FLAG = -m64\nCONFIGURE_COMPILER_FLAGS += LDFLAGS="-m64"\nendif\n'
    browser.write_text(text)
    # This is part of dotnet/icu's normal eng/icu.proj build contract.
    shutil.copy2(source / "icu-filters/curr-root.txt", source / "icu/icu4c/source/data/curr/root.txt")


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
            raise RuntimeError(f"Unset {name}: the Memory64 ICU recipe uses fixed target compiler flags.")
    environment = os.environ.copy()
    environment.update({"EMSDK_PATH": str(sdk), "EM_CACHE": str(cache), "EM_FROZEN_CACHE": "",
                        "EMCC_CORES": str(jobs), "DOTNET_EMSCRIPTEN_LLVM_ROOT": str(sdk / "bin") + "/",
                        "DOTNET_EMSCRIPTEN_NODE_JS": str(node), "DOTNET_EMSCRIPTEN_BINARYEN_ROOT": str(sdk) + "/"})
    return environment, node


def verify_archives(directory, sdk, names):
    result = {}
    for name in names:
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty Memory64 dependency archive: {path}")
        members = run([sdk_tool(sdk, "llvm-ar"), "t", path]).splitlines()
        headers = run([sdk_tool(sdk, "llvm-readobj"), "--file-header", path])
        formats = re.findall(r"^Format:\s*(\S+)\s*$", headers, re.MULTILINE)
        architectures = re.findall(r"^Arch:\s*(\S+)\s*$", headers, re.MULTILINE)
        # llvm-readobj silently ignores bitcode and unknown archive members.
        # Compare against the real inventory so a partial inspection cannot
        # certify a mixed archive containing unrecognized files.
        if (not formats or len(formats) != len(architectures) or len(formats) != len(members) or
                set(formats) != {"WASM"} or set(architectures) != {"wasm64"}):
            found = ", ".join(sorted(set(architectures))) or "no recognized objects"
            raise RuntimeError(f"{path}: expected only wasm64 archive members, found {found} (recognized {len(formats)} of {len(members)} members). Rebuild this dependency with -m64; browser-wasm transport libraries are 32-bit.")
        result[name] = {"sha256": sha256(path), "bytes": path.stat().st_size, "wasm64_members": len(architectures)}
    return result


def verify_icu(directory, sdk):
    for relative in [*("lib/" + name for name in ARCHIVES + DATA), "include/unicode/uversion.h"]:
        path = directory / relative
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Incomplete Memory64 ICU dependency: {path}")
    result = verify_archives(directory / "lib", sdk, ARCHIVES)
    for name in DATA:
        path = directory / "lib" / name
        result[name] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    return result


def prepare_sysroot(options):
    sdk = options.emsdk.resolve()
    environment, _ = sdk_environment(sdk, options.emscripten_cache, options.jobs)
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


def link_probe(directory, sdk, environment, node, work):
    source = work / "icu-memory64-probe.cpp"
    source.write_text('''#include <assert.h>
#include <stdio.h>
#include <unicode/uversion.h>
#include <unicode/ustring.h>
#include <unicode/ucol.h>
static_assert(sizeof(void*) == 8 && sizeof(size_t) == 8, "ICU probe must target Memory64");
int main() {
    UVersionInfo version;
    u_getVersion(version);
    const UChar text[] = { 0x4e2d, 'x', 0 };
    UCollator* (*volatile collator)(const char*, UErrorCode*) = ucol_open;
    assert(version[0] == 72 && version[1] == 1);
    assert(u_strlen(text) == 2 && collator != nullptr);
    printf("ICU %d.%d Memory64 archive probe PASS; pointer=%zu\\n", version[0], version[1], sizeof(void*));
    return 0;
}
''')
    output = work / "icu-memory64-probe.js"
    command = [sdk / "emscripten/em++", source, "-m64", "-O0", "-fno-exceptions", "-DU_DISABLE_RENAMING=1",
               "-sWASM_BIGINT=1", "-sASSERTIONS=1", "-sENVIRONMENT=node", "-I" + str(directory / "include"),
               *[directory / "lib" / name for name in ARCHIVES], "-o", output]
    run(command, env=environment, log=work / "link-probe-build.log")
    result = run([node, output], env=environment)
    (work / "link-probe-run.log").write_text(result)
    if "Memory64 archive probe PASS; pointer=8" not in result:
        raise RuntimeError("The ICU Memory64 archive execution probe did not report success.")
    print(result, end="", flush=True)
    return {"status": "PASS", "command": list(map(str, command)), "stdout": result}


def build_locked(options):
    repo = options.repo_root.resolve()
    check_runtime_pin(repo)
    sdk = options.emsdk.resolve()
    environment, node = sdk_environment(sdk, options.emscripten_cache, options.jobs)
    identity = {"icu_commit": ICU_COMMIT, "icu_version": ICU_VERSION, "source_archive_sha256": ICU_ARCHIVE_SHA256,
                "recipe_version": RECIPE_VERSION, "pointer_size": 8,
                "emcc_version": run([sdk / "emscripten/emcc", "--version"], env=environment),
                "clang_sha256": sha256(sdk_tool(sdk, "clang")),
                "wasm_ld_sha256": sha256(sdk_tool(sdk, "wasm-ld"))}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output = options.output.resolve()
    marker = output / "icu-memory64.json"
    if marker.is_file():
        previous = json.loads(marker.read_text())
        if previous.get("fingerprint") == fingerprint:
            if verify_icu(output, sdk) != previous.get("files"):
                raise RuntimeError(f"Previously built ICU files changed: {output}. Select a fresh output directory.")
            print(f"Using verified Memory64 ICU: {output}")
            return
        raise RuntimeError(f"ICU/toolchain fingerprint changed; select a fresh output directory: {output}")
    if output.exists():
        raise RuntimeError(f"Output exists without a Memory64 ICU build manifest; use verify for external dependencies or select a fresh output directory: {output}")
    archive = fetch_source(options.source_cache)
    work = options.work_dir.resolve() / fingerprint[:16]
    work.mkdir(parents=True, exist_ok=True)
    source_parent = work / "source"
    if source_parent.exists():
        shutil.rmtree(source_parent)
    source = extract_source(archive, source_parent)
    prepare_recipe(source)
    environment["CC"] = shutil.which(options.host_cc) or options.host_cc
    environment["CXX"] = shutil.which(options.host_cxx) or options.host_cxx
    stage = work / "browser-wasm64/native"
    command = ["make", "-f", "icu.mk", "all", "TARGET_OS=browser", "TARGET_ARCHITECTURE=wasm64",
               "WASM_ENABLE_THREADS=false", "ICU_TRACING=false",
               f"HOST_OBJDIR={work / 'host'}", f"TARGET_OBJDIR={work / 'target'}", f"TARGET_BINDIR={stage}",
               f"ICU_BUILD_JOBS={options.jobs}", f"EMSDK_PATH={sdk}", "SHELL=/bin/bash"]
    run(command, cwd=source / "eng", env=environment, log=work / "build.log")
    # icu.mk leaves data files at TARGET_BINDIR's root. The transport packaging
    # contract places them in native/lib, and normally uses the pinned prebuilts
    # rather than regenerating the globalization data as a side effect of a
    # native library build (eng/nuget/Microsoft.NETCore.Runtime.ICU.Transport.pkgproj).
    for name in DATA:
        shutil.copy2(source / "eng/prebuilts/wasm" / name, stage / "lib" / name)
        (stage / name).unlink(missing_ok=True)
    libraries = verify_icu(stage, sdk)
    probe = link_probe(stage, sdk, environment, node, work)
    manifest = {**identity, "fingerprint": fingerprint, "source_url": ICU_URL, "target": "browser-wasm64",
                "target_flags": ["-m64", "-Oz", "-fno-exceptions"], "data_filter": "icudt_wasm",
                "published_data_source": "pinned dotnet/icu eng/prebuilts/wasm; official transport default",
                "currency_filter": "icu-filters/curr-root.txt", "emsdk_path": str(sdk),
                "emscripten_cache": str(options.emscripten_cache.resolve()), "jobs": options.jobs,
                "host_cc": environment["CC"], "host_cxx": environment["CXX"],
                "command": list(map(str, command)), "work_dir": str(work), "files": libraries, "link_probe": probe}
    (stage / "icu-memory64.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / (output.name + ".tmp-" + uuid.uuid4().hex)
    try:
        shutil.copytree(stage, temporary)
        temporary.replace(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    print(f"Built and verified Memory64 ICU: {output}", flush=True)


def build(options):
    # Multiple native projects can request the same dependency in one MSBuild
    # graph. Serialize publication and source/build-directory preparation.
    import fcntl
    output = options.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    work = options.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    # Different output paths can still share the same fingerprint/work tree.
    # Guard both locations before deleting sources or invoking make.
    with (output.parent / (output.name + ".build.lock")).open("a+") as lock, \
            (work / ".build.lock").open("a+") as work_lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fcntl.flock(work_lock, fcntl.LOCK_EX)
        return build_locked(options)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("build", "verify", "fetch", "prepare-sysroot"))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--emsdk", type=Path, default=Path(os.environ["EMSDK_PATH"]) if os.environ.get("EMSDK_PATH") else None)
    parser.add_argument("--output", "--icu-dir", dest="output", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--source-cache", type=Path)
    parser.add_argument("--emscripten-cache", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--host-cc", default="cc")
    parser.add_argument("--host-cxx", default="c++")
    options = parser.parse_args()
    if options.jobs < 1:
        parser.error("--jobs must be positive")
    repo = options.repo_root.resolve()
    options.source_cache = options.source_cache or repo / ".dotnet/wasm-tools/icu/source"
    options.output = options.output or repo / "artifacts/bin/icu/browser-wasm64/Release/native"
    options.work_dir = options.work_dir or repo / "artifacts/obj/icu/browser-wasm64"
    options.emscripten_cache = options.emscripten_cache or Path(os.environ.get("EM_CACHE", str(repo / ".dotnet/wasm-tools/emscripten-memory64")))
    try:
        if options.operation == "fetch":
            check_runtime_pin(repo)
            print(fetch_source(options.source_cache))
            return
        if options.emsdk is None:
            parser.error("--emsdk or EMSDK_PATH is required")
        if options.operation == "verify":
            print(json.dumps({"target": "browser-wasm64", "files": verify_icu(options.output.resolve(), options.emsdk.resolve())}, indent=2))
        elif options.operation == "prepare-sysroot":
            prepare_sysroot(options)
        else:
            if not sys.platform.startswith("linux"):
                raise RuntimeError("The source-build recipe currently supports Linux build hosts.")
            build(options)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Memory64 ICU dependency error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
