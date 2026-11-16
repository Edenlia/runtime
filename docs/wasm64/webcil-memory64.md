# IL WebCIL final memory model

The production IL converter can emit an unshared self-installing CoreCLR WebCIL
wrapper importing either Memory32 or Memory64. The payload format remains version 1
and the wrapper ABI remains version 2. Existing Mono version 0 and CoreCLR
Memory32 output bytes are unchanged.

`WebcilConverter.Memory64` selects the final wrapper's imported memory, imported
`__memory_base` global and `getWebcilSize` destination parameter. It does not
describe the native C pointer ABI. The Memory64 wrapper still uses i32 offsets
and lengths into its passive data segment for `memory.init`.

The SDK build and publish conversion tasks receive the public
`WasmWebcilMemory64` property:

| Native lane | C pointer size | Final wrapper model | SDK property |
| --- | --- | --- | --- |
| browser-wasm | 4 | Memory32 / i32 base | default false |
| native browser-wasm64 | 8 | Memory64 / i64 base | defaults true for the recognized RID, when unset |
| lowered wasm64 (`MEMORY64=2`) | 8 | Memory32 / i32 base | explicitly false |

The emitted browser host uses Emscripten's link-time `toIndexType` conversion
for imported globals and table growth. A lowered host therefore keeps i32
indices while its existing native-call adapter continues to pass i64 C pointers.
This macro is also present in the pinned
[Emscripten 6.0.2 source](https://github.com/emscripten-core/emscripten/blob/6.0.2/src/parseTools.mjs).
Executed native/browser acceptance used the explicitly selected 6.0.10 toolchain;
the repository SDK pin was not changed.

`ConvertDllsToWebcil.TargetArchitecture` separately protects the native ABI.
The SDK passes its resolved `TargetArchitecture`, with an exact
`browser-wasm64` RID fallback only when the architecture is unset. Both native
and lowered wasm64 reject explicit R2R images and skip optional prebuilt R2R
selection. Choosing Memory32 for lowering cannot make wasm32 native R2R usable
with an eight-byte C ABI. The existing wasm64 R2R gate remains in place.

Build and publish conversion stamps include the final model and native
architecture. Per-file cache validation also reads the wrapper's imported memory
model. Switching either direction replaces an opposite-profile IL wrapper,
including when its timestamp is newer than the input. Repeating an unchanged
build retains its output timestamp.

## Executed acceptance

The [receipt](evidence/2026-11-17-webcil-memory64.json) records exact source/input
hashes and task-local raw artifacts.

- The actual production task project builds with SDK 12 for its normal net and
  .NET Framework targets, with no warnings/errors. The existing
  `WebcilInWasmSizesTests` class runs 32 cases against the built converter/tasks.
- A separately built untouched baseline converter and the changed converter
  produce identical default bytes for real managed IL and matching wasm64
  CoreLib, for both Mono version 0 and CoreCLR version 1.
- Eight invocations of the real SDK configuration and build-conversion targets
  verify defaults, RID fallback, explicit lowering and bidirectional profile
  changes. An unchanged profile skips conversion.
- The real converted IL and matching CoreLib load through the minified production
  browser host and native C stubs under Node 24 and Chrome 157. All three lanes
  above pass both buffered and streaming instantiation, imported memory/base
  checks, `getWebcilSize`, aligned allocation, exact native payload comparison,
  callback pointer slots, table growth and failed-profile cleanup.

The native C host functions are explicit stubs: these runs do not execute
CoreCLR or any managed guest method. They do not validate GC/EH, high-address
memory, R2R or the complete SDK publish/workload flow. General SDK
`IsBrowserWasmProject` dispatch and runtime-pack native paths still contain
`browser-wasm` assumptions and need a separate lane-plumbing change.

The wrapper imports unshared memory. Supporting UE's pthread/shared-memory
WebCIL path is a separate capability; these results do not establish that route.
The existing R2R-only loader's Emscripten table-global compatibility is also
outside this IL checkpoint. The table adapter was tested against the real
exported table without enabling unsupported wasm64 R2R.
