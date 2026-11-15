#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Test the app target's call-helper command routing, without running a guest.

First build clr.corelib+clr.callhelpers for browser/wasm64 Release. Run this script
with DOTNET_HOST_PATH set to the repository-pinned SDK host (or dotnet on PATH).
WASM_CALLHELPERS_DLL and WASM_CALLHELPERS_CORELIB can override the default Release
bootstrap/CoreLib paths. Missing prerequisites fail; they are never skipped.

The production MSBuild app target and bootstrap assembly are real. Framework
resolution and module/assembly filtering are stubs, and the wasm32 executable
control is a host stub. These tests establish routing and expected rejection,
not wasm64 helper emission or managed/native/browser execution.
"""

import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).with_name("CallHelperRouting.proj")
ABI_DIAGNOSTIC = (
    "The wasm64 target is recognized, but portable call-helper generation requires "
    "the wasm64 managed/native ABI implementation."
)


def host_architecture():
    machine = platform.machine().lower()
    return {
        "amd64": "x64", "x86_64": "x64", "aarch64": "arm64",
        "i386": "x86", "i686": "x86", "armv7l": "arm",
    }.get(machine, machine)


class CallHelperRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.architecture = host_architecture()
        dotnet = os.environ.get("DOTNET_HOST_PATH") or shutil.which("dotnet")
        if not dotnet or not Path(dotnet).is_file():
            raise RuntimeError("Set DOTNET_HOST_PATH to the repository-pinned SDK host.")
        cls.dotnet = Path(dotnet).resolve()
        artifacts = REPOSITORY / "artifacts/bin/coreclr/browser.wasm64.Release"
        helper = Path(os.environ.get(
            "WASM_CALLHELPERS_DLL",
            artifacts / cls.architecture / "crossgen2-callhelpers/crossgen2.dll",
        )).resolve()
        cls.corelib = Path(os.environ.get(
            "WASM_CALLHELPERS_CORELIB", artifacts / "IL/System.Private.CoreLib.dll",
        )).resolve()
        for label, path in (("helper bootstrap", helper), ("target CoreLib", cls.corelib)):
            if not path.is_file():
                raise RuntimeError(
                    f"Missing {label}: {path}. Build clr.corelib+clr.callhelpers for "
                    "browser/wasm64 Release, or set WASM_CALLHELPERS_DLL and "
                    "WASM_CALLHELPERS_CORELIB to matching build outputs."
                )

        scratch_root = REPOSITORY / "artifacts/obj/wasm-callhelper-routing"
        scratch_root.mkdir(parents=True, exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(prefix="run-", dir=scratch_root)
        cls.addClassCleanup(cls.scratch.cleanup)
        cls.work = Path(cls.scratch.name)
        log_root = Path(os.environ.get(
            "WASM_CALLHELPER_TEST_LOG_DIR",
            REPOSITORY / "artifacts/log/wasm-callhelper-routing",
        ))
        cls.logs = log_root / cls.work.name
        cls.logs.mkdir(parents=True, exist_ok=True)
        print(f"Call-helper routing logs: {cls.logs}", flush=True)

        # Stage the actual host-tool closure in the canonical layout to exercise
        # inferred selection even when WASM_CALLHELPERS_DLL names another build.
        cls.artifacts = cls.work / "target-artifacts"
        cls.staged_helper = cls.artifacts / cls.architecture / "crossgen2-callhelpers/crossgen2.dll"
        shutil.copytree(helper.parent, cls.staged_helper.parent)
        cls.spaced_helper = cls.work / "tool with spaces/crossgen2.dll"
        shutil.copytree(helper.parent, cls.spaced_helper.parent)
        cls.environment = os.environ.copy()
        cls.environment.pop("DOTNET_HOST_PATH", None)
        cls.environment.pop("EMSDK_PATH", None)
        cls.results = []
        cls.addClassCleanup(cls.write_results)

    @classmethod
    def write_results(cls):
        (cls.logs / "results.json").write_text(
            json.dumps(cls.results, indent=2) + "\n", encoding="utf-8",
        )

    def run_target(self, name, diagnostic, properties=None, environment=None):
        output = self.work / name
        properties = {
            "HarnessOutput": str(output),
            "RoutingTestArtifactsPath": str(self.artifacts),
            "RoutingTestHostArchitecture": self.architecture,
            "RoutingTestDotNet": str(self.dotnet),
            "RoutingTestCoreLib": str(self.corelib),
            **(properties or {}),
        }
        command = [
            str(self.dotnet), "msbuild", str(PROJECT), "-nologo", "-v:n",
            *[f"-p:{key}={value}" for key, value in properties.items()],
        ]
        result = subprocess.run(
            command, env={**self.environment, **(environment or {})},
            text=True, capture_output=True, check=False,
        )
        log = result.stdout + result.stderr
        (self.logs / f"{name}.log").write_text(log, encoding="utf-8")
        response = output / "callhelpers-generator.rsp"
        response_text = response.read_text(encoding="utf-8-sig") if response.is_file() else None
        self.results.append({
            "name": name, "command": command, "exit_code": result.returncode,
            "expected_diagnostic": diagnostic, "response_file": response_text,
            "scope": "Host routing/rejection only; framework resolution and module/assembly filtering stubbed; no guest execution",
        })
        self.assertNotEqual(result.returncode, 0, log)
        self.assertIn(diagnostic, log)
        return output, response_text

    def assert_abi_rejection(self, name, properties=None, environment=None):
        output, response = self.run_target(name, ABI_DIAGNOSTIC, properties, environment)
        self.assertIsNotNone(response)
        self.assertIn("--targetarch:wasm64\n", response)
        self.assertIn("--targetos:browser\n", response)
        for source in ("callhelpers-pinvoke.cpp", "callhelpers-reverse.cpp", "callhelpers-interp-to-managed.cpp"):
            self.assertFalse((output / source).exists(), f"Unexpected emitted helper: {source}")

    def test_inferred_wasm64_generator(self):
        self.assert_abi_rejection("inferred-wasm64-generator")

    def test_explicit_path_with_spaces_and_host_fallback(self):
        self.assert_abi_rejection(
            "explicit-path-with-spaces-host-fallback",
            {"Crossgen2CallHelpersPath": str(self.spaced_helper), "DisableDotNetTool": "true"},
            {"DOTNET_HOST_PATH": str(self.dotnet)},
        )

    def test_missing_sdk_host_rejected(self):
        # dotnet msbuild populates DOTNET_HOST_PATH itself, so override the
        # property explicitly to exercise the genuinely missing-host case.
        self.run_target(
            "missing-sdk-host-rejected", "Set DotNetTool or DOTNET_HOST_PATH to the SDK host",
            {"DisableDotNetTool": "true", "DOTNET_HOST_PATH": ""},
        )

    def test_wasm32_dll_rejected(self):
        self.run_target(
            "wasm32-dll-rejected", "to a crossgen2 executable, not the DLL",
            {"RuntimeIdentifier": "browser-wasm", "Crossgen2Path": str(self.staged_helper)},
        )

    def test_missing_wasm64_generator_does_not_fall_back(self):
        self.run_target(
            "missing-wasm64-generator-no-fallback", "Portable call-helper generator not found:",
            {"Crossgen2CallHelpersPath": str(self.work / "missing.dll"), "Crossgen2Path": str(self.staged_helper)},
        )

    def test_wasm32_executable_routing_host_stub(self):
        if os.name == "nt":
            stub = self.work / "wasm32 executable stub.cmd"
            stub.write_text(
                '@echo off\nset "ROUTING_RSP=%~1"\nset "ROUTING_RSP=%ROUTING_RSP:~1%"\n'
                'echo %*>"%ROUTING_RSP%.invoked"\nexit /b 43\n', encoding="utf-8",
            )
        else:
            stub = self.work / "wasm32 executable stub.sh"
            stub.write_text(
                '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "${1#@}.invoked"\nexit 43\n',
                encoding="utf-8",
            )
            stub.chmod(0o755)
        output, response = self.run_target(
            "wasm32-executable-routing-host-stub", "exited with code 43",
            {"RuntimeIdentifier": "browser-wasm", "Crossgen2Path": str(stub)},
        )
        self.assertIsNotNone(response)
        self.assertIn("--targetarch:wasm\n", response)
        self.assertTrue((output / "callhelpers-generator.rsp.invoked").is_file())
        self.results[-1]["scope"] += "; wasm32 executable is an intentional host stub"


if __name__ == "__main__":
    unittest.main()
