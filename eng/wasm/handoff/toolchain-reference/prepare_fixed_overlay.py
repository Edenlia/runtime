"""Prepare a separately owned Emscripten LLVM_ROOT after the normal Clang build succeeds."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SDK = ROOT / "emsdk"
SOURCE = ROOT / "llvm-project"
BUILD = ROOT / "llvm-build"
OVERLAY = ROOT / "fixed-llvm"
PATCH = ROOT.parent / "UE" / "Analysis" / "8620eb7.patch"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    # The caller must establish successful exit of build-fixed-clang.cmd before running this script.
    clang = BUILD / "bin" / "clang.exe"
    mc = BUILD / "bin" / "llvm-mc.exe"
    for path in (clang, mc):
        if not path.is_file():
            raise RuntimeError("Build product missing: " + str(path))
    if OVERLAY.exists():
        raise RuntimeError("Overlay already exists; inspect its provenance instead of overwriting: " + str(OVERLAY))
    source_sha = subprocess.check_output(["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
    if source_sha != "a06d9165905ce89b5ffef2bbb84c886d60a9b8bf":
        raise RuntimeError("Unexpected LLVM source revision: " + source_sha)
    version = subprocess.check_output([str(clang), "--version"], text=True)
    (OVERLAY / "bin").mkdir(parents=True)
    records = []
    for original in sorted((SDK / "upstream" / "bin").glob("*.exe")):
        producer = clang if original.name in {"clang.exe", "clang++.exe"} else original
        destination = OVERLAY / "bin" / original.name
        shutil.copy2(producer, destination)
        records.append({"name": original.name, "producer": str(producer),
                        "sha256": sha(destination), "stock_sha256": sha(original),
                        "kind": "patched-normal-clang" if producer == clang else "stock-sdk"})
    shutil.copy2(mc, OVERLAY / "bin" / mc.name)
    records.append({"name": mc.name, "producer": str(mc), "sha256": sha(mc), "kind": "patched-llvm-mc"})
    # Keep the stock SDK's target headers/resource layout and preserve the original SDK bytes.
    resource_source = SDK / "upstream" / "lib" / "clang"
    shutil.copytree(resource_source, OVERLAY / "lib" / "clang")
    resource_records = [{"path": str(path.relative_to(resource_source)), "sha256": sha(path)}
                        for path in sorted(resource_source.rglob("*")) if path.is_file()]
    manifest = {"created_unix_s": time.time(), "source_sha": source_sha,
                "patch_commit": "8620eb7b55e857a5f6e430be624b5a6605e8c53e",
                "patch_sha256": sha(PATCH), "clang_version": version,
                "configuration": "Release; assertions ON; WebAssembly backend; MSVC19.51; Ninja; resumed with 2 workers",
                "build_command": str(ROOT / "build-fixed-clang.cmd"),
                "resume_command": str(ROOT / "resume-fixed-clang-shortpath.cmd"),
                "short_cwd_junction": str(ROOT.parents[6] / ".git" / "uw"),
                "source_diff": subprocess.check_output(["git", "-C", str(SOURCE), "diff"], text=True),
                "override": {"EM_LLVM_ROOT": str(OVERLAY / "bin")},
                "sdk_unchanged": str(SDK), "tools": records, "resource_headers": resource_records,
                "verification": "pending; run normal-driver assembler and ABI probes"}
    (OVERLAY / "provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"overlay": str(OVERLAY), "clang_version": version,
                      "tools": len(records), "resource_files": len(resource_records)}))


if __name__ == "__main__":
    main()
