#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Exercise the actual native projects' Memory64 ICU preparation targets.

Requires DOTNET_HOST_PATH, EMSDK_PATH, NUGET_PACKAGES, and
MEMORY64_EMSCRIPTEN_TEST_CACHE. Build the default Memory64 ICU dependency first:
this suite fails if its manifest is missing and never invokes a native build.
Only existing archives are verified; host-generated version files use a
temporary directory. These checks do not execute the CoreCLR guest.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPOSITORY = Path(__file__).resolve().parents[3]
PROJECTS = ("src/coreclr/runtime.proj", "src/native/libs/build-native.proj")
DEFAULT_ICU = REPOSITORY / "artifacts/bin/icu/browser-wasm64/Release/native"
PROPERTIES = (
    "TargetArchitecture,TargetRid,_IcuDir,Memory64IcuDir,_Memory64IcuWasOverridden,"
    "_Memory64IcuOperation,Memory64EmscriptenCacheDir,BrowserHostMaximumHeapSize,"
    "_CoreClrBuildEnvironmentVariables,_BuildNativeEnvironmentVariables,_BuildNativeArgs"
)
ITEMS = "NativeCMakeArg,_WasmOptBaselineFeatureFlag,_PreparedMemory64Icu,_NativeExecProbeOutput"


def file_snapshot(directory):
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*") if path.is_file()
    }


