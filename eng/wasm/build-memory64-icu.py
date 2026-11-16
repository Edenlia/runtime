#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Build the runtime-pinned ICU with the stock Emscripten Memory64 compiler.

The existing ICU transport contains only wasm32 libraries. This recipe preserves
dotnet/icu's browser feature/data filters, adds -m64 to every target compilation
and link, and keeps generated system libraries outside the frozen SDK cache.
"""

import argparse
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
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
PTHREAD_SYSROOT_TARGETS = ("libstubs", "libc-mt", "libdlmalloc-mt", "libclang_rt.builtins-wasmsjlj-mt",
                           "libc++-mt-wasmexcept", "libc++abi-mt-wasmexcept", "libunwind-mt-wasmexcept")
PTHREAD_SYSROOT_OBJECTS = ("crtbegin-mt",)
RECIPE_VERSION = 9
WINDOWS_HOST_ICU_FIX = {
    "upstream_commit": "564c92d666354a8ed0f99cba0f239eba790bd148",
    "upstream_url": "https://github.com/unicode-org/icu/commit/564c92d666354a8ed0f99cba0f239eba790bd148",
    "subject": "ICU-22721 Delete obsolete __STRICT_ANSI__ workaround for MinGW.",
}
WINDOWS_HOST_ICU_HUNK = """#if U_PLATFORM == U_PF_MINGW && defined __STRICT_ANSI__
/* tzset isn't defined in strict ANSI on MinGW. */
#undef __STRICT_ANSI__
#endif

