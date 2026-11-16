#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Inspect explicit Memory64 native products. This never instantiates or executes a guest."""

import argparse
from collections import Counter
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


_ICU_SPEC = importlib.util.spec_from_file_location(
    "memory64_icu", Path(__file__).resolve().parents[1] / "build-memory64-icu.py")
ICU = importlib.util.module_from_spec(_ICU_SPEC)
_ICU_SPEC.loader.exec_module(ICU)


class Blocked(RuntimeError):
    """A required inspection tool is unavailable; no successful check can be claimed."""


def require_file(path):
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Missing or empty product: {path}")
    return path


def command_output(command, *, cwd=None, env=None, text=True):
    result = subprocess.run(list(map(str, command)), cwd=cwd, env=env,
                            text=text, capture_output=True, check=False)
    if result.returncode != 0:
        error = result.stderr if text else result.stderr.decode(errors="replace")
        raise RuntimeError(f"Inspection command failed ({result.returncode}): {command}\n{error}")
    return result.stdout


def llvm_major(version):
    match = re.search(r"(?:clang|LLVM) version\s+(\d+)", version)
    if not match:
        raise RuntimeError(f"Cannot identify LLVM version: {version}")
    return int(match.group(1))


def tool_identity(path):
    path = require_file(path)
    return {"path": str(path), "sha256": ICU.sha256(path),
            "version": command_output([path, "--version"]).strip()}


def valid_sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def verify_file_record(record, directory, label):
    if (not isinstance(record, dict) or not isinstance(record.get("path"), str) or
            not record["path"] or not valid_sha256(record.get("sha256"))):
        raise RuntimeError(f"{label}: expected a producer path and SHA256.")
    path = Path(record["path"])
    path = require_file(path if path.is_absolute() else directory / path)
    if ICU.sha256(path) != record["sha256"]:
        raise RuntimeError(f"{label}: producer file SHA256 changed: {path}")
    return {"path": str(path), "sha256": record["sha256"]}


def verify_toolchain_evidence(path, lane):
    path = require_file(path)
    record = json.loads(path.read_text())
    if not isinstance(record, dict):
        raise RuntimeError(f"{path}: producer evidence must be a JSON object.")
    if lane == "patched":
        if (record.get("build_lane") != "patched" or
                not isinstance(record.get("source_revision"), str) or
                re.fullmatch(r"[0-9a-f]{40}", record["source_revision"]) is None or
                not isinstance(record.get("source_repo"), str) or not record["source_repo"] or
                not isinstance(record.get("command"), list) or not record["command"] or
                not all(isinstance(item, str) and item for item in record["command"])):
            raise RuntimeError(f"{path}: patched evidence needs build_lane, source_repo, full source_revision and command.")
        if record.get("build_status") != "success":
            raise RuntimeError(f"{path}: producer does not record a successful patched build (build_status=success required).")
        source = Path(record["source_repo"])
        source = (source if source.is_absolute() else path.parent / source).resolve()
        if command_output(["git", "-C", source, "rev-parse", "HEAD"]).strip() != record["source_revision"]:
            raise RuntimeError(f"{path}: patched source revision does not match its source checkout.")
        verify_file_record(record.get("patch"), path.parent, "toolchain patch")
        tools = record.get("tools")
        if not isinstance(tools, dict) or not {"compiler", "assembler"}.issubset(tools):
            raise RuntimeError(f"{path}: patched evidence needs compiler and assembler producer records.")
        for name, tool in tools.items():
            verify_file_record(tool, path.parent, "producer " + name)
    elif record.get("build_lane") == "patched":
        raise RuntimeError(f"{path}: patched producer evidence cannot be labelled as a stock build.")
    return {"path": str(path), "sha256": ICU.sha256(path), "record": record}


