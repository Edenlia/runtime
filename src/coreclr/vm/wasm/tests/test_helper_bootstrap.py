#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Exercise real portable helper generation; requires matching built framework inputs.

Build clr.callhelpers and clr+libs for the chosen target first. Optional explicit
paths allow comparison with an audited framework build without copying products.
No guest execution or new target support is established by these host tests.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[5]
PROJECT = REPOSITORY / "src/coreclr/vm/wasm/generate-coreclr-helpers.proj"
TABLES = {"callhelpers-pinvoke.cpp", "callhelpers-reverse.cpp", "callhelpers-interp-to-managed.cpp"}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--target-os", choices=("browser", "wasi"), default="browser")
parser.add_argument("--configuration", choices=("Release", "Checked", "Debug"), default="Release")
parser.add_argument("--dotnet")
parser.add_argument("--bootstrap")
parser.add_argument("--full-compiler")
parser.add_argument("--scan-path")
parser.add_argument("--evidence-dir")
OPTIONS, UNITTEST_ARGUMENTS = parser.parse_known_args()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HelperBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = OPTIONS.dotnet or os.environ.get("DOTNET_HOST_PATH")
        if not host:
            host = str(Path(os.environ.get("DOTNET_INSTALL_DIR", REPOSITORY / ".dotnet")) / "dotnet")
        cls.dotnet = str(Path(shutil.which(host) or host).resolve())
        if not Path(cls.dotnet).is_file():
            raise RuntimeError("Run eng/common/dotnet.sh first or set --dotnet to the repository SDK host.")
        cls.environment = os.environ.copy()
        cls.environment["DOTNET_HOST_PATH"] = str(Path(cls.dotnet).resolve())
        cls.command = [cls.dotnet, "msbuild", str(PROJECT), "-nologo", "-v:q",
                       f"-p:Configuration={OPTIONS.configuration}", f"-p:CallHelperTargetOS={OPTIONS.target_os}"]
        query = subprocess.run(
            [*cls.command, "-getProperty:ArtifactsBinDir,ArtifactsObjDir,BuildArchitecture", "-getItem:_WasmCallHelperTarget"],
            cwd=REPOSITORY, env=cls.environment, text=True, capture_output=True, check=True)
        metadata = json.loads(query.stdout)
        target = metadata["Items"]["_WasmCallHelperTarget"][0]
        cls.scan = Path(OPTIONS.scan_path or target["ScanPath"]).resolve()
        cls.response_file = Path(metadata["Properties"]["ArtifactsObjDir"]) / "wasm-callhelpers" / OPTIONS.target_os / "generate-coreclr-helpers.rsp"
        tool_root = Path(metadata["Properties"]["ArtifactsBinDir"]) / "coreclr" / f"{OPTIONS.target_os}.wasm.{OPTIONS.configuration}" / metadata["Properties"]["BuildArchitecture"]
        cls.bootstrap = Path(OPTIONS.bootstrap or tool_root / "crossgen2-callhelpers/crossgen2.dll").resolve()
        cls.full = Path(OPTIONS.full_compiler or tool_root / ("crossgen2/crossgen2.exe" if os.name == "nt" else "crossgen2/crossgen2")).resolve()
        for label, path in (("helper-only tool", cls.bootstrap), ("full compiler", cls.full), ("framework CoreLib", cls.scan / "System.Private.CoreLib.dll")):
            if not path.is_file():
                raise RuntimeError(f"Missing {label}: {path}; build the required products or provide the explicit path.")
        scratch = REPOSITORY / "artifacts/obj/helper-bootstrap-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(prefix="run-", dir=scratch)
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.work = Path(cls.scratch.name)
        cls.evidence = Path(OPTIONS.evidence_dir or REPOSITORY / "artifacts/log/helper-bootstrap-tests") / cls.work.name
        cls.evidence.mkdir(parents=True, exist_ok=True)
        cls.results = []
        cls.hashes = {}
        cls.addClassCleanup(cls.write_manifest)
        print(f"Helper bootstrap evidence: {cls.evidence}", flush=True)

    @classmethod
    def write_manifest(cls):
        manifest = {"target_os": OPTIONS.target_os, "configuration": OPTIONS.configuration,
                    "bootstrap": str(cls.bootstrap), "full_compiler": str(cls.full),
                    "scan_path": str(cls.scan), "input_sha256": {p.name: sha256(p) for p in sorted(cls.scan.glob("*.dll"))},
                    "bootstrap_sha256": sha256(cls.bootstrap), "tables": cls.hashes, "cases": cls.results,
                    "checked_in_comparison": OPTIONS.configuration == "Release",
                    "scope": "Real host generator and regeneration project tests; no guest execution."}
        (cls.evidence / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def run_command(self, name, command, cwd=REPOSITORY):
        result = subprocess.run(command, cwd=cwd, env=self.environment,
                                text=True, capture_output=True, check=False)
        (self.evidence / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        self.results.append({"name": name, "command": list(map(str, command)), "exit_code": result.returncode})
        return result

    def generate(self, name, compiler, extra=(), cwd=REPOSITORY):
        output = self.work / name
        result = self.run_command(name, [*self.command, "-t:GenerateCallHelpers",
            f"-p:CallHelperCompilerPath={compiler}", f"-p:CallHelperOutputRoot={output}",
            f"-p:{'BrowserScanPath' if OPTIONS.target_os == 'browser' else 'WasiScanPath'}={self.scan}", *extra], cwd=cwd)
        if result.returncode == 0:
            shutil.copy2(self.response_file, self.evidence / f"{name}.rsp")
        return result, output / OPTIONS.target_os

    def assert_tables(self, directory):
        self.assertEqual({p.name for p in directory.glob("*.cpp")}, TABLES)
        for name in TABLES:
            self.assertGreater((directory / name).stat().st_size, 0)

    def test_generator_matches_full_compiler(self):
        bootstrap, generated = self.generate("bootstrap", self.bootstrap)
        self.assertEqual(bootstrap.returncode, 0, bootstrap.stdout + bootstrap.stderr)
        full, expected = self.generate("full", self.full)
        self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
        self.assert_tables(generated)
        self.assert_tables(expected)
        for name in TABLES:
            checked_in = PROJECT.parent / OPTIONS.target_os / name
            self.assertTrue((generated / name).read_bytes() == (expected / name).read_bytes(),
                            f"{name}: helper-only output differs from full Crossgen2; see the generation logs.")
            if OPTIONS.configuration == "Release":
                self.assertTrue((generated / name).read_bytes() == checked_in.read_bytes(),
                                f"{name}: checked-in table is stale. Regenerate with generate-coreclr-helpers.sh "
                                f"-c Release --target-os {OPTIONS.target_os} and review the diff.")
            self.hashes[name] = sha256(generated / name)

    def test_compiler_and_output_paths_with_spaces(self):
        copied = self.work / "compiler with spaces"
        shutil.copytree(self.bootstrap.parent, copied)
        result, output = self.generate("output with spaces", copied / self.bootstrap.name)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_tables(output)

    def test_bootstrap_has_no_native_jit_dependencies(self):
        forbidden = [p.name for p in self.bootstrap.parent.iterdir()
                     if p.name.lower().startswith(("clrjit", "libclrjit", "jitinterface", "libjitinterface"))]
        self.assertEqual(forbidden, [])

    def test_relative_compiler_path_uses_repository_root(self):
        copied = self.work / "relative-tool"
        shutil.copytree(self.bootstrap.parent, copied)
        result, output = self.generate("relative-compiler", (copied / self.bootstrap.name).relative_to(REPOSITORY), cwd=self.work)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_tables(output)

    def test_non_helper_compilation_is_rejected(self):
        output = self.work / "unexpected-r2r.dll"
        result = self.run_command("reject-compilation", [self.dotnet, str(self.bootstrap),
            f"--targetos:{OPTIONS.target_os}", "--targetarch:wasm", f"--out:{output}", str(self.scan / "System.Private.CoreLib.dll")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only supports --generate-portable-callhelpers", result.stdout + result.stderr)
        self.assertFalse(output.exists())

    def test_invalid_target_is_rejected(self):
        output = self.work / "invalid-target"
        result = self.run_command("reject-target", [self.dotnet, str(self.bootstrap), "--targetos:browser",
            "--targetarch:x64", f"--generate-portable-callhelpers:{output}", str(self.scan / "System.Private.CoreLib.dll")])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --targetarch wasm", result.stdout + result.stderr)
        self.assertFalse(any(output.glob("*.cpp")))

    def test_missing_compiler_is_rejected(self):
        result, output = self.generate("missing-compiler", self.work / "missing.dll")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CallHelperCompilerPath does not exist", result.stdout + result.stderr)
        self.assertFalse(any(output.glob("*.cpp")))

    def test_missing_dotnet_host_is_rejected(self):
        result, output = self.generate("missing-host", self.bootstrap, ["-p:DOTNET_HOST_PATH=", "-p:DotNetTool="])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".NET host", result.stdout + result.stderr)
        self.assertFalse(any(output.glob("*.cpp")))

    def test_empty_framework_input_is_rejected(self):
        empty = self.work / "empty"
        empty.mkdir()
        result, output = self.generate("empty-input", self.bootstrap,
            [f"-p:{'BrowserScanPath' if OPTIONS.target_os == 'browser' else 'WasiScanPath'}={empty}"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No assemblies to scan", result.stdout + result.stderr)
        self.assertFalse(any(output.glob("*.cpp")))

    def test_missing_host_path_is_rejected(self):
        result, output = self.generate("missing-host-path", self.bootstrap,
            [f"-p:DOTNET_HOST_PATH={self.work / 'missing dotnet'}"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".NET host for the crossgen2 DLL does not exist", result.stdout + result.stderr)
        self.assertFalse(any(output.glob("*.cpp")))


if __name__ == "__main__":
    unittest.main(argv=[__file__, *UNITTEST_ARGUMENTS])
