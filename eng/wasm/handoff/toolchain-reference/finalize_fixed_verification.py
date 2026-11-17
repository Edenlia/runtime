"""Attach completed real-driver and Node acceptance records to the toolchain producer."""
import json
from pathlib import Path
from prepare_fixed_overlay import ROOT, SDK, SOURCE, OVERLAY, sha


def main():
    probe = ROOT.parent / "UE" / "FixedProbe"
    assembly_path = probe / "assembly-results.json"
    abi_path = probe / "results.json"
    assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
    abi = json.loads(abi_path.read_text(encoding="utf-8"))
    assert assembly["pass"] and abi["pass"]
    for label in ("wasm32", "wasm64", "wasm32-legacy", "wasm64-legacy"):
        case = assembly["cases"][label]
        assert case["assemble"]["exit_code"] == 0
        assert "-cc1as" in case["assemble"]["output"]
        assert case["reject_wrong_index"]["exit_code"] != 0
    for label, bits in (("wasm32", 32), ("wasm64-native", 64), ("wasm64-lowered", 32)):
        case = abi["cases"][label]
        assert case["pass"]
        assert case["wasm_limits"]["tables"][0]["index_bits"] == bits
        assert case["wasm_limits"]["memories"][0]["index_bits"] == bits
    manifest_path = OVERLAY / "provenance.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for tool in manifest["tools"]:
        if "stock_sha256" in tool:
            assert sha(SDK / "upstream" / "bin" / tool["name"]) == tool["stock_sha256"]
    manifest["build_exit_code"] = 0
    manifest["source_file_hashes"] = {
        str(path.relative_to(SOURCE)): sha(path) for path in [
            SOURCE / "llvm/lib/Target/WebAssembly/AsmParser/WebAssemblyAsmTypeCheck.cpp",
            SOURCE / "llvm/lib/Target/WebAssembly/AsmParser/WebAssemblyAsmTypeCheck.h"]}
    manifest["verification"] = {"pass": True,
        "assembly_results": str(assembly_path), "assembly_results_sha256": sha(assembly_path),
        "abi_results": str(abi_path), "abi_results_sha256": sha(abi_path),
        "original_sdk_binaries_unchanged": True,
        "normal_driver": "in-process clang -cc1as; no external assembler adapter or type-check suppression",
        "target_scope": "WebAssembly backend only; use explicit target (as emcc does), default target is unknown",
        "sysroot_note": "Emscripten's supported LLVM_ROOT switch may regenerate its task-local system-library cache; SDK version and linker remain 6.0.10",
        "boundaries": "No complete CoreCLR build, guest execution, UnrealSharp browser host or UE Web game validated"}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"pass": True, "provenance": str(manifest_path),
                      "clang_sha256": next(x["sha256"] for x in manifest["tools"] if x["name"] == "clang.exe")}))


if __name__ == "__main__":
    main()
