# CoreCLR wasm64 target and build bring-up

This work adds a distinct CoreCLR target for native Memory64: target selection,
native and managed layouts, portable call-helper generation, source-built ICU,
and separate build products. The initial build host is Linux x64, the target OS
is `browser`, and the intended managed execution model is single-threaded.
This is a build bring-up checkpoint. It does not establish a deployable wasm64
runtime or a successful complete build with the unmodified pinned toolchain.

## Target identity and boundaries

| Surface | wasm32 | wasm64 |
| --- | --- | --- |
| Build architecture | `wasm` | `wasm64` |
| Internal type-system target | `Wasm32` | `Wasm64` |
| Development RID | `browser-wasm` | `browser-wasm64` |
| Wasm family property | `TargetsWasm` | `TargetsWasm`, `TargetsWasm64` |
| Native target symbols | `TARGET_WASM`, `TARGET_WASM32`, `TARGET_32BIT` | `TARGET_WASM`, `TARGET_WASM64`, `TARGET_64BIT` |
| CoreLib target symbols | `TARGET_WASM`, `TARGET_32BIT` | `TARGET_WASM`, `TARGET_WASM64`, `TARGET_64BIT` |

An explicit `-arch wasm64` survives browser target selection; omitting the
architecture still selects wasm32. RID, architecture and CoreLib platform
overrides must agree. WASI, Mono wasm64, NativeAOT, managed multithreading and
Memory64 lowering compatibility mode are outside this target's initial scope.
The Windows build entry points have not been extended or validated for it.

`browser-wasm64` is an in-tree development identity, not a shipping workload or
RID-graph commitment. No public `System.Runtime.InteropServices.Architecture`
value is added; `Architecture.Wasm` remains the public Wasm family identity.
Full wasm64 JIT/ReadyToRun compilation is explicitly rejected. Ordinary browser
loader/WebCIL execution, SDK/workload publishing, and application execution
remain separate work.

## Width and layout contract

| Quantity | Contract |
| --- | --- |
| Native pointer, `size_t`, `intptr_t`, managed reference/native integer | 8 bytes for wasm64; 4 for wasm32 |
| Function pointer | 8 bytes with the selected wasm64 toolchain |
| Linear-memory address type | i64 for native Memory64 |
| Table address type | i64 for the selected Emscripten wasm64 ABI |
| Interpreter argument slot | 8 bytes on both targets |
| Portable frame alignment | 16 bytes on both targets |
| Transition block | 16 bytes for wasm64; 8 for wasm32, containing two native-sized addresses |

Memory address width and table address width are independent Wasm properties.
The table64 requirement above follows the selected toolchain's ABI; it is not
inferred from the name Memory64. Indirect calls must consume the referenced
table's address type. Portable helper signatures, emitted C/C++ declarations,
saved frame pointers and indirect argument addresses use the guest target's
width, including when the generator runs on an x64 host.

Explicit i32 values remain 32-bit. Context flags, metadata tokens, format-defined
RVA/length/index fields and virtual bytecode offsets retain their semantic widths.
Selecting wasm64 does not mechanically widen those formats or establish support
for values outside their existing bounds.

Native code-heap allocations use pointer alignment without changing Wasm's
minimum function alignment. Desktop 64-bit jump stubs and native personality
jump thunks are excluded from the Wasm paths. Serialized u32 function indices
are explicitly extended before native-address arithmetic; their stored format
remains unchanged.

The managed saved-context constants are in
[`AsmOffsets.cs`](../../../src/coreclr/System.Private.CoreLib/src/System/Runtime/ExceptionServices/AsmOffsets.cs).
For wasm64, `CONTEXT` is 0x28 bytes, with interpreter FP/IP at 0x18/0x20.
`REGDISPLAY` is 0x98 bytes in Release (SP/PC at 0x88/0x90) and 0xa0 in Checked
(SP/PC at 0x90/0x98). These values come from the actual Memory64 C++ layouts.
The native exception-handling translation unit includes the same source and
checks its constants with `static_assert`; both configurations must pass.

