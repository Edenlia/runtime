# Native pthread compatibility

`test/eden-web-native-pthreads` adds the explicit, default-off
`WasmNativePthreads` native profile. It is separate from Windows build-host
support and the intrinsic wasm64 pointer fixes.

The need is measured: the original single-thread ICU archives execute in native
Memory64, but UE's established final shared-memory link rejects
`collationtailoring.ao` for missing atomics/bulk-memory features. UE's final link
continues to use `-m64 -sMEMORY64=2 -pthread -sPROXY_TO_PTHREAD -sWASMFS=1`.

## Profile contract

The initial profile is limited to browser/CoreCLR/wasm64. It compiles native
CoreCLR, host and library objects with the real Emscripten `-pthread` ABI. Native
host cross-components retain their host compiler and flags. Explicit CMake 0/1
inputs prevent a cached true value surviving a switch back to the default.

`WasmEnableThreads` and `FeatureMultithreading` remain disabled. The wasm64
managed-thread validation still rejects them. This profile permits one managed
runtime thread to run on a native pthread worker; it does not enable CLR managed
thread creation.

Browser builds with the compiler's `__EMSCRIPTEN_PTHREADS__` macro use the SDK's
`pthread_setschedparam` implementation. The Wasm PAL fallback remains for
non-pthread browser builds and WASI. This avoids defining the same API in both
PAL and the native-pthread libc without enabling managed thread creation.

The ICU helper's `--native-pthreads` option uses the pinned browser recipe's
existing `WASM_ENABLE_THREADS=true`, which adds native `-pthread` flags. The
default remains false. Source pins, resource definitions, data filters,
optimization and exception choices are unchanged. The native mode participates
in the build fingerprint and manifest, with separate default work/output/cache
paths. A supplied native-pthread ICU dependency requires a manifest declaring
that mode; mismatched modes or file hashes fail before compilation.

The normal system-library preparation selects the SDK's native-MT variants for
libc, malloc, compiler runtime, C++ ABI and native Wasm exceptions, together with
the SDK's `crtbegin-mt.o` startup object. The selected Emscripten driver resolves
ordinary `-l` aliases to the selected variants. The three already-qualified
native Wasm EH names are selected explicitly as MT archives. CoreCLR retains
`-nostdlib`, so the native profile also selects `-l:crtbegin-mt.o` for pthread TLS
initialization. The raw startup object is verified separately from archive
members, with its type and hash recorded. Default non-pthread flags are unchanged.
The repository's 6.0.2 SDK pin is unchanged; binary validation in this session
uses the explicitly selected UE 6.0.10 SDK and separately recorded fixed Clang.

BrowserHost-Static installs an immutable native-profile manifest. The live-build
inventory ships it under `native/src/wasm-props.json`. The SDK compares the
consumer's native mode to the precompiled archive mode before either prebuilt
reuse or relinking; relinking cannot retarget incompatible native archives.
The profile and manifest also participate in the response-file/link dependency
contract. The exported corerun kit records the native mode and retains the
corresponding compile/link flags.

## Build outputs

Use a dedicated worktree and a fresh toolchain/profile cache. On Windows,
`build-runtime.cmd` owns its canonical `artifacts` root; changing only MSBuild's
object root would separate generated version inputs from their native consumers.
Use the existing `BuildSubdirectory=native-pthreads` partition and matching
`CoreclrRuntimeBinDir`/`CoreCLRArtifactsPath` values for CoreLib, cDAC and native
runtime products. Evaluate the actual project properties before building.

The existing wasm64 default subset does not include `host.native`. Include that
normal lane explicitly when BrowserHost-Static and its shipped profile metadata
are required. No default subset or UE target setting is changed by this profile.

## Executed boundary and remaining gates

Focused checks compile the actual native CMake route for default wasm32,
default wasm64 and native-pthread wasm64, with compiler assertions for pointer
width, the Emscripten pthread/atomics macros and absence of the managed-thread
define. An actual x64/MSVC host cross-component build retains its native flags.
Imported MSBuild rules and the dependency CLI pass default/profile and negative
mode/target/managed-thread checks. Contract checks build the real task source,
execute producer/install and inventory/copy paths, inspect compile/link/wasm-opt
response files, and reject both archive-profile mismatch directions.

The complete recipe 9 native-pthread ICU dependency has built all pinned targets,
verified its 441 archive members and passed real native Memory64 pthread
execution. Its data remains the unchanged pinned transport data. The first
normal native graph then exposed the Windows dependency-path quoting boundary,
which swallowed following CMake arguments; no valid native profile CLR
configuration or compilation is claimed from that attempt.

After the Windows argv/cache routing repairs, the next normal graph configured
the intended profile and compiled production CLR sources. Its corerun link then
found a duplicate `pthread_setschedparam` in the PAL fallback and SDK libc.
Focused checks compile the actual fallback source hunk for 32/64-bit ST and MT
compiler modes, verify symbol ownership, reproduce the old duplicate with the
actual SDK libc archive member, and link/execute the repaired native-pthread
case. The normal native graph and matched managed guest still require success.

Frozen-cache link-only probes demonstrate why the native profile needs both
explicit MT EH names and the SDK pthread startup object: qualified ST names are
not retargeted by ordinary alias mapping, and `-nostdlib` omits TLS startup.
The corrected native-MT selection links successfully with all completed SDK
inputs unchanged. This does not claim a CLR guest or executed exception path.

Complete native runtime products and a matching managed guest have not yet
been built at this checkpoint. The broader existing SDK wasm64 publish
route still has browser-RID, helper-target and archive-name gaps. The contract
checks do not claim that route, native response-file execution, a NuGet runtime
pack or a CLR guest has passed. Actual native Memory64 and UE lowered64 pthread
product/guest execution remain separate acceptance lanes.
