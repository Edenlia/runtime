#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Exercise the real call-helper MSBuild entry point, without substituting a compiler.

The default suite checks rejected target selections before any generation. Add
--full-generation after building the ordinary wasm host crossgen2 and both complete
framework closures to check actual output and architecture isolation. Missing build
inputs fail that suite. Generated tables and invocation logs stay under --evidence-dir.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[3]
PROJECT = REPO / "src/coreclr/vm/wasm/generate-coreclr-helpers.proj"
NAMES = ("callhelpers-pinvoke.cpp", "callhelpers-reverse.cpp", "callhelpers-interp-to-managed.cpp")
OPTIONS = None


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CallHelperTests(unittest.TestCase):
    def invoke(self, properties, expected_error=None, invocation="msbuild"):
        directory = OPTIONS.evidence_dir / self.id().split(".")[-1]
        directory.mkdir(parents=True, exist_ok=True)
        command = [str(OPTIONS.dotnet), "msbuild", str(PROJECT), "-nologo", "-t:GenerateCallHelpers",
                   f"-p:Configuration={OPTIONS.configuration}",
                   f"-p:ArtifactsObjDir={OPTIONS.evidence_dir / 'obj'}/",
                   f"-p:CallHelperOutputRoot={directory / 'output'}"]
        command.extend(f"-p:{key}={value}" for key, value in properties.items())
        result = subprocess.run(command, cwd=REPO, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        (directory / f"{invocation}-command.json").write_text(json.dumps(command, indent=2) + "\n")
        (directory / f"{invocation}.log").write_text(result.stdout)
        if expected_error is None:
            self.assertEqual(0, result.returncode, result.stdout)
        else:
            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn(expected_error, result.stdout)
        return directory

    def ordinary_compiler_dll(self):
        path = OPTIONS.compiler
        if path is None:
            path = REPO / "artifacts/bin/coreclr" / f"browser.wasm.{OPTIONS.configuration}" / "crossgen2/crossgen2.dll"
        self.assertTrue(path.is_file(), f"Build the ordinary crossgen2.csproj DLL first, or select it with --compiler: {path}")
        self.assertEqual(".dll", path.suffix.lower(), "Use the ordinary crossgen2 DLL for host validation tests.")
        return path

    def closure(self, architecture):
        path = OPTIONS.scan32 if architecture == "wasm" else OPTIONS.scan64
        if path is None:
            path = REPO / "artifacts/bin/testhost" / f"net12.0-browser-{OPTIONS.configuration}-{architecture}" / "shared/Microsoft.NETCore.App/12.0.0"
        # A CoreLib-only directory is insufficient for framework table acceptance.
        for name in ("System.Private.CoreLib.dll", "System.Runtime.dll", "System.Collections.dll"):
            self.assertTrue((path / name).is_file(), f"Build the complete {architecture} framework closure: missing {path / name}")
        matching_corelib = REPO / "artifacts/bin/coreclr" / f"browser.{architecture}.{OPTIONS.configuration}" / "IL/System.Private.CoreLib.dll"
        self.assertTrue(matching_corelib.is_file(), f"Build the matching {architecture} CoreLib product: {matching_corelib}")
        self.assertEqual(sha256(matching_corelib), sha256(path / "System.Private.CoreLib.dll"),
                         f"Framework closure must contain the actual matching CoreLib product: {matching_corelib}")
        manifest = {file.name: sha256(file) for file in sorted(path.glob("*.dll"))}
        (OPTIONS.evidence_dir / f"inputs-{architecture}.json").write_text(
            json.dumps({"source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                        "path": str(path), "assemblies": manifest}, indent=2) + "\n")
        return path


class TargetValidationTests(CallHelperTests):
    def evaluate_targets(self, properties, label):
        directory = OPTIONS.evidence_dir / self.id().split(".")[-1]
        directory.mkdir(parents=True, exist_ok=True)
        command = [str(OPTIONS.dotnet), "msbuild", str(PROJECT), "-nologo", "-v:q",
                   "-t:_ValidateCallHelperTargetOS", "-getItem:_WasmCallHelperTarget",
                   "-getProperty:CallHelperTargetArchitecture,CallHelperTargetOS,NetCoreAppCurrent,_FrameworkVersion"]
        command.extend(f"-p:{key}={value}" for key, value in properties.items())
        result = subprocess.run(command, cwd=REPO, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        (directory / f"{label}-command.json").write_text(json.dumps(command, indent=2) + "\n")
        (directory / f"{label}.log").write_text(result.stdout)
        self.assertEqual(0, result.returncode, result.stdout)
        return json.loads(result.stdout)

    def test_default_width_preserves_both_framework_scan_paths(self):
        actual = self.evaluate_targets({"Configuration": "Release"}, "default")
        properties = actual["Properties"]
        self.assertEqual("wasm", properties["CallHelperTargetArchitecture"])
        self.assertEqual("", properties["CallHelperTargetOS"])
        targets = actual["Items"]["_WasmCallHelperTarget"]
        self.assertEqual(["browser", "wasi"], [item["Identity"] for item in targets])
        for item in targets:
            expected = REPO / "artifacts/bin/testhost" / f"{properties['NetCoreAppCurrent']}-{item['Identity']}-Release-wasm" / "shared/Microsoft.NETCore.App" / properties["_FrameworkVersion"]
            self.assertEqual(expected, Path(item["ScanPath"]))

    def test_memory64_defaults_to_matching_browser_framework(self):
        for configuration in ("Release", "Checked"):
            with self.subTest(configuration=configuration):
                actual = self.evaluate_targets({"Configuration": configuration,
                                                "CallHelperTargetArchitecture": "wasm64"}, configuration)
                properties = actual["Properties"]
                self.assertEqual("wasm64", properties["CallHelperTargetArchitecture"])
                self.assertEqual("browser", properties["CallHelperTargetOS"])
                targets = actual["Items"]["_WasmCallHelperTarget"]
                self.assertEqual(["browser"], [item["Identity"] for item in targets])
                expected = REPO / "artifacts/bin/testhost" / f"{properties['NetCoreAppCurrent']}-browser-{configuration}-wasm64" / "shared/Microsoft.NETCore.App" / properties["_FrameworkVersion"]
                self.assertEqual(expected, Path(targets[0]["ScanPath"]))

    def test_unknown_architecture_is_rejected(self):
        self.invoke({"CallHelperTargetArchitecture": "x64"}, "Unknown CallHelperTargetArchitecture 'x64'")

    def test_memory64_wasi_is_rejected(self):
        self.invoke({"CallHelperTargetArchitecture": "wasm64", "CallHelperTargetOS": "wasi"},
                    "wasm64 call helpers currently support only CallHelperTargetOS=browser")

    def test_unknown_os_is_rejected(self):
        self.invoke({"CallHelperTargetOS": "linux"}, "Unknown CallHelperTargetOS 'linux'")

    def test_missing_compiler_override_does_not_fall_back(self):
        path = OPTIONS.evidence_dir / "missing-crossgen2.dll"
        self.assertFalse(path.exists())
        self.invoke({"CallHelperTargetArchitecture": "wasm64", "CallHelperCompilerPath": path},
                    "CallHelperCompilerPath does not exist:")

    def test_shell_rejects_invalid_width_and_missing_values(self):
        script = PROJECT.with_suffix(".cmd" if sys.platform == "win32" else ".sh")
        command = ["cmd", "/d", "/c", str(script)] if sys.platform == "win32" else ["bash", str(script)]
        for arguments, expected in ((["--arch", "x64"], "Invalid architecture"),
                                    (["--arch", "wasm64", "--target-os", "wasi"], "support only --target-os browser"),
                                    (["--arch"], "Missing value for --arch"),
                                    (["--compiler-path"], "Missing value for --compiler-path"),
                                    (["--output-root"], "Missing value for --output-root")):
            with self.subTest(arguments=arguments):
                result = subprocess.run([*command, *arguments], cwd=REPO, text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertNotEqual(0, result.returncode, result.stdout)
                self.assertIn(expected, result.stdout)


class CompilerValidationTests(CallHelperTests):
    def test_dll_without_a_host_is_rejected(self):
        self.invoke({"CallHelperTargetArchitecture": "wasm64", "CallHelperCompilerPath": self.ordinary_compiler_dll(),
                     "DotNetTool": "", "DOTNET_HOST_PATH": ""}, "A .NET host is required")

    def test_dll_with_a_missing_host_is_rejected(self):
        self.invoke({"CallHelperTargetArchitecture": "wasm64", "CallHelperCompilerPath": self.ordinary_compiler_dll(),
                     "DOTNET_HOST_PATH": OPTIONS.evidence_dir / "missing-dotnet"}, "The .NET host for the crossgen2 DLL does not exist:")

    def test_memory64_missing_closure_does_not_fall_back(self):
        self.invoke({"CallHelperTargetArchitecture": "wasm64", "CallHelperCompilerPath": self.ordinary_compiler_dll(),
                     "BrowserScanPath": OPTIONS.evidence_dir / "missing-wasm64-framework"},
                    "The wasm64 framework scan path does not exist:")

    def test_empty_scan_does_not_generate_tables(self):
        directory = OPTIONS.evidence_dir / "empty-framework"
        directory.mkdir(exist_ok=True)
        output = self.invoke({"CallHelperTargetArchitecture": "wasm64", "CallHelperCompilerPath": self.ordinary_compiler_dll(),
                              "BrowserScanPath": directory}, "No assemblies to scan were found")
        self.assertFalse(list(output.rglob("*.cpp")))


class FullGenerationTests(CallHelperTests):
    def test_32_default_target_and_output_stability(self):
        # Omit the architecture property to exercise the 32-bit default, and the
        # compiler property unless the caller explicitly selects another host build.
        closure = self.closure("wasm")
        properties = {"CallHelperTargetOS": "browser"}
        if OPTIONS.compiler is not None:
            properties["CallHelperCompilerPath"] = OPTIONS.compiler
        if OPTIONS.scan32 is not None:
            properties["BrowserScanPath"] = closure
        directory = self.invoke(properties)
        generated = directory / "output/browser"
        first = {name: ((generated / name).read_bytes(), (generated / name).stat().st_mtime_ns) for name in NAMES}
        for name in NAMES:
            self.assertNotIn(b"wasm64 call helpers require", first[name][0])
            if OPTIONS.configuration == "Release":
                self.assertEqual((PROJECT.parent / "browser" / name).read_bytes(), first[name][0], name)
        self.assertIn("#define ARG_IND(i) ((int32_t)((int32_t*)ARG_ADDR(i)))",
                      (generated / "callhelpers-interp-to-managed.cpp").read_text())
        if OPTIONS.configuration != "Release":
            # Configuration-specific import comments need not match the checked-in
            # Release closure. Still require stable bytes and output timestamps.
            self.invoke(properties, invocation="repeat")
            for name in NAMES:
                self.assertEqual(first[name][0], (generated / name).read_bytes(), name)
                self.assertEqual(first[name][1], (generated / name).stat().st_mtime_ns, name)
        response = OPTIONS.evidence_dir / "obj/wasm-callhelpers/browser/generate-coreclr-helpers.rsp"
        self.assertIn("--targetarch:wasm\n", response.read_text())
        self.assertFalse((directory / "output/browser/wasm64").exists())

    def test_64_uses_memory64_inputs_and_isolated_output(self):
        closure = self.closure("wasm64")
        response32 = OPTIONS.evidence_dir / "obj/wasm-callhelpers/browser/generate-coreclr-helpers.rsp"
        original32 = response32.read_bytes() if response32.exists() else None
        properties = {"CallHelperTargetArchitecture": "wasm64"}
        if OPTIONS.scan64 is not None:
            properties["BrowserScanPath"] = closure
        if OPTIONS.compiler is not None:
            properties["CallHelperCompilerPath"] = OPTIONS.compiler
        directory = self.invoke(properties)
        generated = directory / "output/browser/wasm64"
        self.assertEqual(sorted(NAMES), sorted(path.name for path in generated.glob("*.cpp")))
        for name in NAMES:
            self.assertIn('static_assert(sizeof(void*) == 8, "wasm64 call helpers require 64-bit pointers");',
                          (generated / name).read_text())
        self.assertIn("#define ARG_IND(i) ((int64_t)((int64_t*)ARG_ADDR(i)))",
                      (generated / "callhelpers-interp-to-managed.cpp").read_text())
        response = OPTIONS.evidence_dir / "obj/wasm-callhelpers/browser/wasm64/generate-coreclr-helpers.rsp"
        arguments = response.read_text().splitlines()
        self.assertIn("--targetarch:wasm64", arguments)
        self.assertIn(str(closure / "System.Private.CoreLib.dll"), arguments)
        if original32 is not None:
            self.assertEqual(original32, response32.read_bytes())
        self.assertFalse(list((directory / "output/browser").glob("*.cpp")))
        if OPTIONS.compiler is None:
            # Exercise the supported DLL override and real host execution as well as
            # the default single-file executable, keeping both commands and outputs.
            properties["CallHelperCompilerPath"] = self.ordinary_compiler_dll()
            properties["CallHelperOutputRoot"] = directory / "dll-output"
            self.invoke(properties, invocation="dll")
            for name in NAMES:
                self.assertEqual((generated / name).read_bytes(),
                                 (directory / "dll-output/browser/wasm64" / name).read_bytes(), name)


def main():
    global OPTIONS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet", type=Path, required=True)
    parser.add_argument("--configuration", choices=("Release", "Checked", "Debug"), default="Release")
    parser.add_argument("--compiler", type=Path, help="Ordinary host crossgen2 DLL; permits Release host / Checked guest")
    parser.add_argument("--scan32", type=Path)
    parser.add_argument("--scan64", type=Path)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--compiler-validation", action="store_true",
                        help="Also validate ordinary compiler/host/scan failures; requires the real crossgen2 DLL")
    parser.add_argument("--full-generation", action="store_true")
    OPTIONS = parser.parse_args()
    for key in ("dotnet", "compiler", "scan32", "scan64", "evidence_dir"):
        value = getattr(OPTIONS, key)
        if value is not None:
            setattr(OPTIONS, key, value.resolve())
    OPTIONS.evidence_dir.mkdir(parents=True, exist_ok=True)
    suite = unittest.TestSuite()
    classes = [TargetValidationTests]
    if OPTIONS.compiler_validation or OPTIONS.full_generation:
        classes.append(CompilerValidationTests)
    if OPTIONS.full_generation:
        classes.append(FullGenerationTests)
    for test_class in classes:
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_class))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