The compiler target currently reports `SupportsRelativePointers=false` for both
Wasm widths. This is the implementation's current layout/relocation policy,
not a restriction imposed by the Memory64 specification. Relative pointer
support requires its own producer/consumer implementation and tests.

## GC and allocation defaults

Wasm64 preserves the Wasm segment collector policy. It does not automatically
enable the desktop `USE_REGIONS` default merely because `HOST_64BIT` is set.
The Wasm reservation implementation allocates and clears real linear memory;
large virtual reservations therefore cannot be treated as cheap sparse address
space reservations. Region support needs a separate measured memory policy.

Wasm64 uses natural 8-byte pointer/object alignment. Within the Wasm family,
the extra `FEATURE_64BIT_ALIGNMENT` behavior for selected 32-bit object layouts
remains limited to wasm32, consistently with `TargetDetails.SupportsAlign8`. Card bytes
and flags keep their existing meaning while address arithmetic and reference
stores use native widths. Compilation and layout checks do not validate GC
collection, growth, allocation failure, high-address roots or large live sets.

## Native build and product isolation

Use the checkout-pinned SDK and Emscripten, with dependencies described in
[`linux-requirements.md`](../../workflow/requirements/linux-requirements.md).
Keep each source checkout's product directories separate; sharing the SDK/tool
cache does not authorize substituting CoreLib, helper sources or native archives
from another target or checkout.

The three wasm64 helper source files are checked in beneath
`src/coreclr/vm/wasm/browser/wasm64/`, following the wasm32 convention. Ordinary
native builds consume those tables; they do not require a complete managed
framework build or helper regeneration on every invocation.

The wasm64 root defaults select `provision.emsdk`, `clr.runtime`, `clr.hosts`,
`clr.corelib` and `libs.native`. These are the native build entry points:

```sh
./build.sh -os browser -arch wasm64 -c Release
./build.sh -os browser -arch wasm64 -c Checked
```

They select `-m64` before native compiler layout probes and prepare genuine
Memory64 ICU after SDK acquisition. The table64 assembler limitation described
below still applies: these commands do not establish a successful complete
build with the stock pinned SDK. Explicit unsupported JIT, native CoreLib/R2R
and pack requests must fail rather than be reported as completed.

Native runtime/CoreLib directories include `browser.wasm64.<configuration>`;
native-library paths include `net12.0-browser-<configuration>-wasm64`.
CoreLib IL products stay beneath the runtime directory's `IL/` child.
Compiler-width mismatches, inconsistent CoreLib platform overrides, and wrong
native dependency architectures must fail instead of populating a misleading
target directory. Relink kits record their target architecture. Relinking also
requires the matching SDK and prepared Memory64 sysroot cache; the kit must not
silently fall back to the SDK's stock wasm32 cache.

## Regenerating the checked-in helpers

Maintainers regenerating framework tables need the ordinary host tools and a
complete matching managed framework closure. On Linux x64, build the required
wasm32 products and host compiler through the existing subsets:

```sh
./build.sh -os browser -arch wasm -c Release \
  -subset clr.runtime+clr.hosts+clr.corelib+clr.crossarchtools+clr.tools+host.native+libs \
  /p:PublishReadyToRun=false
```

The `clr.crossarchtools+clr.tools+libs` portion uses normal host compiler build
paths. The other subsets supply its runtime/CoreLib inputs and the
`libBrowserHost.a` required by ordinary wasm32 framework/testhost staging.
A normal `clr+libs` build is another way to build that prerequisite closure.
Select a supported host compiler independently of the Emscripten guest compiler.

Both guest widths use the ordinary host Crossgen2. Its normal Linux x64
self-contained location is
`artifacts/bin/coreclr/browser.wasm.Release/x64/crossgen2/crossgen2`.
The explicit `--targetarch` selects the guest type system. Portable generation
returns before native JIT initialization; the normal tool's copied cross-JIT
does not provide or imply wasm64 code generation.

Build the actual wasm64 managed framework inputs without ReadyToRun:

```sh
./build.sh -os browser -arch wasm64 -c Release \
  -subset clr.corelib+libs.sfx+libs.oob /p:PublishReadyToRun=false
```

