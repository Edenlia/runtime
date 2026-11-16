# ICU for browser-wasm64

The existing `Microsoft.NETCore.Runtime.ICU.Transport` package contains wasm32
native archives. A Memory64 runtime needs separately compiled archives. This
Linux-hosted recipe builds the ICU source commit selected by
`eng/Version.Details.xml`, verifies every archive member's architecture, and
links and executes an ICU probe with the selected Emscripten SDK before
publishing an output directory.

Requirements are Python 3.10 or later (required by the pinned Emscripten), GNU
make, a host C/C++ compiler, and the
repository-pinned Emscripten SDK with its Node and LLVM tools. Provision that SDK
through the `provision.emsdk` subset first, or pass `-p:EMSDK_PATH=/path/to/sdk`.
The first build downloads a fixed dotnet/icu commit from GitHub and verifies its
SHA256 before extraction. An existing verified download can be used offline.

From the repository root:

```sh
./dotnet.sh msbuild eng/wasm/BuildMemory64Icu.proj
```

The in-tree wasm64 CoreCLR and native-library build targets prepare this
dependency automatically after acquiring Emscripten. An explicit
`Memory64IcuDir` on those build targets selects an external dependency: only
ICU verification runs, and that directory is never overwritten. Use this property
for overrides; `CMakeArgs` containing `CMAKE_ICU_DIR` is rejected for wasm64 so
it cannot bypass the architecture check.

Before ICU preparation, the build prepares the seven system libraries named by
CoreCLR's `-nostdlib` link. It calls the selected SDK's official
`embuilder.py --wasm64 build` with `libstubs`, `libc`, `libdlmalloc`,
`libclang_rt.builtins-wasmsjlj`, `libc++-wasmexcept`, `libc++abi-wasmexcept`, and
`libunwind-wasmexcept`. Emscripten maps `-lmalloc` to `libdlmalloc`, and its native
Wasm EH settings select the `-wasmsjlj` builtins variant. The `-wasmexcept`
libraries use `-fwasm-exceptions -sWASM_LEGACY_EXCEPTIONS=0`. The preparation
checks every member of all seven resulting archives for the wasm64 architecture;
builder errors, missing archives, and wrong or unrecognized member types fail
before native compilation. These calls use the same separate Memory64 cache and
job limit as ICU, while wasm32 builds keep their existing SDK/cache path.

The system-library preparation can also be run directly:

```sh
python3 eng/wasm/build-memory64-icu.py prepare-sysroot \
  --emsdk /path/to/sdk --emscripten-cache /path/to/memory64/cache --jobs 2
```

Retain that SDK and prepared cache when later consuming the native relink kit.

The defaults place the output in
`artifacts/bin/icu/browser-wasm64/Release/native`, intermediate files in
`artifacts/obj/icu/browser-wasm64`, and downloads/system libraries under the
shared Wasm tool cache. ICU is built with its browser feature and data filters,
`-m64`, single-threaded ICU without tracing, and two make jobs.
`Memory64IcuBuildJobs` adjusts that concurrency. Additional `EMCC_CFLAGS`,
`EMMAKEN_CFLAGS`, or `EM_COMPILER_WRAPPER` overrides are rejected. The
four published `.dat` files come from the same source commit's
`eng/prebuilts/wasm` directory, matching the official transport packaging default;
they are independent of the native pointer width.

Important properties are `Memory64IcuDir`, `Memory64IcuWorkDir`,
`Memory64IcuSourceCacheDir`, `Memory64EmscriptenCacheDir`, `EMSDK_PATH`, and
`PythonExecutable`. Native runtime compilation must use the same SDK and set
`EM_CACHE` to `Memory64EmscriptenCacheDir` with `EM_FROZEN_CACHE` empty. The
recipe refuses the SDK's stock frozen cache, so generated Memory64 system
libraries stay separate from the wasm32 lane.

`icu-memory64.json` records the source pin/checksum, compiler/linker identity,
archive hashes and object counts, and the successful link/execution probe.
Repeated build requests recheck published archive/data hashes and archive member
widths. They reuse an output only if its source/toolchain fingerprint matches.
A changed fingerprint or modified output requires selecting a fresh output
directory. Do not remove that check to reuse an archive from another toolchain.

To check an externally built dependency without building ICU:

```sh
./dotnet.sh msbuild eng/wasm/BuildMemory64Icu.proj \
  -p:Memory64IcuOperation=verify -p:Memory64IcuDir=/path/to/native
```

This checks the complete package layout and requires every member of all three
native archives to report `Arch: wasm64`, with the member inventory checked
independently using `llvm-ar`. It rejects wasm32, native, mixed, empty, bitcode,
and unrecognized-member archives. External verification establishes the archive layout and
width; the source provenance and execution probe in a recipe-generated
manifest apply only to that source build.

For a checksum-verified source download without a compiler, use
`-p:Memory64IcuOperation=fetch`. The Python entry point also exposes `build`,
`verify`, and `fetch` directly; run
`python3 eng/wasm/build-memory64-icu.py --help` for their path options.

The focused verifier tests compile tiny real object files with the selected
LLVM tools; they do not build or execute ICU:

```sh
EMSDK_PATH=/path/to/sdk python3 eng/wasm/tests/test_memory64_icu.py -v
```

After a successful default ICU build, the MSBuild integration checks exercise
the actual runtime/native-library projects, including cache environment,
dependency reuse, and rejection of the existing wasm32 transport. These checks
do not invoke the native build targets. They require the pinned SDK, Emscripten,
the existing default ICU manifest, and restored ICU transport package:

```sh
DOTNET_HOST_PATH=/path/to/dotnet EMSDK_PATH=/path/to/sdk \
  NUGET_PACKAGES=/path/to/restored/packages \
  MEMORY64_EMSCRIPTEN_TEST_CACHE=/path/to/memory64/system/cache \
  python3 eng/wasm/tests/test_memory64_icu_integration.py -v
```

The focused system-library tests use real LLVM object files and an instrumented
builder fixture to check cold-cache call ordering, cache isolation, wrong-width
rejection, and failure propagation through the actual MSBuild preparation
targets. They require the pinned SDK/LLVM tools and an already built default
ICU directory; they do not compile the real SDK libraries:

```sh
DOTNET_HOST_PATH=/path/to/dotnet EMSDK_PATH=/path/to/sdk \
  python3 eng/wasm/tests/test_memory64_sysroot.py -v
```

An ICU probe success establishes this dependency's Memory64 compilation and
linking. It does not establish a working CoreCLR wasm64 runtime, managed/native
transitions, globalization data loading, exception handling, or GC.