"""
WINDOWS_GUEST_ICU_FIX = {
    "config_sub_upstream_tree": "bf835bad36a09828051dd8cc6f58bb62bac93fde",
    "config_sub_upstream_url": "https://github.com/unicode-org/icu/blob/bf835bad36a09828051dd8cc6f58bb62bac93fde/icu4c/source/config.sub",
    "config_sub_upstream_sha256": "11c54f55c3ac99e5d2c3dc2bb0bcccbf69f8223cc68f6b2438daa806cf0d16d8",
    "emscripten_fragment_source": "https://github.com/microsoft/vcpkg/blob/8f363bdc11359ede4bc51e5eb32a2617538049c8/ports/icu/portfile.cmake",
    "emscripten_fragment_source_sha256": "24381125afa64a02776bfce2aa2624c9fdc295d8454b0c44b3979623785a88e8",
    "emscripten_fragment": "mh-linux",
    "derived_currency_encoding": "UTF-8 with BOM; original resource definitions unchanged",
}
WINDOWS_CONFIG_SUB_REPLACEMENTS = (
    ("| wasm32 \\\n", "| wasm32 | wasm64 \\\n"),
    ("| wasm32-* \\\n", "| wasm32-* | wasm64-* \\\n"),
    ("| -aos* | -aros* | -cloudabi* | -sortix* \\\n", "| -aos* | -aros* | -emscripten* | -cloudabi* | -sortix* \\\n"),
)
WINDOWS_FRAGMENT_REPLACEMENT = (
    'case "${host}" in\n*-*-solaris*)',
    'case "${host}" in\n*-*-emscripten*) icu_cv_host_frag=mh-linux ;;\n*-*-solaris*)',
)


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


def prepare_windows_host_source(source):
    # ICU-22721 removes a MinGW-only workaround that makes modern libstdc++
    # headers assume GNU language extensions while compiling in C++11 mode.
    # Apply the exact accepted upstream deletion in our owned extraction. Its
    # platform guard is false for the WebAssembly guest; target settings stay
    # identical to the pinned browser recipe.
    path = source / "icu/icu4c/source/common/putil.cpp"
    text = path.read_bytes().decode("utf-8")
    if text.count(WINDOWS_HOST_ICU_HUNK) != 1:
        raise RuntimeError("The pinned ICU source no longer matches the ICU-22721 MinGW adaptation.")
    before = sha256(path)
    path.write_bytes(text.replace(WINDOWS_HOST_ICU_HUNK, "").encode("utf-8"))
    return {**WINDOWS_HOST_ICU_FIX, "file": "icu/icu4c/source/common/putil.cpp",
            "removed_hunk_sha256": hashlib.sha256(WINDOWS_HOST_ICU_HUNK.encode()).hexdigest(),
            "before_sha256": before, "after_sha256": sha256(path)}


def prepare_windows_guest_source(source):
    adaptations = []
    # Backport only the accepted machine/OS recognition, rather than replacing
    # the entire build-aux script or mislabelling the guest as wasm32.
    root = source / "icu/icu4c/source"
    config_sub = root / "config.sub"
    if sha256(config_sub) != "38930c2485d8935ee7f82bfc61cbf60b9e33a7b96b11fbb26be7adffa2a8f874":
        raise RuntimeError("The pinned ICU config.sub no longer matches the guest tuple adaptation.")
    changes = [("config.sub", WINDOWS_CONFIG_SUB_REPLACEMENTS),
               ("configure", (WINDOWS_FRAGMENT_REPLACEMENT,)),
               ("acinclude.m4", (WINDOWS_FRAGMENT_REPLACEMENT,))]
    for name, replacements in changes:
        path = root / name
        before = sha256(path)
        text = path.read_bytes().decode("utf-8")
        for old, new in replacements:
            if text.count(old) != 1:
                raise RuntimeError(f"The pinned ICU {name} no longer matches the Emscripten adaptation.")
            text = text.replace(old, new)
        path.write_bytes(text.encode("utf-8"))
        adaptations.append({**WINDOWS_GUEST_ICU_FIX, "file": "icu/icu4c/source/" + name,
            "patch_sha256": hashlib.sha256(json.dumps(replacements, separators=(",", ":")).encode()).hexdigest(),
            "before_sha256": before, "after_sha256": sha256(path)})
    browser = source / "eng/icu.browser.mk"
    with browser.open("a", encoding="utf-8", newline="\n") as output:
        output.write("\nCONFIGURE_ARGS += --build=$(ICU_BUILD_TRIPLE) --host=$(ICU_GUEST_TRIPLE)\n")
    # Native Windows genrb otherwise silently uses the active ANSI code page.
    # Mark only the owned derived copy; do not transcode or alter the filter.
    currency_filter = source / "icu-filters/curr-root.txt"
    currency = root / "data/curr/root.txt"
    original = currency_filter.read_bytes()
    original.decode("utf-8")
    if currency.read_bytes() != original or original.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError("The derived ICU currency resource no longer matches the pinned UTF-8 filter.")
    before = sha256(currency)
    currency.write_bytes(b"\xef\xbb\xbf" + original)
    adaptations.append({"file": "icu/icu4c/source/data/curr/root.txt", "operation": "prepend UTF-8 BOM to derived copy",
        "source_filter": "icu-filters/curr-root.txt", "source_filter_sha256": sha256(currency_filter),
        "before_sha256": before, "after_sha256": sha256(currency)})
    return adaptations


class EmscriptenSdk:
    """Resolve the selected SDK's own configuration, including supported LLVM overrides."""

    def __init__(self, root, cache, jobs):
        self.root = root.resolve()
        self.emscripten = next((path for path in (self.root / "emscripten", self.root / "upstream/emscripten")
                               if (path / "emcc.py").is_file()), None)
        if self.emscripten is None:
            raise RuntimeError(f"No Emscripten Python driver found in SDK: {self.root}")
        if cache.resolve() == (self.emscripten / "cache").resolve():
            raise RuntimeError("Use a separate Memory64 system-library cache; the SDK cache must not be overwritten.")
        for name in ("EMCC_CFLAGS", "EMMAKEN_CFLAGS", "EM_COMPILER_WRAPPER"):
            if os.environ.get(name):
                raise RuntimeError(f"Unset {name}: the Memory64 ICU recipe uses fixed target compiler flags.")
        self.environment = os.environ.copy()
        self.environment.update({"EMSDK_PATH": str(self.root), "EM_CACHE": str(cache.resolve()),
                                 "EM_FROZEN_CACHE": "", "EMCC_CORES": str(jobs)})
        # The Windows em*.exe launchers need this even when the helper itself
        # was invoked with an absolute Python path outside PATH.
        self.environment.setdefault("EMSDK_PYTHON", sys.executable)
        if not self.environment.get("EM_CONFIG"):
            config = next((path for path in (self.root / ".emscripten", self.emscripten / ".emscripten")
                           if path.is_file()), None)
            if config is None:
                raise RuntimeError(f"The selected SDK has no configuration. Activate it locally first: {self.root}")
            self.environment["EM_CONFIG"] = str(config)
        # The runtime-composed SDK uses these variables; the standalone emsdk uses
        # its normal EM_CONFIG/EM_LLVM_ROOT contract instead. Query the result below.
        if self.emscripten.parent == self.root:
            suffix = ".exe" if os.name == "nt" else ""
            self.environment.setdefault("DOTNET_EMSCRIPTEN_LLVM_ROOT", self.environment.get("EM_LLVM_ROOT", str(self.root / "bin")))
            self.environment.setdefault("DOTNET_EMSCRIPTEN_NODE_JS", str(self.root / "node/bin" / ("node" + suffix)))
            self.environment.setdefault("DOTNET_EMSCRIPTEN_BINARYEN_ROOT", str(self.root))
        query = "import json; from tools import config; print(json.dumps({'llvm':config.LLVM_ROOT,'binaryen':config.BINARYEN_ROOT,'node':config.NODE_JS}))"
        self.config = json.loads(run([sys.executable, "-c", query], cwd=self.emscripten, env=self.environment))
        self.llvm = Path(self.config["llvm"]).resolve()
        self.node = list(self.config["node"]) if isinstance(self.config["node"], list) else [self.config["node"]]
        node = Path(self.node[0]) if self.node else None
        # The runtime-composed SDK configures node/bin/node on Windows, where
        # CreateProcess resolves that spelling to node.exe. Validate the same
        # executable rather than rejecting its supported extensionless spelling.
        if os.name == "nt" and node is not None and not node.is_file() and not node.suffix:
            node = Path(str(node) + ".exe")
        if node is None or not node.is_file():
            raise RuntimeError(f"The selected SDK has no configured Node executable: {self.node}")
        self.node[0] = str(node.resolve())
        self.config["resolved_node"] = self.node
        self.config["node_executable_sha256"] = sha256(node)
        requested_llvm = self.environment.get("EM_LLVM_ROOT")
        if requested_llvm and Path(requested_llvm).resolve() != self.llvm:
            raise RuntimeError(f"The selected SDK did not honor EM_LLVM_ROOT: requested {requested_llvm}, resolved {self.llvm}")

    def tool(self, name):
        tool = self.llvm / (name + (".exe" if os.name == "nt" else ""))
        if not tool.is_file():
            raise RuntimeError(f"Required configured Emscripten tool is missing: {tool}")
        return tool

    def driver(self, name):
        script = self.emscripten / (name + ".py")
        if script.is_file():
            return [sys.executable, str(script)]
        driver = self.emscripten / name
        if not driver.is_file():
            raise RuntimeError(f"Required Emscripten driver is missing: {driver}")
        return [str(driver)]


