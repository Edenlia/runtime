# Task-local fixed normal Clang

The stock UE-required Emscripten 6.0.10 SDK reports LLVM `a06d9165905ce89b5ffef2bbb84c886d60a9b8bf`, Clang
`24.0.0git`. Its normal assembler rejects its own compiler-generated wasm64 textual assembly at `call_indirect`:
`type mismatch, expected [i32] but got [i64]`. Direct C-to-object and the final Memory64-lowered C-only executable
work; those routes do not exercise runtime assembly sources.

`llvm-project/` is a detached sparse checkout of exactly that LLVM SHA. The existing user fix
`8620eb7b55e857a5f6e430be624b5a6605e8c53e` applies unchanged (`git apply --check` succeeded). Only the two checker
files are modified. The downloaded patch is `../UE/Analysis/8620eb7.patch`, SHA256
`2318fba38d1b4ecb1fe4af370b3e9283d164a70bddb8a8da9a05c92e681e5fb1`.

`build-fixed-clang.cmd` builds ordinary Clang and llvm-mc with VS 2026's MSVC 19.51, CMake 3.31.7 and Ninja 1.13.2.
Configuration is Release with assertions, WebAssembly backend, eight compile jobs and one link job. Tests,
benchmarks and examples are omitted from the producer build. The normal integrated assembler is retained and no
type-check suppression is used. Build output is `llvm-build/`; logs are `../UE/Logs/fixed-clang-build.log`. The two
early sparse-source configuration failures are preserved separately (`missing-libc` and `missing-docs`).

The first native build stopped at 1855/3326 actions because an MSVC relative object path exceeded Win32's length
limit, despite the machine's LongPathsEnabled setting. A short junction inside the primary cache fixed the first
object but a later 262-character object path still failed. The task-owned workspace `.git/uw` junction now points
to this exact Toolchain directory, reducing that path to 231 characters. Running the unchanged generated Ninja
graph from `.git/uw/llvm-build` compiled the affected objects successfully; outputs have not been moved or deleted.
`resume-fixed-clang-shortpath.cmd` is the resume entry.

Eight overlapping LLVM workers and another UE build also exhausted PCH virtual-memory headroom (OS1455); the
same graph now resumes with two workers, retaining all compiler and PCH settings. Logs preserve each failed
attempt. Heavy LLVM compilation was then interrupted through the task-owned session at the parent's request to
sequence the UE native retry; no user process was stopped. After the UE AutoBuild retry exited successfully, the
parent released the resource slot and the same graph resumed with two workers. Its final log is
`../UE/Logs/fixed-clang-build-final.log`: both Clang and llvm-mc linked, and the wrapper exited successfully.
Future heavy builds must likewise be sequenced with the parent.

The official Emscripten override is process-local `EM_LLVM_ROOT=<absolute tool bin>`; see its
`upstream/emscripten/tools/config.py::parse_config_file` and `shared.py::llvm_tool_path_with_suffix`.
The patched producer must be exercised via that normal driver route after build exit success. Original emsdk
binaries and the Installed UE tree must remain unchanged. A separate overlay may combine the newly built normal
Clang with hash-verified stock linker/tools/resource headers; its provenance and probe results must identify the
mixed producer explicitly.

Runtime's own pinned SDK remains 6.0.2. This compiler is an experimental UE 6.0.10 compatibility lane, not a silent
runtime pin update. A successful compiler build/probe does not establish complete runtime native build or guest
execution; Windows ICU portability is a separate prerequisite described in `../UE/Analysis/windows-native-route.md`.

## Accepted producer and verification

`fixed-llvm/provenance.json` records the exact source diff, patch/source/binary hashes, original SDK tool/resource
hashes and accepted result hashes. `finalize_fixed_verification.py` returned exit zero after checking these records.
Patched normal Clang SHA256 is `6c5ce14d830a38be10991a4d639a881b32d6399e3d59717cf8f9d3ce732590a4`.

Use only the per-process official override `EM_LLVM_ROOT=<this Toolchain>/fixed-llvm/bin`. The producer includes the
WebAssembly backend only; its default target is `unknown`, so callers must pass an explicit Wasm target as emcc does.
It is not a replacement Windows host C++ compiler. All other overlay linker/tools and target resource headers are
hash-verified copies of the original 6.0.10 SDK. Original SDK binaries were rehashed and remained unchanged. The
supported LLVM_ROOT switch automatically regenerated the task-local Emscripten system-library cache; its SDK
version, library recipes and stock linker remain 6.0.10.

Accepted evidence:

- `../UE/FixedProbe/assembly-results.json`: four compiler-generated textual-assembly cases (wasm32/wasm64, named and
  legacy immediate-zero table operands) reassemble successfully through the normal Clang driver. Verbose logs prove
  in-process `clang -cc1as`, without an external assembler wrapper. All four deliberately wrong index widths are
  rejected. The reassembled objects link with the stock SDK linker, and Node exits zero for wasm32, native wasm64,
  and UE-style `-m64 -sMEMORY64=2` final lowering.
- `../UE/FixedProbe/results.json`: all three pthread/WasmFS JS/native pointer+function-pointer roundtrips pass.
  C data/function pointers are 4/4 bytes for wasm32 and 8/8 bytes for both wasm64 modes. Actual final table and memory
  indices are 32/32, 64/64 and 32/32 respectively; lowering does not turn the C ABI back into a 32-bit ABI.
- `../UE/StockAssemblyProbe/assembly-results.json`: the stock compiler rejected the correct wasm64 i64 index while
  accepting a deliberately wrong i32 index. The fixed producer reverses those outcomes and retains wasm32 checks.

These accepted files are hashed by the producer manifest. Use a separate probe output directory and log prefix for
rechecks, so the accepted record remains reproducible. No complete CoreCLR native build, CoreCLR guest execution,
UnrealSharp browser runtime or UE Web game has been established by these standalone compiler checks.