def bitcode_layout(path, llvm_dis, clang_major):
    if llvm_dis is None:
        raise Blocked(f"{path}: LLVM bitcode needs --llvm-dis from the selected SDK's LLVM version. "
                      "Clang IR re-emission rewrites the target triple/layout and is not a valid check.")
    if llvm_major(command_output([llvm_dis, "--version"])) != clang_major:
        raise Blocked(f"{llvm_dis}: llvm-dis must match the selected SDK's LLVM major {clang_major}.")
    ir = command_output([llvm_dis, path, "-o", "-"])
    triple_match = re.search(r'^target triple = "([^"]+)"$', ir, re.MULTILINE)
    layout_match = re.search(r'^target datalayout = "([^"]+)"$', ir, re.MULTILINE)
    if not triple_match or not layout_match:
        raise RuntimeError(f"{path}: bitcode must identify its original target triple and data layout.")
    triple, layout = triple_match.group(1), layout_match.group(1)
    pointers = [field.split(":") for field in layout.split("-")
                if field.startswith("p:") or field.startswith("p0:")]
    if not triple.startswith("wasm64-") or not layout.startswith("e-") or len(pointers) != 1:
        raise RuntimeError(f"{path}: expected wasm64 bitcode, found triple={triple}, layout={layout}")
    pointer = pointers[0]
    index_size = pointer[4] if len(pointer) > 4 else pointer[1]
    if len(pointer) < 3 or pointer[1:3] != ["64", "64"] or index_size != "64":
        raise RuntimeError(f"{path}: wasm64 bitcode has an incompatible pointer data layout: {layout}")
    return {"triple": triple, "data_layout": layout}


def verify_archive(path, sdk, *, llvm_dis=None, clang_major=None):
    """Use LLVM's archive reader, including its duplicate-member selector, instead of parsing ar."""
    path = require_file(path)
    with path.open("rb") as stream:
        magic = stream.read(8)
    if magic != b"!<arch>\n":
        raise RuntimeError(f"{path}: expected a self-contained archive; thin/external-member archives are not products.")
    ar = ICU.sdk_tool(sdk, "llvm-ar")
    names = command_output([ar, "t", path]).splitlines()
    if not names:
        raise RuntimeError(f"{path}: archive contains no object members.")
    for name in names:
        if (name in (".", "..") or Path(name).name != name or "/" in name or "\\" in name or
                not name or any(ord(character) < 32 for character in name)):
            raise RuntimeError(f"{path}: unsupported archive member path: {name!r}")
    counts = Counter(names)
    seen = Counter()
    kinds = Counter()
    layouts = set()
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="memory64-archive-") as temporary:
        root = Path(temporary)
        # LLVM handles GNU/BSD long names and symbol tables. Duplicate members are extracted
        # by occurrence so a good member cannot hide an earlier member with the same name.
        command_output([ar, "x", path], cwd=root)
        for name in names:
            seen[name] += 1
            member = root / name
            if counts[name] > 1:
                occurrence = root / ("member-" + str(sum(seen.values())))
                occurrence.mkdir()
                command_output([ar, "xN", seen[name], path, name], cwd=occurrence)
                member = occurrence / name
            if member.is_symlink():
                raise RuntimeError(f"{path}: extracted member is a link: {name}")
            require_file(member)
            with member.open("rb") as stream:
                member_magic = stream.read(4)
            if member_magic == b"\0asm":
                headers = command_output([ICU.sdk_tool(sdk, "llvm-readobj"), "--file-header", member])
                formats = re.findall(r"^Format:\s*(\S+)\s*$", headers, re.MULTILINE)
                arches = re.findall(r"^Arch:\s*(\S+)\s*$", headers, re.MULTILINE)
                if formats != ["WASM"] or arches != ["wasm64"]:
                    raise RuntimeError(f"{path}({name}#{seen[name]}): expected wasm64 object, found {arches or formats}.")
                try:
                    wasm_linking_version(member)
                except RuntimeError as error:
                    raise RuntimeError(f"{path}({name}#{seen[name]}): {error}") from error
                kinds["wasm64_objects"] += 1
            elif member_magic in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
                if clang_major is None:
                    clang_major = llvm_major(command_output([ICU.sdk_tool(sdk, "clang"), "--version"]))
                try:
                    layout = bitcode_layout(member, llvm_dis, clang_major)
                except RuntimeError as error:
                    raise type(error)(f"{path}({name}#{seen[name]}): {error}") from error
                layouts.add((layout["triple"], layout["data_layout"]))
                kinds["wasm64_bitcode"] += 1
            else:
                raise RuntimeError(f"{path}({name}#{seen[name]}): member is neither a Wasm64 object nor LLVM bitcode.")
            digest.update(f"{name}#{seen[name]}:{ICU.sha256(member)}\n".encode())
    return {"path": str(path), "sha256": ICU.sha256(path), "bytes": path.stat().st_size,
            "members": len(names), "member_types": dict(kinds), "member_digest_sha256": digest.hexdigest(),
            "bitcode_layouts": [{"triple": triple, "data_layout": layout} for triple, layout in sorted(layouts)]}


