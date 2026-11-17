# CoreCLR browser JS exception profile

`CoreClrBrowserJsEh=true` is an experimental, default-off product for embedding
the CoreCLR interpreter into an existing Emscripten JavaScript-SjLj application.
The motivating consumer is UE's Wasm64 Installed Build: its precompiled
ImageWrapper, PNG and FreeType objects use JavaScript SjLj. Emscripten 6.0.10
does not support linking those objects with the existing native-Wasm-EH
CoreCLR product. A link-only exception setting does not convert their ABI.

Use a separate worktree and output/cache directories for this product. The
normal build entry is unchanged, for example:

```powershell
./eng/build.ps1 -subset clr.runtime+clr.hosts+clr.corelib+libs.native+host.native `
  -os browser -arch wasm64 -runtimeFlavor CoreCLR -configuration Release `
  /p:CoreClrBrowserJsEh=true /p:WasmNativePthreads=true
```

Normal host prerequisites and the matching wasm64 ICU recipe remain required.
An explicitly supplied completed ICU dependency is verified by its original
manifest; this profile does not relabel or overwrite it. Keep every project in
the build graph on the same source revision, native options and output layout.

The supported capability is deliberately narrow:

- Browser/CoreCLR/wasm64, native pthread compatibility, one managed runtime
  thread, and the interpreter.
- Loose, ordinary IL PE assemblies. ReadyToRun headers and native image loading
  are rejected before native image registration; configuration cannot enable
  ReadyToRun or disable the interpreter.
- Runtime-owned C and C++ frames use Emscripten JS exceptions consistently.
  The SDK selects its ordinary matching C/C++ libraries and startup objects.
- The corerun link kit records the exception model and restricted assembly
  capabilities. Its WebCIL path rejects this profile.

This does not enable the browser SDK's general JS-EH publishing path. Its
existing CoreCLR native-EH requirement remains in place. It does not add managed
multithreading, R2R, WebCIL or runtime code generation.

Interpreted catch resumption uses the existing typed C++
`ResumeAfterCatchException` protocol. A context restore in this profile must
identify a live interpreter frame belonging to the current thread and method.
Other native or compiled restore requests report unsupported capability; a
compiled instruction pointer is never interpreted as bytecode. The default
native-Wasm-EH implementation retains its original exception tag and behavior.

Native C++ exceptions must remain inside runtime-owned EH-enabled frames.
Existing application C frames compiled with `-fignore-exceptions` can swallow
them. An embedding boundary must complete managed exception handling inside
the runtime and return through its defined native result protocol.

Validate a newly produced runtime with real initialization, managed/native
round trips, typed managed catches, throw-from-catch, rethrow, filters/finally
and owner-thread shutdown. Independent C++ exception probes establish language
compatibility; they do not constitute a completed CoreCLR or UE gameplay test.
