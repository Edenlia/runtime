#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Check the actual CoreLib project's target selection using the pinned SDK.

Set DOTNET_HOST_PATH to the repository-pinned SDK executable. These host tests
evaluate production MSBuild properties and validation targets; they do not
execute a guest or validate native transitions. Native compilation separately
checks AsmOffsets.cs against the actual native types with static_assert.
"""

import json
import os
from pathlib import Path
import subprocess
import unittest


REPOSITORY = Path(__file__).resolve().parents[3]
PROJECT = REPOSITORY / "src/coreclr/System.Private.CoreLib/System.Private.CoreLib.csproj"
DOTNET = os.environ.get("DOTNET_HOST_PATH", "dotnet")


class CoreLibTargetTests(unittest.TestCase):
    def evaluate(self, architecture, configuration, *arguments):
        return subprocess.run(
            [DOTNET, "msbuild", str(PROJECT), "-nologo", "-v:q",
             "-p:TargetOS=browser", f"-p:TargetArchitecture={architecture}",
             f"-p:Configuration={configuration}", *arguments],
            text=True, capture_output=True, check=False,
        )

    def assert_target(self, architecture, configuration, pointer_bits):
        result = self.evaluate(
            architecture, configuration,
            "-t:ValidateWasm64CoreLibPlatform",
            "-getProperty:TargetOS,TargetArchitecture,Platform,Is64Bit,DefineConstants,"
            "SupportsWasmIntrinsics,RuntimeBinDir,OutputPath,IntermediateOutputPath",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actual = json.loads(result.stdout)["Properties"]
        self.assertEqual(actual["TargetOS"], "browser")
        self.assertEqual(actual["TargetArchitecture"], architecture)
        self.assertEqual(actual["Platform"], architecture)
        self.assertEqual(actual["Is64Bit"] == "true", pointer_bits == 64)
        self.assertEqual(actual["SupportsWasmIntrinsics"], "true")

        constants = actual["DefineConstants"].split(";")
        self.assertIn("TARGET_WASM", constants)
        self.assertIn(f"TARGET_{pointer_bits}BIT", constants)
        other_bits = 32 if pointer_bits == 64 else 64
        self.assertNotIn(f"TARGET_{other_bits}BIT", constants)
        self.assertEqual("TARGET_WASM64" in constants, pointer_bits == 64)
        self.assertEqual("DEBUG" in constants, configuration == "Checked")

        output = Path(actual["OutputPath"]).resolve()
        runtime = Path(actual["RuntimeBinDir"]).resolve()
        expected = REPOSITORY / "artifacts/bin/coreclr" / f"browser.{architecture}.{configuration}"
        self.assertEqual(runtime, expected.resolve())
        self.assertEqual(output, (runtime / "IL").resolve())
        self.assertIn(f"browser.{architecture}.{configuration}", actual["IntermediateOutputPath"])

    def test_release_wasm32(self):
        self.assert_target("wasm", "Release", 32)

    def test_release_wasm64(self):
        self.assert_target("wasm64", "Release", 64)

    def test_checked_wasm32(self):
        self.assert_target("wasm", "Checked", 32)

    def test_checked_wasm64(self):
        self.assert_target("wasm64", "Checked", 64)

    def test_conflicting_platform_rejected(self):
        result = self.evaluate(
            "wasm64", "Release", "-p:Platform=wasm", "-t:ValidateWasm64CoreLibPlatform",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TargetArchitecture=wasm64 is incompatible with Platform=wasm", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