class WasmReader:
    def __init__(self, data):
        self.data, self.position = data, 0

    def take(self, size):
        if size < 0 or size > len(self.data) - self.position:
            raise RuntimeError("Truncated Wasm section.")
        start = self.position
        self.position += size
        return self.data[start:self.position]

    def byte(self):
        return self.take(1)[0]

    def uleb(self, bits=32):
        value = 0
        for shift in range(0, bits, 7):
            byte = self.byte()
            value |= (byte & 127) << shift
            if byte & 128 == 0:
                if value >= 1 << bits:
                    break
                return value
        raise RuntimeError("Invalid or overflowing Wasm integer.")

    def name(self):
        return self.take(self.uleb()).decode("utf-8")

    def reference_type(self):
        kind = self.byte()
        if kind in (0x63, 0x64):  # ref null / ref followed by a signed heap type
            for _ in range(5):
                if self.byte() & 128 == 0:
                    return
            raise RuntimeError("Invalid Wasm heap type.")
        if kind not in range(0x68, 0x74):
            raise RuntimeError(f"Unsupported Wasm reference type: {kind:#x}")

    def limits(self):
        flags = self.uleb()
        if flags & ~7:
            raise RuntimeError(f"Unsupported Wasm limits flags: {flags:#x}")
        address_bits = 64 if flags & 4 else 32
        minimum = self.uleb(address_bits)
        maximum = self.uleb(address_bits) if flags & 1 else None
        return {"address_bits": address_bits, "minimum": minimum, "maximum": maximum,
                "shared": bool(flags & 2)}


def wasm_sections(path):
    module = WasmReader(require_file(path).read_bytes())
    if module.take(8) != b"\0asm\x01\0\0\0":
        raise RuntimeError(f"{path}: expected an ordinary Wasm core module.")
    while module.position < len(module.data):
        section_id = module.byte()
        yield section_id, WasmReader(module.take(module.uleb()))


def wasm_linking_version(path):
    versions = []
    for section_id, section in wasm_sections(path):
        if section_id == 0 and section.name() == "linking":
            versions.append(section.uleb())
    if versions != [2]:
        raise RuntimeError(f"{path}: expected relocatable Wasm linking metadata version 2; a final module is not an archive object.")
    return versions[0]


