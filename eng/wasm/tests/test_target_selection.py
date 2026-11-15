#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Run with DOTNET_HOST_PATH pointing to the repository-pinned SDK host."""

import json
import os
from pathlib import Path
import subprocess
import unittest


PROJECT = Path(__file__).with_name("TargetSelection.proj")
DOTNET = os.environ.get("DOTNET_HOST_PATH", "dotnet")


class TargetSelectionTests(unittest.TestCase):
    def evaluate(self, **properties):
        result = subprocess.run(
            [DOTNET, "msbuild", str(PROJECT), "-nologo", "-v:q", "-t:Check",
             "-getProperty:TargetOS,TargetArchitecture,TargetRid,TargetsWasm,TargetsWasm64,Is64Bit,DefineConstants",
             *[f"-p:{key}={value}" for key, value in properties.items()]],
            text=True, capture_output=True, check=False)
        return result

    def assert_target(self, properties, architecture, pointer_bits):
        result = self.evaluate(**properties)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actual = json.loads(result.stdout)["Properties"]
        self.assertEqual(actual["TargetOS"], "browser")
        self.assertEqual(actual["TargetArchitecture"], architecture)
        self.assertEqual(actual["TargetRid"], f"browser-{architecture}")
        self.assertEqual(actual["TargetsWasm"], "true")
        constants = actual["DefineConstants"].split(";")
        self.assertIn(f"TARGET_{pointer_bits}BIT", constants)
        other_bits = 32 if pointer_bits == 64 else 64
        self.assertNotIn(f"TARGET_{other_bits}BIT", constants)
        self.assertEqual(actual["TargetsWasm64"] == "true", pointer_bits == 64)

    def assert_rejected(self, diagnostic, **properties):
        result = self.evaluate(**properties)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(diagnostic, result.stdout + result.stderr)

    def test_browser_default_is_wasm32(self):
        self.assert_target({"TargetOS": "browser"}, "wasm", 32)

    def test_wasm32_rid_inference(self):
        self.assert_target({"RuntimeIdentifier": "browser-wasm"}, "wasm", 32)

    def test_explicit_wasm64(self):
        self.assert_target({"TargetOS": "browser", "TargetArchitecture": "wasm64"}, "wasm64", 64)

    def test_wasm64_rid_inference(self):
        self.assert_target({"RuntimeIdentifier": "browser-wasm64"}, "wasm64", 64)

    def test_wrong_rid_architecture(self):
        self.assert_rejected("requires TargetArchitecture=wasm64",
                             RuntimeIdentifier="browser-wasm64", TargetArchitecture="wasm")
        self.assert_rejected("requires RuntimeIdentifier=browser-wasm64",
                             TargetOS="browser", TargetArchitecture="wasm64", RuntimeIdentifier="browser-wasm")

    def test_unsupported_execution_modes(self):
        common = {"TargetOS": "browser", "TargetArchitecture": "wasm64"}
        self.assert_rejected("requires the CoreCLR runtime", **common, RuntimeFlavor="Mono")
        self.assert_rejected("single managed thread", **common, WasmEnableThreads="true")
        self.assert_rejected("ReadyToRun compilation for wasm64 is not implemented",
                             **common, PublishReadyToRun="true")
        self.assert_rejected("requires TargetOS=browser", TargetOS="wasi", TargetArchitecture="wasm64")

    def test_host_tool_r2r_is_allowed(self):
        result = self.evaluate(TargetOS="browser", TargetArchitecture="wasm64",
                               RuntimeIdentifier="linux-x64", IsInBuildToolProject="true",
                               PublishReadyToRun="true", Subset="clr.callhelpers")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_compiler_subset_rejected(self):
        self.assert_rejected("wasm64 JIT and ReadyToRun compiler are not implemented",
                             TargetOS="browser", TargetArchitecture="wasm64", Subset="clr.nativecorelib")


if __name__ == "__main__":
    unittest.main()
