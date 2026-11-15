# CoreCLR wasm64 bring-up

This work starts from runtime commit
`2b5ea9af2991abe307beb855729ab52409d6333f`. The first checkpoint introduces
target selection, target layouts, native build selection, an independent host
call-helper tool, and test infrastructure. It does not yet provide an executable
CoreCLR wasm64 runtime.

## Target contract

| Surface | wasm32 | wasm64 |
| --- | --- | --- |
| Build architecture | `wasm` | `wasm64` |
| Internal type-system architecture | `Wasm32` | `Wasm64` |
| Development RID | `browser-wasm` | `browser-wasm64` |
| Pointer, native integer, reference width | 4 bytes | 8 bytes |
| Native source directory | `wasm` | `wasm` |
| Native target symbols | `TARGET_WASM`, `TARGET_WASM32`, `TARGET_32BIT` | `TARGET_WASM`, `TARGET_WASM64`, `TARGET_64BIT` |
| CoreLib symbols | `TARGET_WASM`, `TARGET_32BIT` | `TARGET_WASM`, `TARGET_WASM64`, `TARGET_64BIT` |
| Emscripten selection | default | `-m64` at compile and link time |

`TargetsWasm` describes the family; `TargetsWasm64` describes its 64-bit member.
An explicit browser `wasm64` selection is preserved. The browser default stays
`wasm`. A wasm64 target requires CoreCLR, browser, and the current single managed
thread execution model. WASI, Mono wasm64, managed multithreading, and Memory64
lowering compatibility mode are outside this checkpoint.

`browser-wasm64` is a development identity. This checkpoint does not add a public
`System.Runtime.InteropServices.Architecture` value, a shipping RID graph entry,
or an installable workload. SDK resolution, runtime/compiler packs and workload
publication require their own implementation and validation.

RVA, metadata tokens, counts and flags retain their format-defined widths. Host
type-system tests explicitly distinguish 8-byte references/native integers from
4-byte metadata-like fields and 16-byte Wasm vectors. These tests use the guest
target's layout, independently of the host pointer size.

## Observed external ABI

The selected checkout pins SDK `12.0.100-alpha.1.26557.102` and names Emscripten
`6.0.2` in its cache configuration. The restored official toolchain package
actually reports `emcc 6.0.3` and `clang 23.1.0`. Both the configured identity
and actual executable versions must be recorded in subsequent runs.

The unmodified restored compiler's `-m64` output was inspected and executed:

| Probe observation | Result |
| --- | --- |
| `void*`, `size_t`, `intptr_t`, function pointer | 8 bytes |
| `{ int64_t; double; void*; }` | size 24, alignment 8, pointer offset 16 |
| Aggregate parameter and return | indirect addresses are i64 |
| Mixed scalar indirect call | `(i32, i64, f64, f32) -> i64` |
| Memory address type | i64 |
| Table address type | i64 |
| Native struct return and indirect callback | executed successfully in Node and Chromium |

Memory64 alone does not imply table64. The table result above is an observation
of this compiler's output. Managed lowering, VM signature keys, helper C++
types, transition blocks, saved contexts and stackwalk/EH layouts still need
to implement and validate a common contract against this ABI.

The stock toolchain's frozen cache contains wasm32 system libraries only. The
wasm64 probe used a separate `EM_CACHE` and cleared `EM_FROZEN_CACHE` to let the
unmodified compiler build its own libraries. The stock cache was preserved.
No compiler patch or alternative toolchain was used. Future runtime builds
must also select an isolated writable cache when system libraries are missing.

Native probes executed with Node `v24.22.1` without extra Wasm engine flags.
The repository-provisioned Linux browser reports `Chrome/157.0.8103.0`, while
the configured download label is `157.0.8103.78`. Browser execution was observed
through CDP, including the assertion results and exit code. These are native
toolchain probes, not managed CoreCLR execution.

## Bootstrap and unsupported paths

`clr.callhelpers` builds a framework-dependent host tool at
`artifacts/bin/coreclr/browser.wasm64.Release/<host-arch>/crossgen2-callhelpers/`.
The directory contains its managed dependency closure and no native JIT or JIT
interface library. The binary only accepts portable call-helper mode and is
kept separate from the normal Crossgen2 compiler output.

Architecture-aware regeneration selects matching scan directories, response
files and source output. Native test and browser relink targets use the separate
`Crossgen2CallHelpersPath` for wasm64 and invoke its DLL with the SDK host.

Actual wasm64 helper emission is deliberately rejected until the managed ABI
is implemented. In particular, native type tokens for `this`/struct pointers,
`ARG_IND` and portable frame-pointer declarations still need coordinated
updates. Existing wasm32 helper tables are not substituted. Full wasm64 JIT
and ReadyToRun paths also reject the target explicitly.

CoreLib IL output and native object selection are independently testable at
this checkpoint. Ordinary browser host startup, IL-only WebCIL, CLR native
transitions, GC/EH, high-address objects, JS interop and compiled execution
remain blocked by their unimplemented dependencies.

## Native dependencies and memory

The current ICU transport (`11.0.0-alpha.1.26418.1`) contains no `browser-wasm64`
payload. Native builds report the missing header/archive set before starting
the native build body. `WasmIcuNativeDir` can select a separately built ICU;
the directory must have `include/unicode/utypes.h` and
`lib/libicu{uc,i18n,data}.a` from the selected Memory64 toolchain. The presence
check is not an object-architecture validator; the native linker must reject
incompatible supplied archives. Globalization is not disabled to conceal this
dependency.