class BuildHost:
    def __init__(self, options, environment):
        self.environment = environment.copy()
        self.msys = options.msys2_root.resolve() if options.msys2_root else None
        self.short_paths = options.msys2_short_paths
        self.path_mappings = {}
        if self.short_paths and os.name != "nt":
            raise RuntimeError("--msys2-short-paths applies only to the Windows/MSYS2 build host.")
        if os.name == "nt":
            if self.msys is None:
                raise RuntimeError("Windows source builds require --msys2-root with GNU make and a UCRT64 host compiler.")
            for relative in ("usr/bin/bash.exe", "usr/bin/cygpath.exe", "usr/bin/make.exe", "ucrt64/bin/gcc.exe", "ucrt64/bin/g++.exe"):
                if not (self.msys / relative).is_file():
                    raise RuntimeError(f"Required MSYS2 host tool is missing: {self.msys / relative}")
            self.environment.update({"MSYSTEM": "UCRT64", "CHERE_INVOKING": "yes", "MSYS2_PATH_TYPE": "minimal"})
            self.environment["PATH"] = os.pathsep.join((str(self.msys / "ucrt64/bin"), str(self.msys / "usr/bin"), self.environment.get("PATH", "")))
            self.environment["CC"] = options.host_cc if options.host_cc != "cc" else "/ucrt64/bin/gcc"
            self.environment["CXX"] = options.host_cxx if options.host_cxx != "c++" else "/ucrt64/bin/g++"
            # These values are consumed by a POSIX configure/make process, even
            # though emconfigure itself uses native Python. Keep executable and
            # script path conversion enabled, and preserve only these options.
            exclusions = self.environment.get("MSYS2_ARG_CONV_EXCL", "")
            self.environment["MSYS2_ARG_CONV_EXCL"] = ";".join(filter(None, (exclusions, "--prefix=", "--with-cross-build=")))
            if self.short_paths:
                # system_libs batches relative source paths. SDK and cache must
                # share the same ancestor spelling, otherwise aliases inflate
                # those paths past Windows's native process argument limit.
                self.environment["EM_CACHE"] = str(self.native_path(Path(environment["EM_CACHE"])))
        else:
            self.environment["CC"] = shutil.which(options.host_cc) or options.host_cc
            self.environment["CXX"] = shutil.which(options.host_cxx) or options.host_cxx

    def path(self, path):
        if os.name != "nt":
            return str(path)
        return run([self.msys / "usr/bin/cygpath.exe", "-u", self.native_path(path)], env=self.environment).strip()

    def native_path(self, path):
        canonical = Path(path).resolve()
        converted = canonical
        if self.short_paths:
            # Legacy native ICU tools cannot open deep Win32 paths. Reuse only
            # existing NTFS aliases; never create a drive mapping or redirect the
            # output tree. A future directory can use its existing parent's alias.
            existing = canonical
            missing = []
            while not existing.exists():
                missing.insert(0, existing.name)
                existing = existing.parent
            short = run([self.msys / "usr/bin/cygpath.exe", "-d", existing], env=self.environment).strip()
            if not os.path.samefile(existing, short):
                raise RuntimeError(f"MSYS2 short path is not the same physical input: {existing} -> {short}")
            if len(str(existing)) >= 240 and len(short) >= len(str(existing)):
                raise RuntimeError(f"No useful existing NTFS short alias for {existing}; choose a shorter owned work directory.")
            converted = Path(short).joinpath(*missing)
            self.path_mappings[str(canonical)] = {"existing_canonical": str(existing),
                                                  "existing_short": short, "samefile": True,
                                                  "invocation_path": str(converted)}
        return converted

    def make(self, command, cwd, log):
        if os.name == "nt":
            command = [self.msys / "usr/bin/bash.exe", "-lc", shlex.join(list(map(str, command)))]
        return run(command, cwd=cwd, env=self.environment, log=log)

    def configure_wrapper(self, sdk, repo):
        return shlex.join([*(self.path(Path(arg)) for arg in sdk.driver("emconfigure")),
                           "/usr/bin/bash", self.path(repo / "eng/wasm/emscripten-msys2-configure.sh")])