class Memory64IcuIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = ("DOTNET_HOST_PATH", "EMSDK_PATH", "NUGET_PACKAGES", "MEMORY64_EMSCRIPTEN_TEST_CACHE")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError("Missing test prerequisites: " + ", ".join(missing))
        cls.dotnet = Path(os.environ["DOTNET_HOST_PATH"]).resolve()
        cls.sdk = Path(os.environ["EMSDK_PATH"]).resolve()
        cls.cache = Path(os.environ["MEMORY64_EMSCRIPTEN_TEST_CACHE"]).resolve()
        for path in (cls.dotnet, cls.sdk / "emscripten/emcc", DEFAULT_ICU / "icu-memory64.json"):
            if not path.is_file():
                raise RuntimeError(f"Missing test prerequisite: {path}. Provision tools and build Memory64 ICU first.")
        if not cls.cache.is_dir():
            raise RuntimeError(f"Missing isolated Memory64 Emscripten test cache: {cls.cache}")
        dependency = ET.parse(REPOSITORY / "eng/Version.Details.xml").find(
            "./ProductDependencies/Dependency[@Name='Microsoft.NETCore.Runtime.ICU.Transport']")
        if dependency is None:
            raise RuntimeError("The runtime's ICU transport dependency was not found.")
        cls.wasm32_icu = (Path(os.environ["NUGET_PACKAGES"]) / "microsoft.netcore.runtime.icu.transport" /
                          dependency.attrib["Version"] / "runtimes/browser-wasm/native").resolve()
        if not (cls.wasm32_icu / "lib/libicui18n.a").is_file():
            raise RuntimeError(f"Restore the actual wasm32 ICU transport before this test: {cls.wasm32_icu}")
        cls.temporary = tempfile.TemporaryDirectory(prefix="wasm64 ICU integration ")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)

    def invoke(self, project, architecture="wasm64", targets="ValidateWasm64Target", **properties):
        # The fixed target allow-list prevents a test change from silently
        # turning this suite into a native runtime or dependency build.
        allowed = {"ValidateWasm64Target", "PrepareMemory64Icu", "_PrepareCoreClrNativeEnvironment",
                   "BuildNativeCommon", "CheckEnvironment"}
        self.assertTrue(set(targets.split(",")).issubset(allowed), targets)
        self.assertTrue((DEFAULT_ICU / "icu-memory64.json").is_file(), "Memory64 ICU must already be built")
        defaults = {
            "TargetOS": "browser", "TargetArchitecture": architecture, "Configuration": "Release",
            "RuntimeFlavor": "CoreCLR", "EMSDK_PATH": str(self.sdk),
            # Supply NuGet's actual GeneratePathProperty value: these tests do
            # not restore every project/architecture-specific assets graph.
            "PkgMicrosoft_NETCore_Runtime_ICU_Transport": str(self.wasm32_icu.parents[2]),
            "Memory64EmscriptenCacheDir": str(self.cache),
            "NativeVersionFile": str(self.directory / (Path(project).parent.name + "-version.c")),
        }
        defaults.update(properties)
        return subprocess.run(
            [str(self.dotnet), "msbuild", str(REPOSITORY / project), "-nologo", "-v:q",
             f"-t:{targets}", f"-getProperty:{PROPERTIES}", f"-getItem:{ITEMS}",
             *[f"-p:{key}={value}" for key, value in defaults.items()]],
            cwd=REPOSITORY, text=True, capture_output=True, check=False,
        )

    def success(self, project, architecture="wasm64", targets="ValidateWasm64Target", **properties):
        result = self.invoke(project, architecture, targets, **properties)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Exec output can precede the final MSBuild query object. Parse that
        # object, rather than treating dependency verifier output as the query.
        decoder = json.JSONDecoder()
        for index, character in enumerate(result.stdout):
            if character != "{":
                continue
            try:
                actual, _ = decoder.raw_decode(result.stdout, index)
            except ValueError:
                continue
            if isinstance(actual, dict) and "Properties" in actual and "Items" in actual:
                return actual
        self.fail("MSBuild did not return the requested JSON properties/items:\n" + result.stdout + result.stderr)

    def rejected(self, project, diagnostic, **properties):
        result = self.invoke(project, targets="PrepareMemory64Icu", **properties)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(diagnostic, result.stdout + result.stderr)

    def assert_prepared_icu(self, actual, expected):
        self.assertEqual(Path(actual["Properties"]["_IcuDir"]).resolve(), expected.resolve())
        returned = actual["Items"]["_PreparedMemory64Icu"]
        self.assertEqual(len(returned), 1)
        self.assertEqual(Path(returned[0]["Identity"]).resolve(), expected.resolve())
        arguments = [item["Identity"] for item in actual["Items"]["NativeCMakeArg"]]
        icu_arguments = [argument for argument in arguments if "CMAKE_ICU_DIR=" in argument]
        self.assertEqual(len(icu_arguments), 1)
        self.assertIn(f'-DCMAKE_ICU_DIR={actual["Properties"]["_IcuDir"]}', icu_arguments[0])

    def assert_memory64_environment(self, actual, name):
        environment = dict(item.split("=", 1) for item in actual["Properties"][name].split(";") if item)
        self.assertEqual(Path(environment["EMSDK_PATH"]).resolve(), self.sdk)
        self.assertEqual(Path(environment["EM_CACHE"]).resolve(), self.cache)
        self.assertIn("EM_FROZEN_CACHE", environment)
        self.assertEqual(environment["EM_FROZEN_CACHE"], "")

    def test_native_projects_evaluate_width_specific_dependencies_and_memory(self):
        for project in PROJECTS:
            for architecture in ("wasm", "wasm64"):
                with self.subTest(project=project, architecture=architecture):
                    actual = self.success(project, architecture)
                    properties = actual["Properties"]
                    self.assertEqual(properties["TargetRid"], f"browser-{architecture}")
                    flags = [item["Identity"] for item in actual["Items"]["_WasmOptBaselineFeatureFlag"]]
                    self.assertEqual("--enable-memory64" in flags, architecture == "wasm64")
                    expected = DEFAULT_ICU if architecture == "wasm64" else self.wasm32_icu
                    self.assertEqual(Path(properties["_IcuDir"]).resolve(), expected.resolve())
                    self.assertEqual(properties["BrowserHostMaximumHeapSize"],
                                     "8589934592" if architecture == "wasm64" else "2147483648")

    def test_runtime_prepares_default_icu_and_isolated_environment(self):
        actual = self.success(PROJECTS[0], targets="PrepareMemory64Icu,_PrepareCoreClrNativeEnvironment",
                              RuntimeIdentifier="browser-wasm64", Platform="wasm64", Subset="clr.runtime+clr.hosts")
        self.assert_prepared_icu(actual, DEFAULT_ICU)
        self.assertEqual(actual["Properties"]["_Memory64IcuOperation"], "build")
        self.assert_memory64_environment(actual, "_CoreClrBuildEnvironmentVariables")

    def test_libraries_common_target_expands_prepared_icu_and_environment(self):
        actual = self.success(PROJECTS[1], targets="BuildNativeCommon")
        self.assert_prepared_icu(actual, DEFAULT_ICU)
        self.assert_memory64_environment(actual, "_BuildNativeEnvironmentVariables")
        self.assertIn("-DCMAKE_ICU_DIR=" + actual["Properties"]["_IcuDir"],
                      actual["Properties"]["_BuildNativeArgs"])
        self.assertIn("-DCMAKE_EMCC_EXPORTED_FUNCTIONS=", actual["Properties"]["_BuildNativeArgs"])

    def test_external_memory64_directory_with_spaces_is_only_verified(self):
        external = self.directory / "external ICU with spaces"
        shutil.copytree(DEFAULT_ICU, external)
        before = file_snapshot(external)
        for project in PROJECTS:
            with self.subTest(project=project):
                actual = self.success(project, targets="PrepareMemory64Icu", Memory64IcuDir=str(external))
                self.assertEqual(actual["Properties"]["_Memory64IcuWasOverridden"], "true")
                self.assertEqual(actual["Properties"]["_Memory64IcuOperation"], "verify")
                self.assert_prepared_icu(actual, external)
                self.assertEqual(file_snapshot(external), before)

    def test_actual_wasm32_transport_override_is_rejected_by_both_projects(self):
        for project in PROJECTS:
            with self.subTest(project=project):
                self.rejected(project, "expected only wasm64 archive members, found wasm32",
                              Memory64IcuDir=str(self.wasm32_icu))

    def test_low_level_icu_cmake_override_is_rejected_by_both_projects(self):
        for project in PROJECTS:
            with self.subTest(project=project):
                self.rejected(project, "Use Memory64IcuDir instead of CMakeArgs/CMAKE_ICU_DIR",
                              CMakeArgs="-DCMAKE_ICU_DIR=" + str(self.wasm32_icu))

    def test_wasm32_runtime_environment_does_not_select_memory64_cache(self):
        actual = self.success(PROJECTS[0], "wasm", "PrepareMemory64Icu,_PrepareCoreClrNativeEnvironment")
        self.assertEqual(actual["Items"]["_PreparedMemory64Icu"], [])
        environment = actual["Properties"]["_CoreClrBuildEnvironmentVariables"]
        self.assertEqual(environment, "EMSDK_PATH=" + str(self.sdk))
        self.assertNotIn("EM_CACHE", environment)
        self.assertNotIn("EM_FROZEN_CACHE", environment)

    def test_wasm32_libraries_keep_transport_path_and_environment(self):
        actual = self.success(PROJECTS[1], "wasm", "BuildNativeCommon")
        self.assertEqual(actual["Items"]["_PreparedMemory64Icu"], [])
        self.assertEqual(actual["Properties"]["_BuildNativeEnvironmentVariables"], "")
        # wasm32 retains the existing evaluation-time NativeCMakeArg reference;
        # the eventual native Exec expands that item expression.
        arguments = [item["Identity"] for item in actual["Items"]["NativeCMakeArg"]]
        self.assertTrue(any("-DCMAKE_ICU_DIR=" + actual["Properties"]["_IcuDir"] in argument
                            for argument in arguments))
        self.assertEqual(Path(actual["Properties"]["_IcuDir"]).resolve(), self.wasm32_icu)

    def test_native_exec_receives_empty_frozen_cache_and_isolated_cache(self):
        # Keep the importing harness under the repository so MSBuild resolves
        # the NoTargets SDK version from the actual global.json.
        parent = REPOSITORY / "artifacts/obj/icu-integration-tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="native env ", dir=parent) as temporary:
            directory = Path(temporary)
            probe = directory / "probe.py"
            probe.write_text(
                "import os\nfrom pathlib import Path\nimport sys\n"
                "assert Path(os.environ['EM_CACHE']).resolve() == Path(sys.argv[1]).resolve()\n"
                "assert 'EM_FROZEN_CACHE' in os.environ\n"
                "assert os.environ['EM_FROZEN_CACHE'] == ''\n"
                "print('Memory64 native Exec environment PASS')\n", encoding="utf-8")
            project = ET.Element("Project")
            ET.SubElement(project, "Import", {"Project": str(REPOSITORY / PROJECTS[0])})
            target = ET.SubElement(project, "Target", {
                "Name": "CheckEnvironment", "DependsOnTargets": "_PrepareCoreClrNativeEnvironment"})
            execute = ET.SubElement(target, "Exec", {
                "Command": f'"{os.sys.executable}" "{probe}" "{self.cache}"',
                "EnvironmentVariables": "$(_CoreClrBuildEnvironmentVariables)", "ConsoleToMSBuild": "true"})
            ET.SubElement(execute, "Output", {"TaskParameter": "ConsoleOutput", "ItemName": "_NativeExecProbeOutput"})
            harness = directory / "environment.proj"
            ET.ElementTree(project).write(harness, encoding="unicode")
            actual = self.success(str(harness), targets="CheckEnvironment")
            output = [item["Identity"] for item in actual["Items"]["_NativeExecProbeOutput"]]
            self.assertIn("Memory64 native Exec environment PASS", output)
            self.assert_memory64_environment(actual, "_CoreClrBuildEnvironmentVariables")


if __name__ == "__main__":
    unittest.main()
