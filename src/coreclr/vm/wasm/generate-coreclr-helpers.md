# Generating CoreCLR WebAssembly call helpers

The `generate-coreclr-helpers.cmd` (Windows) and `generate-coreclr-helpers.sh` (Linux/macOS)
scripts in this directory regenerate the checked-in CoreCLR call-helper source files used by the
WebAssembly runtime. They parse their arguments and hand the work to
`generate-coreclr-helpers.proj` next to them, which runs crossgen2 in
`--generate-portable-callhelpers` mode over the managed framework assemblies to emit the native
P/Invoke, reverse-P/Invoke, and interpreter-to-managed call helpers, including the shared static
QCall/FCall entrypoint table. The generator lives in
[`ILCompiler.ReadyToRun/PortableCallHelpers`](../../tools/aot/ILCompiler.ReadyToRun/PortableCallHelpers) so it can use crossgen2's
type system to compute the wasm ABI layout of the structs that cross the boundary.

Keeping the scan paths, the crossgen2 lookup and the module list in the project rather than in the
scripts means they are stated once instead of once per shell language.

Each run leaves the exact generator invocation in a response file under
`artifacts/obj/wasm-callhelpers/<target os>/generate-coreclr-helpers.rsp`, which is the first thing
to look at when a regenerated table is not what was expected.

The relink targets for browser and wasi apps run the same crossgen2 mode over the app's own
assembly closure, so these checked-in files and a relinked app are produced by one code path.

By default the scripts generate **both** WebAssembly variations; pass `--target-os browser` or
`--target-os wasi` to regenerate only one:

The architecture defaults to `wasm` (32-bit). `--arch wasm64` selects the separate browser
Memory64 target and defaults the OS to `browser`; `wasi` with `wasm64` is rejected. The wasm64
entry point currently diagnoses the missing managed/native ABI implementation instead of
emitting helpers with wasm32 pointer declarations. Selecting the target does not yet make
helper generation or runtime execution available.

| Target OS | Output directory                | Default scan path (testhost) |
|-----------|---------------------------------|------------------------------|
| `browser` | `src/coreclr/vm/wasm/browser/`  | `artifacts/bin/testhost/net12.0-browser-<config>-wasm/shared/Microsoft.NETCore.App/12.0.0/` |
| `wasi`    | `src/coreclr/vm/wasm/wasi/`     | `artifacts/bin/testhost/net12.0-wasi-<config>-wasm/shared/Microsoft.NETCore.App/12.0.0/` |

Each run emits three files into the output directory:

- `callhelpers-pinvoke.cpp`
- `callhelpers-reverse.cpp`
- `callhelpers-interp-to-managed.cpp`

## The shared QCall/FCall table

