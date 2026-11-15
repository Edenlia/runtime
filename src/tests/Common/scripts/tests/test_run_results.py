#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Host result bookkeeping tests. Set DOTNET_TEST_HOST to a .NET 10+ SDK's dotnet executable.

The copied runner uses the host SDK's framework and a stub launcher. These tests do not build
or execute a guest runtime; they verify that stale logs cannot turn a wasm64 run into success.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


DOTNET = os.environ.get("DOTNET_TEST_HOST") or shutil.which("dotnet")


@unittest.skipUnless(DOTNET, "Set DOTNET_TEST_HOST to a .NET 10+ SDK's dotnet executable")
class RunResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.repository = Path(cls.scratch.name)
        cls.environment = os.environ.copy()
        for key in ("RunCrossGen2", "CrossGen2SynthesizePgo"):
            cls.environment.pop(key, None)
        for key, directory in (
            ("DOTNET_CLI_HOME", "cli-home"), ("XDG_DATA_HOME", "data"),
            ("XDG_CACHE_HOME", "cache"), ("XDG_RUNTIME_DIR", "runtime"),
        ):
            path = cls.repository / directory
            path.mkdir()
            cls.environment[key] = str(path)
        cls.environment["DOTNET_NOLOGO"] = "1"
        cls.environment["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
        version = subprocess.check_output(
            [DOTNET, "--version"], cwd=cls.repository, env=cls.environment, text=True,
        ).strip()
        major = int(version.split(".")[0])
        if major < 10:
            raise unittest.SkipTest("File-based host tests require a .NET 10+ SDK")

        source_repository = Path(__file__).resolve().parents[5]
        cls.source = cls.repository / "src/tests/run.cs"
        cls.source.parent.mkdir(parents=True)
        source = (source_repository / "src/tests/run.cs").read_text(encoding="utf-8")
        # Use the installed host framework so this bookkeeping test does not require a second SDK.
        source = source.replace(
            "#:property TargetFramework=net11.0",
            f"#:property TargetFramework=net{major}.0\n#:property PublishAot=false", 1,
        )
        cls.source.write_text(source, encoding="utf-8")
        (cls.repository / "artifacts/tests/coreclr/browser.wasm64.Debug").mkdir(parents=True)
        launcher = cls.repository / "dotnet.sh"
        launcher.write_text(
            '#!/usr/bin/env python3\n'
            'import os\n'
            'import subprocess\n'
            'from pathlib import Path\n'
            'logs = Path(os.environ["HARNESS_LOG_DIR"])\n'
            'kind = os.environ["HARNESS_RESULT_KIND"]\n'
            'if os.environ.get("HARNESS_VERIFY_HOST_ENV") == "1":\n'
            '    assert os.environ.get("DOTNET_CLI_HOME") == os.environ["HARNESS_EXPECTED_CLI_HOME"]\n'
            '    assert os.environ.get("DOTNET_INSTALL_DIR") == os.environ["HARNESS_EXPECTED_INSTALL_DIR"]\n'
            '    assert "DOTNET_WasmRunnerIsolationProbe" not in os.environ\n'
            '    guest = Path(os.environ["__TestEnv"]).read_text()\n'
            '    assert "export DOTNET_WasmRunnerIsolationProbe=guest-only-probe" in guest\n'
            '    assert "DOTNET_CLI_HOME" not in guest\n'
            '    assert "DOTNET_INSTALL_DIR" not in guest\n'
            '    version = subprocess.run([os.environ["HARNESS_HOST_TOOL"], "--version"],\n'
            '                             text=True, capture_output=True, check=True)\n'
            '    (logs / "host-sdk-version.txt").write_text(version.stdout)\n'
            'if kind != "none":\n'
            '    (logs / "StandaloneRunnerTestResults.testrun.log").write_text("current.sh: " + kind + "\\n")\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
        compiled = subprocess.run(
            [DOTNET, str(cls.source), "--", "--help"], cwd=cls.repository,
            env=cls.environment, text=True, capture_output=True, check=False,
        )
        if compiled.returncode != 0:
            raise RuntimeError(compiled.stdout + compiled.stderr)

    def verify_results(self, kind, expected_code, analyze=False, skip_tests=False, verify_host_env=False):
        logs = self.repository / self.id().split(".")[-1]
        logs.mkdir()
        stale_xml = (
            '<assemblies><assembly name="stale" time="0"><collection time="0">'
            '<test name="stale" type="Stale" method="M" result="Pass" />'
            '</collection></assembly></assemblies>'
        )
        stale_names = ("TestRun.xml", "old.testrun.xml", "UPPER.TESTRUN.XML", "old.testrun.xml.crashed")
        for name in stale_names[:3]:
            (logs / name).write_text(stale_xml, encoding="utf-8")
        (logs / stale_names[3]).write_text("ExitCode=1\n", encoding="utf-8")
        (logs / "StandaloneRunnerTestResults.testrun.log").write_text("stale.sh: Pass\n", encoding="utf-8")
        (logs / "unrelated.log").write_text("preserve", encoding="utf-8")
        environment = self.environment.copy()
        environment["HARNESS_LOG_DIR"] = str(logs)
        environment["HARNESS_RESULT_KIND"] = kind
        if skip_tests:
            environment["SkipTests"] = "true"
        if verify_host_env:
            install_dir = str(Path(DOTNET).resolve().parent)
            environment["DOTNET_INSTALL_DIR"] = install_dir
            environment["DOTNET_WasmRunnerIsolationProbe"] = "guest-only-probe"
            environment["HARNESS_VERIFY_HOST_ENV"] = "1"
            environment["HARNESS_EXPECTED_CLI_HOME"] = environment["DOTNET_CLI_HOME"]
            environment["HARNESS_EXPECTED_INSTALL_DIR"] = install_dir
            environment["HARNESS_HOST_TOOL"] = DOTNET
        arguments = ["-arch", "wasm64", "-os", "browser", "-logs_dir", str(logs)]
        if analyze:
            arguments.append("--analyze_results_only")
        result = subprocess.run(
            [DOTNET, str(self.source), "--", *arguments], cwd=self.repository,
            env=environment, text=True, capture_output=True, check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, expected_code, output)
        for name in stale_names:
            self.assertEqual((logs / name).exists(), analyze, output)
        self.assertEqual((logs / "unrelated.log").read_text(encoding="utf-8"), "preserve")
        if expected_code != 0:
            self.assertIn("No wasm64 tests executed", output)
        if verify_host_env:
            self.assertRegex((logs / "host-sdk-version.txt").read_text(encoding="utf-8"), r"^\d+\.")

    def test_all_skipped_cannot_use_stale_success(self):
        self.verify_results("Skip", 1)

    def test_empty_run_cannot_use_stale_success(self):
        self.verify_results("none", 1)

    def test_skip_tests_cannot_use_stale_success(self):
        self.verify_results("none", 1, skip_tests=True)

    def test_current_result_can_succeed(self):
        self.verify_results("Pass", 0)

    def test_analyze_only_preserves_results(self):
        self.verify_results("none", 0, analyze=True)

    def test_host_sdk_configuration_is_preserved_and_guest_knobs_are_isolated(self):
        self.verify_results("Pass", 0, verify_host_env=True)


if __name__ == "__main__":
    unittest.main()
