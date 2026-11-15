# CoreCLR wasm64 managed ABI work in progress

Dependency: `wasm64/target-foundation` at
`d016e0a6989` (the initial foundation plus its browser build invocation fix).
This is a draft dependent branch; neither the complete foundation gate nor the
managed ABI execution gate is claimed to have passed. Integration stays at the
upstream baseline until the relevant evidence is complete.

The first change implements the common managed calling-convention layout:

- The transition block contains a return address and saved stack pointer, as
  in native `vm/callingconvention.h`: size 8 for wasm32, 16 for wasm64.
- Both targets keep 8-byte interpreter argument slots. A wasm64 native-sized
  parameter is 8 bytes, while an explicit i32 parameter remains 4 bytes inside
  its slot. Aggregates preserve their size and their 8/16-byte alignment rules.
- The common iterator recognizes both architectures for argument placement,
  argument location descriptions and empty signatures with hidden parameters.

Six host tests exercise actual common iterator/transition sources using a
metadata-provider fixture. They cover mixed scalars/pointers/aggregates,
aggregate padding, byrefs and unnamed this/context/continuation slots for
each target. They require no native JIT library. The complete host type-system
suite passes 365 tests with zero failures/skips in Release.

This does not establish native transitions or guest execution. Signature keys,
generated helper declarations, string-constructor special cases, VM consumers,
saved CONTEXT/REGDISPLAY layouts, EH and suspended continuations remain to be
implemented and validated together. The wasm64 helper-emission and full-codegen
guards remain in place. Checked builds and native ABI/GC joint acceptance have
not run.
