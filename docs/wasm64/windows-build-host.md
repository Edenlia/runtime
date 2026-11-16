# Windows build-host prerequisite

This work belongs to `test/eden-web-build-host`, based on
`ef532fc54ebe7c3b3f2e9314a4ac436b07c044c5`. It is separate from the intrinsic
`wasm64/eden-main` changes. It adds Windows routing and a local MSYS2 host for the
existing pinned ICU recipe. It does not change the runtime's Emscripten 6.0.2 pin.

## Tool and output selection

The Windows entry points accept browser/CoreCLR `wasm64` and preserve the browser
`wasm` default. `gen-buildsys.cmd` selects the 64-bit pointer ABI before CMake's
compiler/size checks. Its wasm32 feature cache remains wasm32-only. A cross
component retains its native host architecture and compiler.

The dependency helper reads the selected SDK's actual Python configuration,
including its Node command and supported `EM_LLVM_ROOT` override. It supports both
the runtime-composed `emscripten` layout and standalone emsdk's
`upstream/emscripten` layout. Windows source builds require a task-local MSYS2
UCRT64 environment with GNU make, bash, cygpath, GCC and G++. The script does not
install these tools or change global environment, PATH, registry or drive mappings.

Use an activated SDK, its native Python, an explicit fresh Emscripten system-library
cache and an unpublished ICU output directory. An alternate SDK/compiler requires
its own cache and output; the repository version label is not a fingerprint for
an externally selected toolchain. The ICU build identity records the actual
Emscripten version/configuration, Clang/linker hashes, host compiler versions,
source pin and recipe version. The configured Node argument vector is retained;
Windows's extensionless `node` spelling resolves to the same-path `node.exe`.
Its resolved command and binary hash are recorded. Reusing an output with a
different identity fails.

For example, after assigning absolute paths for the local tools and owned outputs:

```powershell
$env:EMSDK_PATH = $sdkRoot
$env:EM_CONFIG = "$sdkRoot/.emscripten"
$env:EMSDK_PYTHON = $sdkPython
$env:EM_LLVM_ROOT = $fixedLlvmBin

& $sdkPython eng/wasm/build-memory64-icu.py build `
    --emsdk $sdkRoot --msys2-root $msys2Root `
    --source-cache "$dependencyRoot/source-cache" `
    --work-dir "$dependencyRoot/work" --output "$dependencyRoot/output/native" `
    --emscripten-cache $freshSystemLibraryCache --jobs 2
```

The corresponding MSBuild inputs are `Memory64IcuMsys2Root`,
`Memory64IcuSourceCacheDir`, `Memory64IcuWorkDir`, `Memory64IcuDir`,
`Memory64EmscriptenCacheDir` and `Memory64IcuBuildJobs`. Native Python is selected
after SDK acquisition: explicit `PythonExecutable`, then `EMSDK_PYTHON`, then the
runtime SDK's bundled Python, then `python`. Quoted Windows directory arguments
use forward slashes so a trailing backslash cannot consume the closing quote.

The verified ICU directory also uses forward-slash spelling at the Windows
`NativeCMakeArg` boundary. A quoted trailing backslash otherwise absorbs the
following native options, including CMake's `-B` and `-S`, into `CMAKE_ICU_DIR`.
This changes only the same physical directory's invocation spelling; verification,
source selection and compiler/linker settings are unchanged. Linux paths are not
rewritten.

The normal native MSBuild graph prepares ICU before `BuildRuntime` as well as
`BuildNativeCommon`. Inspect the imported `BeforeTargets` hooks when determining
dependencies, rather than only `runtime.proj`'s explicit dependency property.

## Pinned source adaptations

The base remains dotnet/icu `c6131fd7b7cebcef44c17f381b2fe325cb331964`, version
72.1.0.4, verified archive SHA256
`32e27462769c6c63e5afb719695aa57dec82185c0960da823028264dd6c7b4a8`.
The existing Memory64 adaptation and pinned browser feature/data filters remain.
In particular, `WASM_ENABLE_THREADS=false` is unchanged.

