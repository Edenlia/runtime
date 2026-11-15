#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Check the shell runner's argument contract without downloading an SDK or running guests."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class RunArgumentsTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.repository = Path(self.scratch.name)
        source_repository = Path(__file__).resolve().parents[5]
        for relative_path in ("src/tests/run.sh", "eng/common/native/init-os-and-arch.sh"):
            destination = self.repository / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_repository / relative_path, destination)

        self.invocation = self.repository / "invocation.txt"
        dotnet = self.repository / "dotnet.sh"
        dotnet.write_text(
            '#!/usr/bin/env bash\n'
            'printf "%s\\n" "$@" > "$WASM_TEST_INVOCATION"\n'
            'exit "${WASM_TEST_EXIT_CODE:-0}"\n',
            encoding="utf-8",
        )
        dotnet.chmod(0o755)
        self.environment = os.environ.copy()
        for name in ("RunWithNodeJS", "RunCrossGen2", "CrossGen2SynthesizePgo", "RunInterpreter"):
            self.environment.pop(name, None)
        self.environment["WASM_TEST_INVOCATION"] = str(self.invocation)

    def run_script(self, *arguments):
        return subprocess.run(
            ["bash", str(self.repository / "src/tests/run.sh"), *arguments],
            env=self.environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_wasm64_preserves_target_and_browser_defaults(self):
        result = self.run_script("wasm64", "release", "--interpreter", "--tree=GC/Features")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.invocation.read_text(encoding="utf-8").splitlines(),
            [str(self.repository / "src/tests/run.cs"), "--", "-arch", "wasm64",
             "-build_type", "Release", "-os", "browser", "--interpreter", "--node",
             "--tree", "GC/Features"],
        )

    def test_wasm32_defaults_are_preserved(self):
        result = self.run_script("wasm", "checked")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.invocation.read_text(encoding="utf-8").splitlines(),
            [str(self.repository / "src/tests/run.cs"), "--", "-arch", "wasm",
             "-build_type", "Checked", "-os", "browser", "--node"],
        )

    def test_child_failure_is_reported(self):
        self.environment["WASM_TEST_EXIT_CODE"] = "37"
        self.assertEqual(self.run_script("wasm64").returncode, 37)

    def test_unknown_argument_does_not_report_success(self):
        result = self.run_script("wasm65")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.invocation.exists())

    def test_missing_tree_argument_is_rejected(self):
        for arguments in (("--tree",), ("--tree=",), ("--tree:",), ("--tree", "--node")):
            with self.subTest(arguments=arguments):
                result = self.run_script("wasm64", *arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.invocation.exists())

    def test_wasm64_wasi_is_rejected(self):
        result = self.run_script("wasm64", "wasi")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only the browser target", result.stdout)
        self.assertFalse(self.invocation.exists())

    def test_wasm64_compiled_execution_is_rejected(self):
        for option in ("--runcrossgen2tests", "--synthesizepgo", "--runnativeaottests"):
            with self.subTest(option=option):
                result = self.run_script("wasm64", option)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not supported", result.stdout)
                self.assertFalse(self.invocation.exists())

    def test_wasm64_crossgen_environment_is_rejected(self):
        self.environment["RunCrossGen2"] = "1"
        result = self.run_script("wasm64")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.invocation.exists())


if __name__ == "__main__":
    unittest.main()