Stage a fresh managed-only scan from this checkout's published framework DLLs
and its actual wasm64 IL CoreLib. Native archives and a working browser host are
not inputs to portable generation. The following preparation also populates the
default helper testhost scan directory, and verifies every DLL name and SHA256
against its producer. Extra, missing or mismatched DLLs fail the check.

```sh
set -euo pipefail
helper_pack="$PWD/artifacts/bin/microsoft.netcore.app.runtime.browser-wasm64/Release/runtimes/browser-wasm64/lib/net12.0"
helper_corelib="$PWD/artifacts/bin/coreclr/browser.wasm64.Release/IL/System.Private.CoreLib.dll"
helper_default="$PWD/artifacts/bin/testhost/net12.0-browser-Release-wasm64/shared/Microsoft.NETCore.App/12.0.0"
helper_parent="$PWD/artifacts/obj/wasm-callhelpers/browser/wasm64"
mkdir -p "$helper_parent" "$helper_default"
helper_scan="$(mktemp -d "$helper_parent/managed-framework.XXXXXX")"
cp "$helper_pack"/*.dll "$helper_scan/"
cp "$helper_corelib" "$helper_scan/System.Private.CoreLib.dll"
cp "$helper_scan"/*.dll "$helper_default/"
python3 - "$helper_pack" "$helper_corelib" "$helper_scan" "$helper_default" <<'PY_STAGE'
from pathlib import Path
import hashlib, json, subprocess, sys
pack, corelib, scan, default = map(Path, sys.argv[1:])
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
sources = {path.name: path for path in pack.glob("*.dll")}
assert {"System.Runtime.dll", "System.Collections.dll"} <= sources.keys()
sources[corelib.name] = corelib
expected = {name: sha(path) for name, path in sources.items()}
for directory in (scan, default):
    actual = {path.name: sha(path) for path in directory.glob("*.dll")}
    missing, extra = expected.keys() - actual.keys(), actual.keys() - expected.keys()
    mismatched = {name for name in expected.keys() & actual.keys()
                  if expected[name] != actual[name]}
    assert not (missing or extra or mismatched), (directory, missing, extra, mismatched)
record = {
    "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
    "sources": {name: {"path": str(path), "sha256": expected[name]}
                for name, path in sorted(sources.items())},
    "scan": str(scan), "count": len(expected),
}
(scan / "source-inputs.json").write_text(json.dumps(record, indent=2) + "\n")
print(f"PASS: {len(expected)} source-built managed DLLs match both scan directories.")
PY_STAGE
```

The validated Release checkpoint contained 180 framework DLLs and one matching
CoreLib. The comparison derives the complete set from the selected producer;
the inventory can change as framework contents change. A CoreLib-only scan does
not establish complete framework table generation. This preparation does not
depend on successful `externals`/browser-host staging or fabricated native files.

Generate the canonical tables from that explicit fresh scan:

```sh
src/coreclr/vm/wasm/generate-coreclr-helpers.sh -c Release \
  --arch wasm64 --target-os browser --scan-path "$helper_scan"
```

The normal default scan location is the `helper_default` directory above.
Source output is isolated under `src/coreclr/vm/wasm/browser/wasm64/`; response
files and staging output are under `artifacts/obj/wasm-callhelpers/browser/wasm64/`.
Missing inputs must fail without falling back to wasm32 tables.

For the full entry-point checks, also build the ordinary framework-dependent
compiler DLL and run actual generation for both widths:

```sh
./dotnet.sh build src/coreclr/tools/aot/crossgen2/crossgen2.csproj -c Release \
  -p:TargetOS=browser -p:TargetArchitecture=wasm
python3 eng/wasm/tests/test_callhelper_targets.py \
  --dotnet "${DOTNET_INSTALL_DIR:-$PWD/.dotnet}/dotnet" --full-generation \
  --evidence-dir artifacts/obj/callhelper-full-verification
```

See [`generate-coreclr-helpers.md`](../../../src/coreclr/vm/wasm/generate-coreclr-helpers.md)
for compiler/configuration overrides, alternate output roots and the wasm32
byte-for-byte control. Generation and native compilation do not establish
working managed/native transitions or ReadyToRun execution.