def module_address_types(path):
    memories, tables = [], []
    for section_id, section in wasm_sections(path):
        if section_id == 2:
            for _ in range(section.uleb()):
                module_name, field_name, kind = section.name(), section.name(), section.byte()
                if kind == 0:  # function type index
                    section.uleb()
                elif kind == 1:
                    section.reference_type()
                    tables.append({**section.limits(), "import": f"{module_name}.{field_name}"})
                elif kind == 2:
                    memories.append({**section.limits(), "import": f"{module_name}.{field_name}"})
                elif kind == 3:
                    if section.data[section.position] in (0x63, 0x64):
                        section.reference_type()
                    else:
                        section.byte()
                    section.byte()  # mutability; Node and wasm-opt validate its value
                elif kind == 4:  # exception tag
                    section.uleb()
                    section.uleb()
                else:
                    raise RuntimeError(f"Unsupported Wasm import kind: {kind}")
        elif section_id == 4:
            for _ in range(section.uleb()):
                section.reference_type()
                tables.append(section.limits())
        elif section_id == 5:
            for _ in range(section.uleb()):
                memories.append(section.limits())
        else:
            continue
        if section.position != len(section.data):
            raise RuntimeError(f"{path}: unsupported content in Wasm section {section_id}.")
    if not memories or not tables or any(item["address_bits"] != 64 for item in memories + tables):
        raise RuntimeError(f"{path}: expected Memory64 and table64; found memories={memories}, tables={tables}")
    return {"memories": memories, "tables": tables}


def verify_module(path, sdk, node, node_arguments):
    path = require_file(path)
    widths = module_address_types(path)
    node = require_file(node)
    # Feature flags only: prevent an eval/require option from replacing this validation program.
    allowed = {"--experimental-wasm-memory64", "--experimental-wasm-exnref", "--wasm-staging"}
    if any(argument not in allowed for argument in node_arguments):
        raise RuntimeError(f"Unsupported Node validation flags: {node_arguments}; allowed: {sorted(allowed)}")
    environment = os.environ.copy()
    environment.pop("NODE_OPTIONS", None)
    environment["BINARYEN_CORES"] = "1"
    source = '''import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
const bytes = readFileSync(process.argv[1]);
const module = new WebAssembly.Module(bytes);
console.log(JSON.stringify({ status: 'PASS', sha256: createHash('sha256').update(bytes).digest('hex'),
    imports: WebAssembly.Module.imports(module).length, exports: WebAssembly.Module.exports(module).length }));'''
    node_command = [node, *node_arguments, "--input-type=module", "-e", source, path]
    validated = json.loads(command_output(node_command, env=environment))
    if validated.get("status") != "PASS" or validated.get("sha256") != ICU.sha256(path):
        raise RuntimeError("Node did not confirm validation of the selected module.")
    with tempfile.TemporaryDirectory(prefix="memory64-wasm-opt-") as temporary:
        optimized = Path(temporary) / "validated.wasm"
        opt_command = [ICU.sdk_tool(sdk, "wasm-opt"), path, "--all-features", "--vacuum", "-o", optimized]
        command_output(opt_command, env=environment)
        module_address_types(optimized)
    return {"path": str(path), "sha256": ICU.sha256(path), **widths,
            "node": {"path": str(node), "version": command_output([node, "--version"], env=environment).strip(),
                     "sha256": ICU.sha256(node),
                     "flags": node_arguments, "validation": validated},
            "wasm_opt": {"command": list(map(str, opt_command)), "status": "PASS"},
            "guest_instantiated": False, "guest_executed": False}


def verify_kit(directory, sdk, *, llvm_dis=None, clang_major=None):
    directory = Path(directory).resolve()
    marker = require_file(directory / "target-architecture.txt")
    if marker.read_text().splitlines() != ["wasm64"]:
        raise RuntimeError(f"{marker}: native relink kit does not target wasm64.")
    for name in ("corerun-link.rsp", "corerun-compile.rsp", "corerun-compile-user.rsp"):
        response = require_file(directory / name)
        tokens = shlex.split(response.read_text())
        if "-m64" not in tokens or "-m32" in tokens:
            raise RuntimeError(f"{response}: expected consistent -m64 target flags.")
        if name == "corerun-compile.rsp":
            required = {"-DTARGET_WASM", "-DTARGET_WASM64", "-DTARGET_64BIT", "-DTARGET_POINTER_SIZE=8"}
            if not required.issubset(tokens) or {"-DTARGET_WASM32", "-DTARGET_32BIT"}.intersection(tokens):
                raise RuntimeError(f"{response}: generated helper layout does not target wasm64.")
    archives = sorted(directory.glob("*.a"))
    if not archives:
        raise RuntimeError(f"{directory}: the native relink kit contains no archives.")
    if not (directory / "libcorerun_static.a").is_file():
        raise RuntimeError(f"{directory}: the native relink kit is missing libcorerun_static.a.")
    return {"path": str(directory), "architecture": "wasm64",
            "archives": [verify_archive(path, sdk, llvm_dis=llvm_dis, clang_major=clang_major) for path in archives]}


