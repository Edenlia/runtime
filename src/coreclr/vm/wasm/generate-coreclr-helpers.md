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

For `--arch wasm64`, inputs come from the matching `browser-wasm64` framework build, generated
source goes under `src/coreclr/vm/wasm/browser/wasm64/`, and the response file and staging output
go under `artifacts/obj/wasm-callhelpers/browser/wasm64/`. This target currently requires
`browser`. Missing wasm64 inputs are an error; the generator does not substitute wasm32
framework assemblies or tables.

Both guest widths use the ordinary host crossgen2. Its build directory remains
`artifacts/bin/coreclr/browser.wasm.<configuration>/<build architecture>/crossgen2/`.
The explicit `--targetarch` in the response file determines the guest type system and ABI;
portable generation returns before native JIT initialization. This path does not require a
wasm64 cross-JIT and does not enable wasm64 ReadyToRun compilation.

The relink targets for browser and wasi apps run the same crossgen2 mode over the app's own
assembly closure, so these checked-in files and a relinked app are produced by one code path.

By default the scripts generate **both** WebAssembly variations; pass `--target-os browser` or
`--target-os wasi` to regenerate only one:

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
| `-a`, `--arch <wasm\|wasm64>` | Guest architecture (default: `wasm`). `wasm64` defaults to `browser` and rejects `wasi`. |
| `--compiler-path <path>` | Explicit ordinary host crossgen2 executable or framework-dependent DLL. |
| `--output-root <path>` | Write beneath this root instead of the source tree; per-OS and wasm64 subdirectories are retained. |
| `-h`, `--help` | Show usage. |

After running, review and commit any changes to the generated files under
`src/coreclr/vm/wasm/browser/` and `src/coreclr/vm/wasm/wasi/`.

For example, after building the full browser-wasm64 framework closure, regenerate its tables
with a Release host compiler:

```bash
src/coreclr/vm/wasm/generate-coreclr-helpers.sh -c Release --arch wasm64
```

To scan Checked guest inputs with a Release host compiler on Linux x64, select that compiler
explicitly. An alternate output root is useful when comparing results without editing source:

```bash
src/coreclr/vm/wasm/generate-coreclr-helpers.sh -c Checked --arch wasm64 \
  --compiler-path artifacts/bin/coreclr/browser.wasm.Release/x64/crossgen2/crossgen2 \
  --output-root artifacts/obj/callhelpers-verification
```

The equivalent MSBuild properties are `CallHelperTargetArchitecture`, `CallHelperCompilerPath`,
and `CallHelperOutputRoot` on `generate-coreclr-helpers.proj`. Compiler paths and output roots
may be absolute or relative to the repository root. DLLs run with the current `DOTNET_HOST_PATH`
or the repository's `DotNetTool`; no separate helper-only compiler is used. Ordinary wasm32
invocations retain their previous compiler lookup, scan path, source output, and response-file
location.

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

## Target routing checks

The host checks exercise the real MSBuild entry point. Target validation requires only the
checkout-pinned SDK:

```bash
python3 eng/wasm/tests/test_callhelper_targets.py --dotnet .dotnet/dotnet \
  --evidence-dir artifacts/obj/callhelpers-target-validation
```

After building the ordinary browser-wasm host crossgen2 and the complete browser-wasm and
browser-wasm64 managed framework closures, build the standard framework-dependent compiler
DLL for the DLL-host validation cases, then enable actual generation as well:

```bash
./dotnet.sh build src/coreclr/tools/aot/crossgen2/crossgen2.csproj -c Release \
  -p:TargetOS=browser -p:TargetArchitecture=wasm
python3 eng/wasm/tests/test_callhelper_targets.py --dotnet .dotnet/dotnet \
  --full-generation --evidence-dir artifacts/obj/callhelpers-target-generation
```

In Release this compares regenerated wasm32 browser tables byte for byte with the checked-in
files. Other configurations verify stable regeneration against their own input closure. It also
checks the wasm64 input manifest, generated pointer width, and separate output and response
files. Missing compiler products or framework assemblies fail the generation checks. The
`--compiler` option selects an ordinary crossgen2 DLL, and `--configuration Checked` selects
Checked guest inputs; together they allow a Release host compiler to scan a complete Checked
framework closure. The checks retain commands, logs, input hashes, and generated source in the
evidence directory. They do not execute a Wasm guest.