@contextmanager
def file_lock(path):
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as error:
                    if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def verify_archives(directory, sdk, names):
    result = {}
    for name in names:
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty Memory64 dependency archive: {path}")
        members = run([sdk.tool("llvm-ar"), "t", path], env=sdk.environment).splitlines()
        headers = run([sdk.tool("llvm-readobj"), "--file-header", path], env=sdk.environment)
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


def verify_objects(directory, sdk, names):
    result = {}
    for name in names:
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing or empty Memory64 startup object: {path}")
        with path.open("rb") as stream:
            if stream.read(8) != b"\0asm\x01\0\0\0":
                raise RuntimeError(f"{path}: expected a raw wasm64 startup object, not an archive or other format.")
        headers = run([sdk.tool("llvm-readobj"), "--file-header", path], env=sdk.environment)
        formats = re.findall(r"^Format:\s*(\S+)\s*$", headers, re.MULTILINE)
        architectures = re.findall(r"^Arch:\s*(\S+)\s*$", headers, re.MULTILINE)
        if formats != ["WASM"] or architectures != ["wasm64"]:
            raise RuntimeError(f"{path}: expected one raw wasm64 startup object, found {architectures}.")
        result[name] = {"sha256": sha256(path), "bytes": path.stat().st_size,
                        "type": "wasm64 object", "wasm64_objects": 1}
    return result


