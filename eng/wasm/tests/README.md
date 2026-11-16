# CoreLib target and product layout checks

Run these commands from the repository root with the checkout-pinned SDK.
The property tests inspect the actual CoreLib project for both Wasm targets in
Release and Checked, including rejection of a conflicting `Platform` override.

```sh
DOTNET_HOST_PATH="${DOTNET_INSTALL_DIR:-$PWD/.dotnet}/dotnet" python3 eng/wasm/tests/test_corelib_target.py -v
```

Build each CoreLib IL product in its own target and configuration directory:

```sh
./build.sh -os browser -arch wasm -c Release -subset clr.corelib
./build.sh -os browser -arch wasm -c Checked -subset clr.corelib
./build.sh -os browser -arch wasm64 -c Release -subset clr.corelib
./build.sh -os browser -arch wasm64 -c Checked -subset clr.corelib

./dotnet.sh run --file eng/wasm/tests/check-corelib-layout.cs -- \
  artifacts/bin/coreclr/browser.wasm.Release/IL/System.Private.CoreLib.dll \
  artifacts/bin/coreclr/browser.wasm.Checked/IL/System.Private.CoreLib.dll \
  artifacts/bin/coreclr/browser.wasm64.Release/IL/System.Private.CoreLib.dll \
  artifacts/bin/coreclr/browser.wasm64.Checked/IL/System.Private.CoreLib.dll
```

The metadata check requires all four paths. It checks the actual `IntPtr.Size`
and `UIntPtr.Size` IL constants in each final product.
Missing products or a mismatched width fail the check. The internal constant-only
`AsmOffsets` type is removed by CoreLib in-build trimming. Native runtime builds
also compile `AsmOffsets.cs` with C++ `static_assert` checks against native
types; run both Release and Checked to validate that boundary.

These checks do not load or execute the guest CoreLib and do not establish
working managed/native transitions, GC, exception handling, or browser startup.

## Native product architecture and module validation

