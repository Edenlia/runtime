# JS-EH handoff reference snapshots

Start at [the branch handoff](../EDEN-WEB-HANDOFF.md) and
[the product profile](../README-coreclr-browser-js-eh.md).

guest-source/ contains the actual normal CMake host, C# probe and matching
HelperHost sources used by the four successful independent CLR guest lanes.
guest-global.json is the original SDK selection for that guest.
The guest requires a completed matching runtime/framework/link-kit product,
real complete generated helpers, and actual CMake File API profile metadata;
it is not a standalone emulator or a fake CLR.

reference-drivers/ preserves the original successful graph and guest drivers,
plus preparation/query/export scripts. These are historical source snapshots:
some derive paths from the original RuntimeHost/JsEh directory, other paths
are absolute to the original computer. Re-create that task layout in a cache
and adapt all tool/repo/input/output roots before execution. Rebuild and
record fresh evidence rather than copying historical receipts into a new run.

historical-evidence/ contains original small result JSON and the summary of the
actual 1e9f8bd1 build. Absolute paths, PIDs and file hashes identify the old run.
These are not portable binaries or proof that a new machine has run anything.
No full UE browser gameplay success is claimed.

toolchain-reference/ preserves the exact LLVM base/patch provenance, original
producer scripts and patch 8620eb7b55e857a5f6e430be624b5a6605e8c53e.
The old toolchain README's statements about runtime/UE work being pending
describe that earlier standalone compiler checkpoint; see the branch handoff
for the later runtime guest and UE link/cook success.
Do not apply the patch to runtime or replace the UE SDK compiler.
It belongs to a separate LLVM checkout at a06d9165905ce89b5ffef2bbb84c886d60a9b8bf.
Original producer scripts also contain machine paths and need review/adaptation.
The actual build used two workers after memory/path failures; do not replay old
short-path junction assumptions or overwrite occupied tools.

snapshot-inventory.json records original source locations and SHA256 of the
copies. No bin/obj, managed/native products, SDK, asset or cache is included.
The old .NET/runtime source pins remain truthful even after this documentation
commit changes HEAD. A new-source build needs its own new emitted stamp/product.