def verify_icu_profile(directory, native_pthreads):
    marker = directory / "icu-memory64.json"
    if not marker.is_file():
        if native_pthreads:
            raise RuntimeError("Native pthread ICU dependencies require an icu-memory64.json manifest declaring native_pthreads=true.")
        return
    manifest = json.loads(marker.read_text())
    profile = manifest.get("native_pthreads", False)
    if profile is not native_pthreads:
        raise RuntimeError(f"ICU native pthread profile mismatch: requested {native_pthreads}, manifest declares {profile}: {directory}")
    return manifest


def prepare_sysroot(options):
    sdk = EmscriptenSdk(options.emsdk, options.emscripten_cache, options.jobs)
    targets = PTHREAD_SYSROOT_TARGETS if options.native_pthreads else SYSROOT_TARGETS
    objects = PTHREAD_SYSROOT_OBJECTS if options.native_pthreads else ()
    command = [*sdk.driver("embuilder"), "--wasm64", "build", *targets, *objects]
    print("Running: " + " ".join(command), flush=True)
    # embuilder owns its cache lock and skips completed targets. The explicit
    # -nostdlib link cannot request these missing variants through emcc itself.
    subprocess.run(command, env=sdk.environment, check=True)
    library_dir = options.emscripten_cache / "sysroot/lib/wasm64-emscripten"
    libraries = verify_archives(library_dir, sdk, [name + ".a" for name in targets])
    libraries.update(verify_objects(library_dir, sdk, [name + ".o" for name in objects]))
    print(json.dumps({"target": "wasm64-emscripten", "native_pthreads": options.native_pthreads,
                      "files": libraries}, indent=2), flush=True)


def link_probe(directory, sdk, work, native_pthreads):
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
    command = [*sdk.driver("em++"), source, "-m64", "-O0", "-fno-exceptions", "-DU_DISABLE_RENAMING=1",
               *(["-pthread"] if native_pthreads else []),
               "-sWASM_BIGINT=1", "-sASSERTIONS=1", "-sENVIRONMENT=node", "-I" + str(directory / "include"),
               *[directory / "lib" / name for name in ARCHIVES], "-o", output]
    run(command, env=sdk.environment, log=work / "link-probe-build.log")
    result = run([*sdk.node, output], env=sdk.environment)
    (work / "link-probe-run.log").write_text(result)
    if "Memory64 archive probe PASS; pointer=8" not in result:
        raise RuntimeError("The ICU Memory64 archive execution probe did not report success.")
    print(result, end="", flush=True)
    return {"status": "PASS", "command": list(map(str, command)), "stdout": result}