## ICU and toolchain requirements

After SDK acquisition, native wasm64 builds automatically run the selected SDK's
official `embuilder.py --wasm64 build` for the seven explicit `-nostdlib` runtime
dependencies: `libstubs`, `libc`, `libdlmalloc`,
`libclang_rt.builtins-wasmsjlj`, `libc++-wasmexcept`, `libc++abi-wasmexcept` and
`libunwind-wasmexcept`. The `-wasmexcept` variants use non-legacy native Wasm
exceptions. Preparation sets `EM_CACHE` to `Memory64EmscriptenCacheDir` and clears
`EM_FROZEN_CACHE`; selecting the SDK's stock frozen cache is rejected. Every
member of each resulting archive must be recognized as wasm64 before native
compilation proceeds.

The existing ICU transport has no wasm64 native payload. The source recipe
builds the pinned ICU source with the selected Memory64 toolchain, checks every
archive member's architecture, and links/executes an ICU probe before publishing
the default dependency. An explicit `Memory64IcuDir` is verified without being
overwritten. The source/toolchain fingerprint and archive hashes must agree on
reuse. Follow [`README-memory64-icu.md`](../../../eng/wasm/README-memory64-icu.md)
for overrides, cache isolation and verifier commands.

The compiler must also correctly assemble table64 instructions. Investigation
of the [pinned LLVM MC checker](https://github.com/dotnet/llvm-project/blob/b7cbe9c6cf3ea97cc5822cf324cbcef06f54a397/llvm/lib/Target/WebAssembly/AsmParser/WebAssemblyAsmTypeCheck.cpp)
reproduced a defect:
wasm64 C compiled to textual assembly is rejected when reassembled because the
MC checker expects an i32 indirect-call index where the table requires i64.
The direct C-to-object path can succeed, so a successful native C or ICU probe
does not establish that the runtime's `.S` sources can be assembled.
An immutable [LLVM main source inspection](https://github.com/llvm/llvm-project/blob/01bf8c1e1985ac5e191ef607849c1c31b8dc8d34/llvm/lib/Target/WebAssembly/AsmParser/WebAssemblyAsmTypeCheck.cpp)
found the same assumption; that main revision's binary was not executed in the
comparison. The investigated SDK label was `6.0.2`, while its executables
reported Emscripten `6.0.3` and Clang `23.1.0`. A new SDK label alone is not
evidence of a fix. Record actual compiler versions and revisions as well as
the repository's version label.

A separately built, patched `llvm-mc` is used only for an experimental validation
lane. Its explicit assembly-compiler wrapper preprocesses `.S` with the stock
compiler, preserves the effective target features, and invokes that independent
MC binary; C/C++ compilation and final linking retain the stock tools.
The stock SDK is not replaced, and type checking remains enabled. This lane needs
separate object directories and a producer record containing the LLVM revision,
patch, compiler/wrapper paths and hashes, commands and known debug-information
differences. Its results must be labelled patched-toolchain results. They cannot
establish acceptance of the unmodified pinned toolchain or a deployable runtime.

## Verification boundaries

[`eng/wasm/tests/README.md`](../../../eng/wasm/tests/README.md) describes the
CoreLib property/final-product checks and native product inspection. Verify
wasm32 controls and both Release/Checked wasm64 products. Archive-member checks,
actual memory/table type inspection and independent module validation establish
build properties. Inspect the runtime, native-library and interpreter objects,
published archives, prepared sysroot libraries and relink kit, rather than only
compiler probes. Check the final `corerun` module's Memory64/table64 types and
validate it with both Node's `WebAssembly.Module` and `wasm-opt`; these checks do
not execute a guest.
Record source/toolchain identities and stock versus patched lane with each result.

The remaining execution gates include native bidirectional ABI calls, GC/EH,
suspended continuations, actual high addresses, the normal browser loader and
WebCIL path, complete JS interop, real R2R method execution, and SDK/workload
publishing. Completion of this build checkpoint must not be reported as completion
of those gates.