`callhelpers-pinvoke.cpp` contains an entrypoint table for all P/Invokes in the application, as well as all [QCalls and FCalls in System.Private.CoreLib](../../../../docs/design/coreclr/botr/corelib.md#Calling-from-managed-to-native-code). A few specialized FCalls have separate internal runtime implementations that are not included in this table. The QCalls and FCalls are discovered by scanning the members of System.Private.CoreLib to find the corresponding methods.

## The P/Invoke module list

Only the framework native libraries the runtime links statically get an entry in the generated
P/Invoke table. `generate-coreclr-helpers.proj` imports that list from
[`eng/wasm/WasmPInvokeModules.props`](../../../../eng/wasm/WasmPInvokeModules.props), which
`CLRTest.WasmCorerun.targets` imports
too when it links a test-specific corerun, so the checked-in tables and the tests' own cannot be
edited apart.

The browser runtime SDK packages the same props file beside `BrowserWasmApp.CoreCLR.targets`, so
in-tree helper generation, runtime tests, and SDK app builds all consume the canonical list.

Adding a module means editing the props file, rerunning these scripts, and committing the
regenerated files in the same change. A module missing from the list surfaces as a
`DllNotFoundException` at run time rather than as a build failure.

## What needs to be built first

The generator scans the **managed framework assemblies** in the `testhost` folder produced by a
`clr+libs` build, and runs the self-contained crossgen2 that the same build produces. Because the
scripts generate both the `browser` and `wasi` variations by default, you must build **both**
WebAssembly flavors before running them, or pass `--target-os` to regenerate only the flavor you
built. The first build of either flavor also downloads and
provisions the Emscripten SDK (emsdk) automatically.

From the repository root:

**Windows:**
```cmd
.\build.cmd clr+libs -os browser -c Release
.\build.cmd clr+libs -os wasi    -c Release
```

**Linux/macOS:**
```bash
./build.sh clr+libs -os browser -c Release
./build.sh clr+libs -os wasi    -c Release
```

Notes:

- Use a matching `-c <Debug|Release|Checked>` for the configuration you intend to pass to the
  generator script (the script derives the scan path from the configuration name).
- If a required `testhost` scan path or crossgen2 is missing, the script stops and prints the
  exact `build` command needed to produce it.

## Which configuration to generate from

Generate the checked-in tables from a **Release** build. The CI check regenerates them from
Release and compares exactly.

The tables are linked into every configuration's corerun, so their entries must not depend on the
configuration. Debug and Release libraries, a Checked or Release CoreLib, and a Checked or Release
crossgen2 all produce the same P/Invoke, reverse-thunk and interpreter-to-managed entries. The
trailing `// <assembly>, ...` comments on the P/Invoke table are the exception. They list the
assemblies that still reference each import after the library build trims them, and that set
differs by configuration. For example, Debug `System.Net.NameResolution` keeps a reference to
`SystemNative_GetErrNo` that Release trims. Tables regenerated from Debug therefore show
comment-only diffs that the CI check rejects.

## Running the generator

Once both flavors are built, run the script from anywhere (it resolves the repo root itself):

**Windows:**
```cmd
src\coreclr\vm\wasm\generate-coreclr-helpers.cmd -c Release
```

**Linux/macOS:**
```bash
src/coreclr/vm/wasm/generate-coreclr-helpers.sh -c Release
```

### Options

| Option | Description |
|--------|-------------|
| `-c`, `--configuration <Checked\|Debug\|Release>` | Build configuration (default: `Release`). Determines the default scan paths. |
| `-s`, `--scan-path <path>` | Override the default **browser** scan path. |
| `-w`, `--wasi-scan-path <path>` | Override the default **wasi** scan path. |
| `-t`, `--target-os <browser\|wasi>` | Regenerate only this flavor (default: both). |
| `-a`, `--arch <wasm\|wasm64>` | Target architecture (default: `wasm`). `wasm64` is browser-only. |
| `-h`, `--help` | Show usage. |

After running, review and commit any changes to the generated files under
`src/coreclr/vm/wasm/browser/` and `src/coreclr/vm/wasm/wasi/`.

## Interpreter bootstrap without a target JIT

Portable helper generation does not invoke the JIT. The separate
`crossgen2_callhelpers.csproj` builds a framework-dependent host tool without copying native
JIT or JIT-interface libraries. It only accepts `--generate-portable-callhelpers`; compilation
requests fail explicitly. This keeps interpreter bootstrap independent of unfinished target
code generation and leaves the full compiler output untouched.

Build it for the wasm64 target from the repository root:

```bash
./dotnet.sh build src/coreclr/tools/aot/crossgen2/crossgen2_callhelpers.csproj \
  -c Release -p:TargetOS=browser -p:TargetArchitecture=wasm64
```

The tool is written to
`artifacts/bin/coreclr/browser.wasm64.Release/<build architecture>/crossgen2-callhelpers/crossgen2.dll`
and runs on the repository's SDK. This build establishes the bootstrap tool path; it does not
claim that wasm64 helper emission is ready. After the wasm64 managed/native ABI is implemented,
the regeneration entry point is:

```bash
src/coreclr/vm/wasm/generate-coreclr-helpers.sh -c Release --arch wasm64
```

That path selects the wasm64 testhost inputs, writes generated source under
`src/coreclr/vm/wasm/browser/wasm64/`, and leaves its response file and staging output under
`artifacts/obj/wasm-callhelpers/browser/wasm64/`. It never falls back to wasm32 framework inputs,
the wasm32 compiler directory, or the checked-in wasm32 output. Supplying a scan-path override
is the caller's responsibility; the compiler still uses the explicitly selected target layout.
ReadyToRun compilation for wasm64 is also rejected until the code generator is implemented.

## CI check

The Release `browser_wasm` CoreCLR build leg and the `wasi_wasm` CoreCLR build-only leg in
`eng/pipelines/runtime.yml` run
[`wasm-coreclr-callhelpers-check.yml`](../../../../eng/pipelines/common/templates/wasm-coreclr-callhelpers-check.yml)
after building. It regenerates the leg's own flavor with `--target-os` and fails if
`src/coreclr/vm/wasm/<os>/` differs from what is committed, printing the diff and the commands to
fix it. A stale QCall table can fail native linking if it still references a removed entrypoint.
Other stale entries can crash corerun at run time; a missing
`[UnmanagedCallersOnly]` thunk, for example, fails startup with
`GetUnmanagedCallersOnlyThunk: unknown thunk`. Library tests do not catch this because the app
relink generates its own tables.

The legs are triggered by the `wasm_coreclr_callhelpers` path subset in
`eng/pipelines/common/evaluate-default-paths.yml`, which covers the library sources, CoreLib and
the generator, so a change that only touches managed interop still runs the check.