def build_locked(options):
    repo = options.repo_root.resolve()
    check_runtime_pin(repo)
    sdk = EmscriptenSdk(options.emsdk, options.emscripten_cache, options.jobs)
    host = BuildHost(options, sdk.environment)
    host_cc = host.environment["CC"]
    host_cxx = host.environment["CXX"]
    if os.name == "nt":
        host_cc = str(host.msys / "ucrt64/bin/gcc.exe") if host_cc == "/ucrt64/bin/gcc" else host_cc
        host_cxx = str(host.msys / "ucrt64/bin/g++.exe") if host_cxx == "/ucrt64/bin/g++" else host_cxx
    build_triple = run([host_cc, "-dumpmachine"], env=host.environment).strip() if os.name == "nt" else None
    guest_triple = run([*sdk.driver("emcc"), "-m64", "-dumpmachine"], env=sdk.environment).strip() if os.name == "nt" else None
    if os.name == "nt" and guest_triple != "wasm64-unknown-emscripten":
        raise RuntimeError(f"The selected compiler does not report the expected wasm64 guest tuple: {guest_triple}")
    identity = {"icu_commit": ICU_COMMIT, "icu_version": ICU_VERSION, "source_archive_sha256": ICU_ARCHIVE_SHA256,
                "recipe_version": RECIPE_VERSION, "pointer_size": 8,
                "native_pthreads": options.native_pthreads,
                "emcc_version": run([*sdk.driver("emcc"), "--version"], env=sdk.environment),
                "clang_sha256": sha256(sdk.tool("clang")),
                "wasm_ld_sha256": sha256(sdk.tool("wasm-ld")),
                "sdk_configuration": sdk.config,
                "host_os": sys.platform,
                "python_version": sys.version, "python_executable": sys.executable,
                "build_triple": build_triple, "guest_triple": guest_triple,
                "windows_guest_icu_adaptations": WINDOWS_GUEST_ICU_FIX if os.name == "nt" else None,
                "windows_configure_bridge_sha256": sha256(repo / "eng/wasm/emscripten-msys2-configure.sh") if os.name == "nt" else None,
                "msys2_short_paths": host.short_paths,
                "windows_host_icu_fix": {**WINDOWS_HOST_ICU_FIX,
                    "removed_hunk_sha256": hashlib.sha256(WINDOWS_HOST_ICU_HUNK.encode()).hexdigest()} if os.name == "nt" else None,
                "host_cc_version": run([host_cc, "--version"], env=host.environment),
                "host_cxx_version": run([host_cxx, "--version"], env=host.environment)}
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
        if work.resolve() not in source_parent.resolve().parents:
            raise RuntimeError(f"Source cleanup escaped its owned work directory: {source_parent}")
        shutil.rmtree(source_parent)
    source = extract_source(archive, source_parent)
    prepare_recipe(source)
    source_adaptations = [prepare_windows_host_source(source), *prepare_windows_guest_source(source)] if os.name == "nt" else []
    stage = work / "browser-wasm64/native"
    command = ["make", "-f", "icu.mk", "all", "TARGET_OS=browser", "TARGET_ARCHITECTURE=wasm64",
               "WASM_ENABLE_THREADS=" + str(options.native_pthreads).lower(), "ICU_TRACING=false",
               f"HOST_OBJDIR={host.path(work / 'host')}", f"TARGET_OBJDIR={host.path(work / 'target')}", f"TARGET_BINDIR={host.path(stage)}",
               f"ICU_BUILD_JOBS={options.jobs}", f"EMSDK_PATH={host.path(sdk.root)}", "SHELL=/bin/bash"]
    if host.short_paths:
        # GNU make canonicalizes CURDIR even when launched through an alias.
        # Override only the pinned recipe's source-root spelling, not its rules.
        command += [f"TOP={host.path(source)}/"]
    if os.name == "nt":
        # The SDK environment is already resolved above. Runtime-composed Windows
        # SDKs do not ship emsdk_env.sh, and native Python cannot execute configure
        # directly; use the real MSYS2 shell through the normal emconfigure driver.
        command += ["ENV_INIT_SCRIPT=", "ENV_CONFIGURE_WRAPPER=" + host.configure_wrapper(sdk, repo),
                    f"ICU_BUILD_TRIPLE={build_triple}", f"ICU_GUEST_TRIPLE={guest_triple}"]
    (work / "build-identity.json").write_text(json.dumps({**identity, "fingerprint": fingerprint,
        "source_adaptations": source_adaptations, "command": list(map(str, command)),
        "path_mappings": host.path_mappings, "host_em_cache": host.environment["EM_CACHE"]}, indent=2) + "\n")
    host.make(command, cwd=source / "eng", log=work / "build.log")
    # icu.mk leaves data files at TARGET_BINDIR's root. The transport packaging
    # contract places them in native/lib, and normally uses the pinned prebuilts
    # rather than regenerating the globalization data as a side effect of a
    # native library build (eng/nuget/Microsoft.NETCore.Runtime.ICU.Transport.pkgproj).
    for name in DATA:
        shutil.copy2(source / "eng/prebuilts/wasm" / name, stage / "lib" / name)
        (stage / name).unlink(missing_ok=True)
    libraries = verify_icu(stage, sdk)
    probe = link_probe(stage, sdk, work, options.native_pthreads)
    manifest = {**identity, "fingerprint": fingerprint, "source_url": ICU_URL, "target": "browser-wasm64",
                "target_flags": ["-m64", "-Oz", "-fno-exceptions", *(["-pthread"] if options.native_pthreads else [])],
                "data_filter": "icudt_wasm",
                "published_data_source": "pinned dotnet/icu eng/prebuilts/wasm; official transport default",
                "currency_filter": "icu-filters/curr-root.txt", "emsdk_path": str(sdk.root),
                "emscripten_cache": str(options.emscripten_cache.resolve()), "jobs": options.jobs,
                "host_cc": host.environment["CC"], "host_cxx": host.environment["CXX"],
                "command": list(map(str, command)), "work_dir": str(work), "files": libraries, "link_probe": probe,
                "source_adaptations": source_adaptations}
    manifest["path_mappings"] = host.path_mappings
    manifest["host_em_cache"] = host.environment["EM_CACHE"]
    (stage / "icu-memory64.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / (output.name + ".tmp-" + uuid.uuid4().hex)
    try:
        shutil.copytree(stage, temporary)
        temporary.replace(output)
    finally:
        if temporary.exists():
            if output.parent.resolve() not in temporary.resolve().parents:
                raise RuntimeError(f"Temporary cleanup escaped its output parent: {temporary}")
            shutil.rmtree(temporary)
    print(f"Built and verified Memory64 ICU: {output}", flush=True)


def build(options):
    # Multiple native projects can request the same dependency in one MSBuild
    # graph. Serialize publication and source/build-directory preparation.
    output = options.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    work = options.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    # Different output paths can still share the same fingerprint/work tree.
    # Guard both locations before deleting sources or invoking make.
    with file_lock(output.parent / (output.name + ".build.lock")), file_lock(work / ".build.lock"):
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
    parser.add_argument("--native-pthreads", action="store_true",
                        help="Build native pthread-compatible objects; this does not enable CLR managed multithreading.")
    parser.add_argument("--host-cc", default="cc")
    parser.add_argument("--host-cxx", default="c++")
    parser.add_argument("--msys2-root", type=Path, default=Path(os.environ["MSYS2_ROOT"]) if os.environ.get("MSYS2_ROOT") else None)
    parser.add_argument("--msys2-short-paths", action="store_true",
                        help="Use verified existing NTFS aliases for legacy ICU host tools in a deep Windows work directory.")
    options = parser.parse_args()
    if options.jobs < 1:
        parser.error("--jobs must be positive")
    repo = options.repo_root.resolve()
    options.source_cache = options.source_cache or repo / ".dotnet/wasm-tools/icu/source"
    variant = "browser-wasm64-native-pthreads" if options.native_pthreads else "browser-wasm64"
    cache_variant = "emscripten-memory64-native-pthreads" if options.native_pthreads else "emscripten-memory64"
    options.output = options.output or repo / "artifacts/bin/icu" / variant / "Release/native"
    options.work_dir = options.work_dir or repo / "artifacts/obj/icu" / variant
    options.emscripten_cache = options.emscripten_cache or Path(os.environ.get("EM_CACHE", str(repo / ".dotnet/wasm-tools" / cache_variant)))
    try:
        if options.operation == "fetch":
            check_runtime_pin(repo)
            print(fetch_source(options.source_cache))
            return
        if options.emsdk is None:
            parser.error("--emsdk or EMSDK_PATH is required")
        if options.operation == "verify":
            manifest = verify_icu_profile(options.output.resolve(), options.native_pthreads)
            sdk = EmscriptenSdk(options.emsdk, options.emscripten_cache, options.jobs)
            files = verify_icu(options.output.resolve(), sdk)
            if manifest is not None and manifest.get("files") != files:
                raise RuntimeError(f"ICU files do not match their build manifest: {options.output}")
            print(json.dumps({"target": "browser-wasm64", "native_pthreads": options.native_pthreads,
                              "files": files}, indent=2))
        elif options.operation == "prepare-sysroot":
            prepare_sysroot(options)
        else:
            if not (sys.platform.startswith("linux") or os.name == "nt"):
                raise RuntimeError("The source-build recipe supports Linux and Windows/MSYS2 build hosts.")
            build(options)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Memory64 ICU dependency error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