On Windows, the owned extraction also adopts the accepted upstream
[ICU-22721 fix](https://github.com/unicode-org/icu/commit/564c92d666354a8ed0f99cba0f239eba790bd148),
authored by `roubert` and merged in [ICU PR 3003](https://github.com/unicode-org/icu/pull/3003).
It removes the obsolete MinGW `__STRICT_ANSI__` undef that breaks modern
libstdc++ headers in ICU's ordinary C++11 mode. The helper requires exactly one
matching hunk, records its upstream SHA and removed-hunk hash in the build identity,
and records the input/output file hashes. This is an explicitly adapted pinned
source, not an unmodified ICU 72.1 build. No numeric-literal extension or changed
language-standard flag is added. The removed platform guard was false for the
WebAssembly guest.

The owned Windows extraction also backports only wasm64 CPU and Emscripten OS
recognition from the accepted [ICU config.sub snapshot](https://github.com/unicode-org/icu/blob/bf835bad36a09828051dd8cc6f58bb62bac93fde/icu4c/source/config.sub).
The build tuple comes from the native compiler, and the guest tuple from
`emcc -m64 -dumpmachine`; the latter must be `wasm64-unknown-emscripten`.
Both `configure` and `acinclude.m4` explicitly map Emscripten to the unchanged
pinned `mh-linux` fragment, following [Microsoft's ICU port](https://github.com/microsoft/vcpkg/blob/8f363bdc11359ede4bc51e5eb32a2617538049c8/ports/icu/portfile.cmake).
This preserves the existing Linux guest recipe and archive names, while keeping
the native MinGW host separate. It does not use a wasm32 label or the unsupported
`mh-unknown` error stub. Strict hunk checks and source/patch hashes cover these
adaptations.

Only the child configure's `--prefix=` and `--with-cross-build=` argument values
are excluded from MSYS2's native argument conversion. They remain POSIX paths
for ICU's generated makefiles and colon-separated tool PATH. Executable/script
conversion stays enabled, and no global environment is changed.

After stock `emconfigure` selects its tools, the Windows configure bridge changes
only pure tool-path environment values to the same executable's forward-slash
spelling. This prevents the unchanged Linux make fragment's second shell
evaluation from consuming backslashes. Each conversion requires physical file
identity. The existing `LDSHARED` ` -shared` suffix is preserved exactly; an
unrecognized command shape fails. Compiler/linker flags, SDK files and generated
makefiles are unchanged.

Native Windows `genrb` can silently decode the pinned UTF-8 currency filter with
the active ANSI code page. The helper prepends a UTF-8 BOM to the bytes of the
owned derived `data/curr/root.txt` only. It does not transcode, normalize line
endings, edit `icu-filters/curr-root.txt`, or change resource definitions. Actual
`genrb`/`derb` tests show that this produces the same correct resource bytes as
explicit UTF-8 decoding; the original default decoding loses currency symbols.
The manifest records the original filter and derived before/after hashes. The
published data files still come from the unchanged pinned prebuilts.

## Deep Windows paths

Legacy native ICU host tools can reject existing files when their recipe spelling
exceeds Win32 path limits. Moving only object directories does not address long
source paths: GNU make canonicalizes `CURDIR`.

For a deep owned tree on a volume with existing NTFS 8.3 aliases, explicitly add
`--msys2-short-paths`, or set `Memory64IcuMsys2ShortPaths=true` in MSBuild. The
default is false. This option verifies the physical identity of each existing
canonical/short ancestor with `samefile`, records the mapping, and passes a short
`TOP` source-root spelling to the original recipe as well as short dependency
paths. It creates no alias, junction or drive mapping. Missing useful aliases
produce an error requiring a shorter owned work directory. It changes path
spelling only; source selection, feature flags, filters and output ownership stay
the same.

## Executed scope and remaining gates

On 2026-11-17, the task-local Windows environment used exact Emscripten 6.0.10,
the normal fixed LLVM build recorded in the operation's toolchain provenance,
MSYS2 UCRT64 GCC 16.2 and GNU make 4.4.1. Binary execution with pinned 6.0.2 and
Linux regression builds have not been performed in this session.

The actual Windows scripts passed wasm32/emcc pointer-size 4, wasm64/emcc
pointer-size 8 and native x64/MSVC cross-component routing probes, each with an
actual compiler `static_assert`. The modified PowerShell entry built
`clr.nativeprereqs+clr.corelib` for browser/wasm64/Release successfully with the
exact SDK from `global.json`, reused through supported `DOTNET_INSTALL_DIR`.
The actual standalone ICU MSBuild fetch passed, including late Python selection
and Windows directory argv handling. Separate-process lock contention and
exception release passed.

The initial ICU host build failed at the obsolete strict-mode undef; the exact
upstream deletion repairs the C++11 compiler reproduction. The next host build
compiled its tools but failed opening a 266-character input spelling. The same
`gendict` binary and physically identical input succeeded through the verified
short alias. Later attempts exposed inconsistent SDK/cache alias spelling in
Emscripten's batched command, then converted drive-letter paths breaking native
tool DLL lookup. Each has a preserved failure and passing focused reproduction.
The true-tuple configure and normal make dry-run confirm 64-bit pointers, the
same Linux fragment/compiler recipe, archive naming and unchanged filter sources.

The actual CoreCLR native configure completed successfully. A runtime component
build used graph-derived native arguments, the normal interpreter selection and
managed cDAC tool; it compiled hundreds of production wasm64 objects, then failed
at the then-unavailable ICU header. Full recipe 7 subsequently completed all
pinned make targets, verified every member of the three real ICU archives, and
linked/executed its native Memory64 probe successfully. It includes the normal
separate-data stub archive and unchanged pinned transport data. That attempt also
normalized `putil.cpp` LF to CRLF. Recipe 8 corrects the hunk application to preserve
every other byte and fixes extensionless Node validation; its whole-source retry
has not yet run. Recipe 7's identity and files remain recorded under recipe 7.
No complete CoreCLR product, managed guest or browser loader success is implied.

The first complete normal Windows native-graph attempt exposed that native argv
boundary: CMake completed its capability checks but wrote an accidental in-source
build because the verified dependency's closing quote was consumed. No native CLR
compilation or valid profile configuration is inferred from that attempt. Its
generated files and logs were archived. Actual MSBuild target-metadata and normal
`gen-buildsys.cmd` probes reproduce the failure and confirm that the Windows path
normalization preserves the following arguments and intended build directory.
Those metadata-only probes do not claim a complete runtime build.

Standalone native Memory64 and UE's lowered final module require separate real
product/guest tests. UE's established final link retains
`-m64 -sMEMORY64=2 -pthread -sPROXY_TO_PTHREAD -sWASMFS=1`. A single managed
runtime thread does not justify changing UE's native threading configuration.
The real recipe 7 ICU archive probe passes native Memory64 execution, but the
same archives fail UE's established shared-memory link: `collationtailoring.ao`
was not compiled with the required atomics/bulk-memory features. The current
single-thread recipe is therefore insufficient for UE's final native target.
Managed multithreading and native pthread object compatibility require separate
selection; enabling `WasmEnableThreads` currently also enables managed
`FeatureMultithreading`, which the wasm64 validation rejects. No UE threading
flag or ICU target feature has been changed to conceal this measured gate.