Native corerun keeps BigInt and 64-bit heap views for Node on wasm64. Its initial
linear memory remains 128 MiB with an 8 GiB maximum; browserhost defaults to
32 MiB with an 8 GiB maximum. The maximum is a bound, not a startup allocation.
A toolchain probe verified a 32 MiB initial Memory64 memory with the 8 GiB
maximum. This is not a selected or verified managed GC reservation policy.

The corerun link kit records `target-architecture.txt`. A wasm64 test requires
a matching marker, preventing an explicit wasm32 kit override from passing
input selection. Legacy markerless wasm32 kits remain supported.

## Reproduce the available checks

Use the checkout-pinned SDK. When sharing the SDK executable between worktrees,
set `DOTNET_INSTALL_DIR` to the directory containing that exact SDK; do not copy
CoreLib, helpers, native artifacts or packs between worktrees.

```sh
./build.sh -os browser -arch wasm64 -c Release -subset clr.corelib+clr.callhelpers

DOTNET_HOST_PATH=<pinned-sdk>/dotnet python3 eng/wasm/tests/test_target_selection.py -v
python3 src/tests/Common/scripts/tests/test_run_arguments.py -v
DOTNET_TEST_HOST=<pinned-sdk>/dotnet python3 src/tests/Common/scripts/tests/test_run_results.py -v
DOTNET_HOST_PATH=<pinned-sdk>/dotnet python3 eng/wasm/tests/test_callhelper_routing.py -v

# Requires provision.emsdk, CMake and Ninja. Compiles C/C++ objects for each target.
eng/native/tests/wasm-target.sh
# Executes native toolchain probes in Node with an isolated generated sysroot cache.
eng/native/tests/wasm-abi.sh

<pinned-sdk>/dotnet test \
  src/coreclr/tools/aot/ILCompiler.TypeSystem.Tests/ILCompiler.TypeSystem.Tests.csproj \
  -c Release
```

For a restricted home directory, put `DOTNET_CLI_HOME`, `XDG_RUNTIME_DIR`,
`XDG_DATA_HOME`, `NUGET_PACKAGES` and `npm_config_cache` in writable task
directories. Record these paths. Use a single heavy native build at a time.

For the unchanged wasm32 baseline on Debian 13, the host cross-JIT built with
official distribution clang 19.1.7. The Emscripten-bundled clang 23 and system
GCC 14 failed upstream host JIT warning checks (`unused-template` and `nonnull`,
respectively). Their failed logs were retained. Selecting `-clang19` for the
host leaves the repository-pinned Emscripten guest compiler unchanged. Use
`CLR_READELF=/usr/bin/readelf` when the selected LLVM bundle lacks
`llvm-readelf`; no compiler patch or warning suppression is needed for the
successful host cross-JIT lane.

## Checkpoint evidence and next gate

This is an unintegrated, Release-only development checkpoint. Checked builds,
a full wasm32 product regression on the feature worktree, and the browser/SDK
workload matrix have not been run. The complete foundation acceptance gate
remains open.

Host validation has executed the complete type-system suite (359 passed,
0 skipped), including explicit Wasm32/Wasm64 layout cases. The architecture
selection suite executes eight tests, including wrong-RID, wrong-runtime,
threading and ReadyToRun negative cases. Native C/C++ compile assertions cover
both widths and reject a compiler/target mismatch. CoreLib wasm64 IL and the
helper-only host executable have been built successfully.

Runner validation covers argument forwarding, failure propagation, kit
architecture selection, and stale results that could otherwise turn an empty
wasm64 run into a false pass. Analysis-only runs preserve existing results.
The wasm32 baseline must separately establish product and execution results;
native toolchain probes and host compiler tests cannot establish it.

The unchanged upstream baseline completed the Release `clr+libs+packs` build
with clang 19 as the host compiler (0 warnings/errors). The selected standalone
EH `finally` and GC `keepalivetry` tests each executed once through the existing
MSBuild/Node backend, with `DOTNET_InterpMode=3`, expected/actual exit 100,
and zero skips. Matching Release browser call-helper regeneration produced no
tracked source changes.

The upstream `run.sh` entry itself was blocked before guest execution: its runner
clears `DOTNET_CLI_HOME`, and the nested SDK tries to write to a read-only home.
Those zero-execution attempts are recorded separately from the successful
backend tests. This feature branch preserves `DOTNET_CLI_HOME` and
`DOTNET_INSTALL_DIR` for the nested SDK while forwarding runtime knobs to the
guest environment script. It uses `null` to remove those knobs from the host;
an empty string leaves a variable present on .NET 12. Six host result/environment
regressions, including a real nested SDK launch, pass alongside the eight shell
argument tests. Browser JS and workload execution remain `NOT RUN` for this
checkpoint.

The next implementation checkpoint is the managed/native ABI, followed by GC
and browser loading. Freeze the common helper/VM/layout contract before
creating those dependent feature branches. Integrate only the checks actually
executed; retain `BLOCKED`/`NOT RUN` status for unavailable product, browser,
workload and high-memory lanes. The integration branch must not be treated as
a shipping-support claim.
