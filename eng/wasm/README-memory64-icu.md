# Standalone Memory64 dependencies

These entry points build ICU and the Emscripten system libraries needed by a
Memory64 native consumer. They run independently of runtime builds, target JITs,
portable helper generation, managed framework products, and the root build's
target-architecture selection. The MSBuild project evaluates host tool paths;
the dependency compiler receives `-m64` or the official `--wasm64` option.

Requirements are a Linux host, Python 3.10 or later, GNU make, a host C/C++
compiler, and the repository-pinned Emscripten SDK with Node and LLVM tools.
The optional MSBuild entry point uses the checkout-pinned .NET SDK. Provision
Emscripten using the existing `provision.emsdk` subset, or pass an existing SDK
directory explicitly. These files do not install or modify the SDK.

## ICU

The existing ICU transport's browser native archives are wasm32. The recipe
builds the ICU source commit selected by `eng/Version.Details.xml` into a separate
Memory64 output. It downloads the fixed dotnet/icu archive, verifies its SHA256,
preserves the browser feature/data filters, and compiles with `-m64`. A changed
runtime source pin requires updating the recipe and checksum together.

From the repository root:

```sh
./dotnet.sh msbuild eng/wasm/BuildMemory64Icu.proj -p:EMSDK_PATH=/path/to/sdk
```

Or use Python without MSBuild:

```sh
python3 eng/wasm/build-memory64-icu.py build --emsdk /path/to/sdk \
  --emscripten-cache /path/to/memory64/cache
```

Defaults place ICU output in
`artifacts/bin/icu/browser-wasm64/Release/native`, work files in
`artifacts/obj/icu/browser-wasm64`, and downloads/system libraries under the
shared Wasm tool cache. Important MSBuild properties are `Memory64IcuDir`,
`Memory64IcuWorkDir`, `Memory64IcuSourceCacheDir`,
`Memory64EmscriptenCacheDir`, `Memory64IcuBuildJobs` (default two), and
`PythonExecutable`. The standalone operation remains explicit: `build`,
`verify`, or `fetch`. An explicit `Memory64IcuDir` sets the output or input path
for that selected operation; it does not implicitly change the operation.

The four published `.dat` files come from the pinned commit's
`eng/prebuilts/wasm`, matching the transport packaging default. These data files
are independent of pointer width. The native libraries are compiled from source
with the same browser feature filters, without ICU threads or tracing.
Additional `EMCC_CFLAGS`, `EMMAKEN_CFLAGS`, and `EM_COMPILER_WRAPPER` overrides
are rejected.

Before publication, every native archive member must report `Arch: wasm64`,
and the `llvm-ar` inventory must agree with the inspected member count. The
recipe then links and runs an ICU API probe with pointer size eight.
`icu-memory64.json` records the source pin/checksum, compiler/linker identity,
archive/data hashes and member counts, and the probe result. Existing outputs
are reused only when the fingerprint and checked files match; changed or
unrecognized outputs require selecting a fresh output directory.

To verify an external directory without building it:

```sh
./dotnet.sh msbuild eng/wasm/BuildMemory64Icu.proj \
  -p:EMSDK_PATH=/path/to/sdk -p:Memory64IcuOperation=verify \
  -p:Memory64IcuDir=/path/to/native
```

Verification checks the complete ICU layout and all native member widths. It
rejects wasm32, native, mixed, empty, bitcode, and unrecognized-member archives.
This external check establishes layout and architecture; source-build provenance
and the execution probe belong to the recipe-generated manifest. For a
checksum-verified source download without a compiler, select
`-p:Memory64IcuOperation=fetch`. Run the Python entry point with `--help` for
the corresponding CLI path options.

## Emscripten system libraries

The official SDK builder prepares the seven explicit inputs of the intended
`-nostdlib` native link:

```sh
python3 eng/wasm/build-memory64-icu.py prepare-sysroot \
  --emsdk /path/to/sdk --emscripten-cache /path/to/memory64/cache --jobs 2
```

It invokes `embuilder.py --wasm64 build` for `libstubs`, `libc`, `libdlmalloc`,
`libclang_rt.builtins-wasmsjlj`, `libc++-wasmexcept`, `libc++abi-wasmexcept`, and
`libunwind-wasmexcept`, then verifies every member of all seven archives.
Emscripten maps `-lmalloc` to `libdlmalloc`, and native Wasm EH selects the
`-wasmsjlj` builtins variant. The `-wasmexcept` libraries use
`-fwasm-exceptions -sWASM_LEGACY_EXCEPTIONS=0`.

All generated system libraries use a separate Memory64 cache. The recipe
refuses the selected SDK's stock cache and passes `EM_FROZEN_CACHE` empty to
the builder. A later consumer must use the same SDK and prepared `EM_CACHE`,
again with `EM_FROZEN_CACHE` empty. Existing complete targets are reused and
rechecked. Builder failures and wrong or unrecognized archive members fail the
operation.

These entry points do not use CMake's ASM compiler override or an external
replacement `llvm-mc`. They use the selected SDK's normal C/C++ compilation and
official system-library builder. A separate LLVM assembler-checker fix is not
part of this dependency change.

The ICU API probe establishes the selected dependency's compilation,
linking and execution properties. Runtime build-graph integration, native runtime
products, managed/native transitions, exception handling and GC require their
own validation.