After building each target/configuration, pass its actual products explicitly.
The Release example below uses normal output paths for a complete SDK containing
the [LLVM table-index fix](https://github.com/Edenlia/llvm-project/commit/8620eb7b55e857a5f6e430be624b5a6605e8c53e),
with the ordinary Clang assembler and no runtime assembly wrapper. This requires
an actual successful build with that SDK; the focused MC validation alone does
not supply those products. A locally patched SDK still uses the `patched` label
and a producer record; `stock` is reserved for an unmodified SDK build. Set
`WASM64_PRODUCER` to its successful producer JSON record, `WASM_PRODUCT_NODE` to
the selected Node executable, and `EM_CACHE` to the isolated Memory64 sysroot
cache used for that build. `EMSDK_PATH` selects the matching SDK.

```sh
WASM64_PRODUCT_DIR=artifacts/bin/coreclr/browser.wasm64.Release
WASM64_OBJECT_DIR=artifacts/obj/coreclr/browser.wasm64.Release
WASM64_NATIVE_DIR=artifacts/bin/native/net12.0-browser-Release-wasm64/sharedFramework
WASM64_SYSROOT_DIR="$EM_CACHE/sysroot/lib/wasm64-emscripten"
wasm64_native_arguments=(--native-library "$WASM64_PRODUCT_DIR/libclrinterpreter.a")
for wasm64_archive in \
  "$WASM64_OBJECT_DIR/libs-native/System.Native/libSystem.Native.a" \
  "$WASM64_OBJECT_DIR/libs-native/System.Globalization.Native/libSystem.Globalization.Native.a" \
  "$WASM64_OBJECT_DIR/libs-native/System.IO.Compression.Native/libSystem.IO.Compression.Native.a" \
  "$WASM64_NATIVE_DIR"/*.a \
  "$WASM64_SYSROOT_DIR/libstubs.a" \
  "$WASM64_SYSROOT_DIR/libc.a" \
  "$WASM64_SYSROOT_DIR/libdlmalloc.a" \
  "$WASM64_SYSROOT_DIR/libclang_rt.builtins-wasmsjlj.a" \
  "$WASM64_SYSROOT_DIR/libc++-wasmexcept.a" \
  "$WASM64_SYSROOT_DIR/libc++abi-wasmexcept.a" \
  "$WASM64_SYSROOT_DIR/libunwind-wasmexcept.a"
do
  wasm64_native_arguments+=(--native-library "$wasm64_archive")
done
python3 eng/wasm/tests/check_memory64_products.py \
  --emsdk "$EMSDK_PATH" \
  --runtime-archive "$WASM64_PRODUCT_DIR/libcoreclr_static.a" \
  --runtime-archive "$WASM64_PRODUCT_DIR/libcoreclr_gen_static.a" \
  "${wasm64_native_arguments[@]}" \
  --corerun "$WASM64_PRODUCT_DIR/corerun.wasm" \
  --kit "$WASM64_PRODUCT_DIR/corerun-link" \
  --icu artifacts/bin/icu/browser-wasm64/Release/native \
  --node "$WASM_PRODUCT_NODE" \
  --node-arg=--experimental-wasm-exnref \
  --build-lane patched \
  --toolchain-evidence "$WASM64_PRODUCER" \
  --report artifacts/log/memory64-products-release.json
```

For the retained historical external-`llvm-mc` experiment, use
`artifacts/bin/coreclr/browser.wasm64.Release/patched-llvm-mc` and
`artifacts/obj/coreclr/browser.wasm64.Release/patched-llvm-mc` instead, together
with that experiment's original producer record (including its wrapper hash).
The example's archive and module checks are otherwise the same.

Use the corresponding Checked runtime, object and published-native paths for
the Checked build, together with its own successful producer record. The source-
built ICU dependency can be reused with its verified producer manifest. Repeat
`--runtime-archive` and `--native-library` for all products in the claimed scope;
these options do not discover additional product directories implicitly.
Every archive shipped in the selected relink kit is checked independently.
Published `libs.native` archives and corerun's separately compiled native side-build
can have different bytes; both must contain only verified 64-bit members.
Runtime archive copies and ICU archives in the kit must match their selected sources.

The inspector uses the selected SDK's `llvm-ar` and `llvm-readobj` to inspect every
archive member, including repeated member names. Thin archives, missing products,
unrecognized members, wasm32 objects and mixed widths fail. Wasm object members
must carry linking metadata; a final linked module inside an archive is rejected.
An LLVM bitcode member
requires a matching-major `llvm-dis` supplied by `--llvm-dis /path/to/llvm-dis`
unless the SDK already contains it. Its original target triple and pointer data
layout must both identify wasm64. A missing bitcode reader returns `BLOCKED`
(exit 2). Clang IR re-emission is deliberately avoided because it can rewrite a
module's original target triple and data layout.

For the final ordinary Wasm module, the inspector reads the actual memory/table
address-type flags, requires both Memory64 and table64 for this toolchain contract,
constructs `WebAssembly.Module` in the selected Node engine, and independently
validates the binary with the SDK's `wasm-opt`. It never instantiates the module.
The JSON report records paths, hashes, tool versions, engine flags, limits, member
counts, the ICU producer manifest, and the build lane.

For a product built using a patched assembler/compiler wrapper, use
`--build-lane patched --toolchain-evidence /path/to/producer-manifest.json`.
The evidence has this shape (paths may be absolute or relative to the manifest):

```json
{
  "build_lane": "patched",
  "build_status": "success",
  "source_repo": "/path/to/llvm-source-checkout",
  "source_revision": "<full 40-character source HEAD>",
  "patch": { "path": "table64.patch", "sha256": "<64-character SHA256>" },
  "tools": {
    "compiler": { "path": "/path/to/clang-binary", "sha256": "<SHA256>" },
    "assembler": { "path": "/path/to/patched-llvm-mc", "sha256": "<SHA256>" },
    "wrapper": { "path": "/path/to/assembler-wrapper", "sha256": "<SHA256>" }
  },
  "command": ["./build.sh", "-os", "browser", "-arch", "wasm64", "..."]
}
```

The inspector requires a successful producer build record and checks the source
checkout HEAD and actual patch/tool hashes. Prepared/unrun records are rejected.
Compiler and assembler records are required; include the wrapper when one is
used. ICU producer identity fields, build command, tool hashes, and its historical
successful pointer-8 probe record are also required; the probe is not rerun here.
A successful patched lane does not establish stock toolchain acceptance.
Use `--build-lane stock` only when the products were built entirely with the
unmodified toolchain; the pinned SDK's table64 assembler defect currently blocks
that complete runtime build (see [the bring-up notes](../../../docs/design/features/wasm64-bringup.md)).
The ICU producer record remains separate: a verified stock
ICU archive reused by a patched runtime is still recorded as that stock dependency.

The small verifier fixtures use real LLVM objects and standalone Wasm modules:

```sh
EMSDK_PATH="$EMSDK_PATH" WASM_PRODUCT_NODE="$WASM_PRODUCT_NODE" \
  python3 eng/wasm/tests/test_memory64_products.py -v
```

Fixture success validates the inspector. Product-inspection success establishes
the architecture and module-validation assertions for the supplied files; it does
not establish working CoreCLR execution, native ABI transitions, GC/EH, high-address
access, browser loading, or ReadyToRun execution.