def verify_runtime_kit_copies(runtime_archives, kit):
    kit_hashes = {Path(item["path"]).name: item["sha256"] for item in kit["archives"]}
    for item in runtime_archives:
        name = Path(item["path"]).name
        if name == "libcoreclr_gen_static.a":
            continue  # Per-test generated tables deliberately replace this product archive.
        if name not in kit_hashes:
            raise RuntimeError(f"{name}: the native relink kit is missing the selected runtime archive copy.")
        if kit_hashes[name] != item["sha256"]:
            raise RuntimeError(f"{name}: the relink kit and explicit runtime product differ.")
    return kit_hashes


def verify_icu_manifest(directory, sdk):
    ICU.check_runtime_pin(Path(__file__).resolve().parents[3])
    directory = Path(directory).resolve()
    manifest_path = require_file(directory / "icu-memory64.json")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict):
        raise RuntimeError(f"{manifest_path}: ICU producer manifest must be a JSON object.")
    if (manifest.get("target") != "browser-wasm64" or manifest.get("pointer_size") != 8 or
            manifest.get("icu_commit") != ICU.ICU_COMMIT or manifest.get("icu_version") != ICU.ICU_VERSION or
            manifest.get("source_archive_sha256") != ICU.ICU_ARCHIVE_SHA256):
        raise RuntimeError(f"{manifest_path}: ICU manifest does not match the runtime-pinned Memory64 dependency.")
    if (type(manifest.get("recipe_version")) is not int or manifest["recipe_version"] != ICU.RECIPE_VERSION or
            not isinstance(manifest.get("emcc_version"), str) or not manifest["emcc_version"].strip() or
            not valid_sha256(manifest.get("clang_sha256")) or not valid_sha256(manifest.get("wasm_ld_sha256")) or
            not isinstance(manifest.get("emsdk_path"), str) or not manifest["emsdk_path"] or
            not isinstance(manifest.get("command"), list) or not manifest["command"] or
            not all(isinstance(item, str) and item for item in manifest["command"])):
        raise RuntimeError(f"{manifest_path}: incomplete ICU producer identity, tool hashes or build command.")
    probe = manifest.get("link_probe")
    if (not isinstance(probe, dict) or probe.get("status") != "PASS" or
            not isinstance(probe.get("stdout"), str) or
            "Memory64 archive probe PASS; pointer=8" not in probe["stdout"]):
        raise RuntimeError(f"{manifest_path}: missing successful producer Memory64 ICU probe record.")
    with contextlib.redirect_stdout(io.StringIO()):
        files = ICU.verify_icu(directory, sdk)
    if files != manifest.get("files"):
        raise RuntimeError(f"{manifest_path}: ICU archive/data hashes or member counts changed.")
    identity_keys = ("icu_commit", "icu_version", "source_archive_sha256", "recipe_version",
                     "pointer_size", "emcc_version", "clang_sha256", "wasm_ld_sha256")
    identity = {key: manifest.get(key) for key in identity_keys}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    if manifest.get("fingerprint") != fingerprint:
        raise RuntimeError(f"{manifest_path}: ICU producer fingerprint is inconsistent.")
    return {"path": str(directory), "manifest_sha256": ICU.sha256(manifest_path),
            "producer": identity, "fingerprint": fingerprint, "files": files,
            "producer_probe_record": manifest.get("link_probe"),
            "probe_executed_by_this_check": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-archive", type=Path, action="append", required=True)
    parser.add_argument("--native-library", type=Path, action="append", required=True)
    parser.add_argument("--corerun", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--icu", type=Path, required=True)
    parser.add_argument("--emsdk", type=Path, required=True)
    parser.add_argument("--llvm-dis", type=Path)
    parser.add_argument("--node", type=Path)
    parser.add_argument("--node-arg", action="append", default=[])
    parser.add_argument("--build-lane", choices=("stock", "patched"), required=True)
    parser.add_argument("--toolchain-evidence", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    options = parser.parse_args()
    report = {"status": "FAIL", "build_lane": options.build_lane,
              "command": [sys.executable, *sys.argv],
              "inspector": {"path": str(Path(__file__).resolve()), "sha256": ICU.sha256(Path(__file__))},
              "scope": "native product architecture and module validation; no guest instantiation or execution"}
    try:
        sdk = options.emsdk.resolve()
        if options.build_lane == "patched" and options.toolchain_evidence is None:
            raise RuntimeError("The patched build lane requires --toolchain-evidence; it cannot count as stock-toolchain acceptance.")
        if options.toolchain_evidence is not None:
            report["toolchain_evidence"] = verify_toolchain_evidence(options.toolchain_evidence, options.build_lane)
        report["inspection_tools"] = {name: tool_identity(ICU.sdk_tool(sdk, name))
                                      for name in ("clang", "llvm-ar", "llvm-readobj", "wasm-opt", "wasm-ld")}
        major = llvm_major(report["inspection_tools"]["clang"]["version"])
        clang_binary = sdk / "bin" / f"clang-{major}"
        if clang_binary.is_file():
            report["inspection_tools"]["clang_binary"] = tool_identity(clang_binary)
        llvm_dis = options.llvm_dis or (sdk / "bin/llvm-dis" if (sdk / "bin/llvm-dis").is_file() else None)
        if llvm_dis is not None:
            llvm_dis = require_file(llvm_dis)
            report["inspection_tools"]["llvm-dis"] = tool_identity(llvm_dis)
        report["runtime_archives"] = [verify_archive(path, sdk, llvm_dis=llvm_dis, clang_major=major)
                                      for path in options.runtime_archive]
        report["native_libraries"] = [verify_archive(path, sdk, llvm_dis=llvm_dis, clang_major=major)
                                      for path in options.native_library]
        report["kit"] = verify_kit(options.kit, sdk, llvm_dis=llvm_dis, clang_major=major)
        # The kit copies runtime archives. Native libraries also have a separate published build,
        # whose object/debug information may differ from corerun's side-build of the same sources.
        kit_hashes = verify_runtime_kit_copies(report["runtime_archives"], report["kit"])
        report["icu"] = verify_icu_manifest(options.icu, sdk)
        for name in ICU.ARCHIVES:
            if kit_hashes.get(name) != report["icu"]["files"][name]["sha256"]:
                raise RuntimeError(f"{name}: the native relink kit does not contain the selected verified ICU archive.")
        node = options.node or (sdk / "node/bin/node" if (sdk / "node/bin/node").is_file() else sdk / "bin/node")
        report["module"] = verify_module(options.corerun, sdk, node, options.node_arg)
        report["status"] = "PASS"
    except Blocked as error:
        report.update(status="BLOCKED", error=str(error))
    except (OSError, RuntimeError, ValueError, IndexError, subprocess.CalledProcessError) as error:
        report.update(status="FAIL", error=str(error))
    options.report.parent.mkdir(parents=True, exist_ok=True)
    options.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2 if report["status"] == "BLOCKED" else 1


if __name__ == "__main__":
    sys.exit(main())
