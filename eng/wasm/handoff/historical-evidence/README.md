# Local JS-EH wasm64 CoreCLR product and actual guest verification

Final frozen source: `1e9f8bd1e904fb5daaa5aabe3544f7d7eb472791`, branch `test/eden-web-js-eh`, clean.

The normal native graph (`clr.runtime+clr.hosts+clr.corelib+libs.native+host.native`), then normal `libs.sfx`, then the matching managed ILCompiler.ReadyToRun project all exited 0. These are separate actual successful executions; receipts and logs are preserved. No response-file replay, source patch during a build, forced clean, or prebuilt runtime substitution was used.

Authoritative CoreLib SHA256: `c776057cf6c7407340cadbd59584107c1740901b11c325c2c61a5adab493b6db`.
The complete framework inventory contains 180 DLLs. Metadata scanned 182 actual candidates and selected the five recursive guest inputs; every selected PE is IL-only with no managed native header. Fresh net12 HelperHost and the four matching ILC dependencies generated all three helper C++ files with actual CLI exit 0. Browser and Utils emitted Git stamps both actually equal the final source revision.

## Actual results

| Ordinary guest target | Node 24.19.0 | Chrome 157.0.8103.52 | Final shared memory/table | C/C++ pointer ABI |
| --- | --- | --- | --- | --- |
| Native64 | exit 0 | normal Module.onExit(0) | memory64 / table64 | 8 bytes |
| UE-compatible UeLowered | exit 0 | normal Module.onExit(0), 39 actual workers | memory32 / table32 after MEMORY64=2 lowering | 8 bytes |

Both ordinary CMake targets linked the actual complete graph, with 16 unique runtime archives and 19 ordered entries including repetitions/system dependency roles. Own main and complete fresh application helpers replace the corerun/framework helper owners. Only the actual production Browser and Utils JS libraries are linked; no BrowserHost footer/native library or guessed CLR services are supplied.

Each real execution requires:

- Genuine coreclr_initialize, create_delegate, and owner-thread coreclr_shutdown_2 return success; shutdown preserves a prior failure if one occurs.
- Native → managed → native PInvoke/UCO roundtrips return 45 and -33 with two native callbacks.
- A second real managed delegate returns flags 31 for both 9 and -17: typed catch, new throw from catch with preserved InnerException, nested rethrow object identity, three finally blocks, and one exception filter.
- Actual process exit 0 / browser Module.onExit(0), with no browser page/console errors.

The UE-compatible guest preserves measured installed UE5.9 settings: `-m64 -pthread -sMEMORY64=2 -sPROXY_TO_PTHREAD -sWASMFS=1`, 512MiB initial / 4GiB maximum, 4MiB stack, 1MiB default pthread stack, emmalloc, and the original dynamic thread-pool expression. The SDK owns standard libraries/startup. The product is native-pthread compatible while managed threading remains disabled. JS EH compile/link mode is explicit, interpreter-only, direct PE, no R2R/WebCIL.

## Preserved attempts and boundaries

- Failure1 (844e6c71): actual C++ compilation rejected private Frame::Next; the owning feature was corrected to the public accessor after all children exited.
- Failure2 (11f809be): real Rollup/Terser rejected a naked preprocessor conditional in the JS footer; the owning feature now uses valid link-time JS spread. The normal Release pipeline and actual SDK dependency evaluation passed before the final build.
- UeLowered/Attempt1-MissingEmmalloc retains the first frozen-cache link failure. The official exact-SDK embuilder prepared the actual UE allocator variant `libemmalloc-mt` in the new owned JS cache; the unchanged ordinary CMake target then passed. No flags or native/runtime inputs changed.
- The existing fingerprinted recipe9 ICU provider was verified and reused with exact content/tool identities. Its original b86 producer provenance remains unchanged; it was not relabeled as a JS-EH product.

`Guest/DirectPeGuest-1e9f8bd1/results.json` binds source, three normal graph receipts, actual CoreLib/framework/tool/header/JS/helper hashes, final Wasm limits, and the four guest receipts. Standard CMake File API query/reconfigure returned 0 with native assets, CMake cache bytes and compiler-input bytes unchanged. A separate read-only peer rehashed all metadata/helper/native/JS inputs with zero mismatches.

These results establish the interpreter-only CoreCLR product and independent real guest. They do not establish packaged UE gameplay, forced GC/finalizer draining, injected shutdown-failure tests, R2R/WebCIL support, arbitrary C++ exceptions unwinding through UE ignore-exceptions frames, or allocations above 4GiB. RuntimeProduct export and normal UE gameplay/package acceptance are owned by the coordinating task.
