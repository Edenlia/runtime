#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Evaluate real root build routing with the repository-pinned SDK.

Set DOTNET_HOST_PATH to the SDK host. This suite invokes only an empty Check
target: it does not restore, build native components, or execute a guest.
Missing SDK prerequisites fail rather than skipping cases.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).with_name("TargetSelection.proj")
DOTNET = os.environ.get("DOTNET_HOST_PATH", "dotnet")
NATIVE_SUBSETS = "provision.emsdk+clr.runtime+clr.hosts+clr.corelib+libs.native"
PROPERTIES = (
    "TargetOS,TargetArchitecture,TargetRid,TargetsWasm,TargetsWasm64,Platform,"
    "RuntimeFlavor,DefaultSubsets,DefaultCoreClrSubsets,_subset,ClrRuntimeBuildSubsets,"
    "CoreclrRuntimeBinDir,NativeBinDir,WasmAppHostDir,IsInBuildToolProject"
)


class TargetSelectionTests(unittest.TestCase):
    def evaluate(self, **properties):
        defaults = {"Configuration": "Release", "InferPlatformFromTargetArchitecture": "true"}
        defaults.update(properties)
        return subprocess.run(
            [DOTNET, "msbuild", str(PROJECT), "-nologo", "-v:q", "-t:Check",
             f"-getProperty:{PROPERTIES}", "-getItem:ProjectToBuild,_CrossToolSubset",
             *[f"-p:{key}={value}" for key, value in defaults.items()]],
            text=True, capture_output=True, check=False,
        )

    def assert_success(self, **properties):
        result = self.evaluate(**properties)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_rejected(self, diagnostic, **properties):
        result = self.evaluate(**properties)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(diagnostic, result.stdout + result.stderr)

    def assert_target(self, architecture, **properties):
        actual = self.assert_success(**properties)["Properties"]
        self.assertEqual(actual["TargetOS"], "browser")
        self.assertEqual(actual["TargetArchitecture"], architecture)
        self.assertEqual(actual["TargetRid"], f"browser-{architecture}")
        self.assertEqual(actual["TargetsWasm"], "true")
        self.assertEqual(actual["TargetsWasm64"] == "true", architecture == "wasm64")
        self.assertEqual(actual["Platform"], architecture)

    def test_browser_default_remains_wasm32(self):
        self.assert_target("wasm", TargetOS="browser")

    def test_wasm32_rid_inference(self):
        self.assert_target("wasm", RuntimeIdentifier="browser-wasm")

    def test_explicit_wasm64(self):
        self.assert_target("wasm64", TargetOS="browser", TargetArchitecture="wasm64")

    def test_wasm64_rid_inference(self):
        self.assert_target("wasm64", RuntimeIdentifier="browser-wasm64")

    def test_wasm64_default_build_routes_only_native_and_il_products(self):
        for subset in (None, "clr"):
            with self.subTest(subset=subset):
                extra = {} if subset is None else {"Subset": subset}
                actual = self.assert_success(TargetOS="browser", TargetArchitecture="wasm64", **extra)
                properties = actual["Properties"]
                self.assertEqual(properties["DefaultSubsets"], NATIVE_SUBSETS)
                self.assertEqual(properties["DefaultCoreClrSubsets"], NATIVE_SUBSETS)
                self.assertEqual(set(properties["_subset"].strip("+").split("+")),
                                 set(NATIVE_SUBSETS.split("+")))
                self.assertEqual(set(filter(None, properties["ClrRuntimeBuildSubsets"].split(";"))),
                                 {"ClrHostsSubset=true", "ClrRuntimeSubset=true"})
                self.assertEqual(actual["Items"]["_CrossToolSubset"], [])
                projects = actual["Items"]["ProjectToBuild"]
                names = {Path(project["Identity"]).name for project in projects}
                self.assertEqual(names, {"AcquireEmscriptenSdk.proj", "System.Private.CoreLib.csproj",
                                         "runtime-prereqs.proj", "runtime.proj", "build-native.proj"})
                runtime = [p for p in projects if Path(p["Identity"]).name == "runtime.proj"]
                self.assertEqual(len(runtime), 1)
                self.assertIn("ClrRuntimeSubset=true", runtime[0]["AdditionalProperties"])
                self.assertIn("ClrHostsSubset=true", runtime[0]["AdditionalProperties"])
                self.assertNotIn("ClrJitSubset", runtime[0]["AdditionalProperties"])
                self.assertNotIn("ClrCrossComponentsBuild", runtime[0]["AdditionalProperties"])

    def test_existing_wasm32_compiler_routing_is_preserved(self):
        actual = self.assert_success(TargetOS="browser", TargetArchitecture="wasm",
                                     Subset="clr.tools+clr.crossarchtools")
        self.assertIn("clr.nativecorelib", actual["Properties"]["DefaultCoreClrSubsets"].split("+"))
        self.assertEqual([item["Identity"] for item in actual["Items"]["_CrossToolSubset"]],
                         ["ClrWasmJitSubset=true"])
        self.assertTrue(any(Path(item["Identity"]).name == "crossgen2_inbuild.csproj"
                            for item in actual["Items"]["ProjectToBuild"]))

    def test_products_and_apphost_paths_are_isolated_for_both_configurations(self):
        for configuration in ("Release", "Checked"):
            for architecture in ("wasm", "wasm64"):
                with self.subTest(configuration=configuration, architecture=architecture):
                    actual = self.assert_success(TargetOS="browser", TargetArchitecture=architecture,
                                                 Configuration=configuration, Subset="clr.corelib")["Properties"]
                    expected = {
                        "CoreclrRuntimeBinDir": REPOSITORY / f"artifacts/bin/coreclr/browser.{architecture}.{configuration}",
                        "NativeBinDir": REPOSITORY / f"artifacts/bin/native/net12.0-browser-{configuration}-{architecture}",
                        "WasmAppHostDir": REPOSITORY / f"artifacts/bin/WasmAppHost/{architecture}/{configuration}",
                    }
                    for name, path in expected.items():
                        self.assertEqual(Path(actual[name]).resolve(), path.resolve(), name)

    def test_native_projects_receive_architecture_and_isolated_output_paths(self):
        for configuration in ("Release", "Checked"):
            for architecture in ("wasm", "wasm64"):
                for relative_project in ("src/coreclr/runtime.proj", "src/native/libs/build-native.proj"):
                    with self.subTest(configuration=configuration, architecture=architecture,
                                      project=relative_project):
                        result = subprocess.run(
                            [DOTNET, "msbuild", str(REPOSITORY / relative_project), "-nologo", "-v:q",
                             "-t:ValidateWasm64Target", "-p:TargetOS=browser",
                             f"-p:TargetArchitecture={architecture}", f"-p:Configuration={configuration}",
                             "-p:ClrRuntimeSubset=true", "-p:ClrHostsSubset=true",
                             "-getProperty:TargetArchitecture,TargetRid,RuntimeBinDir,IntermediateOutputPath,"
                             "NativeBinDir,_BuildNativeOutConfig,_BuildNativeArgs,ClrJitSubset,ClrFullNativeBuild"],
                            text=True, capture_output=True, check=False,
                        )
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        actual = json.loads(result.stdout)["Properties"]
                        self.assertEqual(actual["TargetArchitecture"], architecture)
                        self.assertEqual(actual["TargetRid"], f"browser-{architecture}")
                        self.assertEqual(actual["ClrJitSubset"], "")
                        self.assertEqual(actual["ClrFullNativeBuild"], "")
                        out_config = f"net12.0-browser-{configuration}-{architecture}"
                        self.assertEqual(Path(actual["NativeBinDir"]).resolve(),
                                         (REPOSITORY / "artifacts/bin/native" / out_config).resolve())
                        if relative_project == "src/coreclr/runtime.proj":
                            target = f"browser.{architecture}.{configuration}"
                            self.assertEqual(Path(actual["RuntimeBinDir"]).resolve(),
                                             (REPOSITORY / "artifacts/bin/coreclr" / target).resolve())
                            self.assertIn(target, actual["IntermediateOutputPath"])
                        else:
                            self.assertEqual(actual["_BuildNativeOutConfig"], out_config)
                            self.assertTrue(actual["_BuildNativeArgs"].startswith(
                                f"{architecture} {configuration} outconfig {out_config} -os browser"))

    def test_conflicting_rids_are_rejected_in_both_directions(self):
        self.assert_rejected("requires TargetArchitecture=wasm64",
                             RuntimeIdentifier="browser-wasm64", TargetArchitecture="wasm")
        self.assert_rejected("requires RuntimeIdentifier=browser-wasm64",
                             TargetOS="browser", TargetArchitecture="wasm64", RuntimeIdentifier="browser-wasm")
        self.assert_rejected("TargetRid=browser-wasm64 requires TargetArchitecture=wasm64",
                             TargetOS="browser", TargetArchitecture="wasm", TargetRid="browser-wasm64")
        self.assert_rejected("requires TargetRid=browser-wasm64",
                             TargetOS="browser", TargetArchitecture="wasm64", TargetRid="browser-wasm")

    def test_conflicting_platforms_are_rejected_in_both_directions(self):
        for platform in ("wasm", "x64"):
            with self.subTest(platform=platform):
                self.assert_rejected("is incompatible with Platform=", TargetOS="browser",
                                     TargetArchitecture="wasm64", Platform=platform)
        self.assert_rejected("Platform=wasm64 requires TargetArchitecture=wasm64",
                             TargetOS="browser", TargetArchitecture="wasm", Platform="wasm64")

    def test_neutral_host_platform_remains_allowed(self):
        self.assert_success(TargetOS="browser", TargetArchitecture="wasm64", Platform="AnyCPU")

    def test_unsupported_execution_modes_are_rejected(self):
        common = {"TargetOS": "browser", "TargetArchitecture": "wasm64"}
        self.assert_rejected("only the CoreCLR runtime", **common, RuntimeFlavor="Mono")
        self.assert_rejected("only the CoreCLR runtime", **common, UseMonoRuntime="true")
        self.assert_rejected("only the CoreCLR runtime", **common, UseNativeAOTRuntime="true")
        self.assert_rejected("only single-threaded builds", **common, WasmEnableThreads="true")
        self.assert_rejected("only single-threaded builds", **common, FeatureMultithreading="true")
        self.assert_rejected("ReadyToRun compilation is not supported", **common, PublishReadyToRun="true")
        for target_os in ("wasi", "linux"):
            with self.subTest(target_os=target_os):
                self.assert_rejected("only TargetOS=browser", TargetOS=target_os, TargetArchitecture="wasm64")

    def test_host_tool_rid_and_readytorun_remain_allowed(self):
        self.assert_success(TargetOS="browser", TargetArchitecture="wasm64",
                            RuntimeIdentifier="linux-x64", IsInBuildToolProject="true",
                            PublishReadyToRun="true", Platform="AnyCPU", Subset="clr.corelib")
        # Also exercise the real host tool: its project name, RID and R2R
        # settings must be recognized without forcing IsInBuildToolProject.
        result = subprocess.run(
            [DOTNET, "msbuild", str(REPOSITORY / "src/coreclr/tools/aot/crossgen2/crossgen2_inbuild.csproj"),
             "-nologo", "-v:q", "-t:ValidateWasm64Target", "-p:TargetOS=browser",
             "-p:TargetArchitecture=wasm64", "-p:Configuration=Release",
             "-getProperty:IsInBuildToolProject,RuntimeIdentifier,NETCoreSdkRuntimeIdentifier,PublishReadyToRun"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        actual = json.loads(result.stdout)["Properties"]
        self.assertEqual(actual["IsInBuildToolProject"], "true")
        self.assertEqual(actual["PublishReadyToRun"], "true")
        self.assertEqual(actual["RuntimeIdentifier"], actual["NETCoreSdkRuntimeIdentifier"])
        self.assertNotEqual(actual["RuntimeIdentifier"], "browser-wasm64")

    def test_unsupported_compiler_subsets_are_rejected(self):
        for subset in ("clr.native", "clr.jit", "clr.wasmjit", "clr.alljits", "clr.alljitscommunity",
                       "clr.nativecorelib", "clr.aot", "clr.crossarchtools",
                       "clr.tools", "clr.nativeaotlibs", "clr.nativeaotruntime"):
            with self.subTest(subset=subset):
                self.assert_rejected("wasm64 does not support JIT, ReadyToRun, NativeAOT",
                                     TargetOS="browser", TargetArchitecture="wasm64", Subset=subset)

    def invoke_build_frontend(self, *arguments):
        # Run the exact frontend and native RID scripts. Replace only Arcade's
        # final build entry point with an argv recorder: no SDK or build runs.
        with tempfile.TemporaryDirectory(prefix="wasm-target-selection-") as directory:
            root = Path(directory)
            native = root / "eng/common/native"
            native.mkdir(parents=True)
            shutil.copy2(REPOSITORY / "eng/build.sh", root / "eng/build.sh")
            for name in ("init-os-and-arch.sh", "init-distro-rid.sh"):
                shutil.copy2(REPOSITORY / "eng/common/native" / name, native / name)
            recorder = root / "eng/common/build.sh"
            recorder.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
            recorder.chmod(0o755)
            return subprocess.run(["bash", str(root / "eng/build.sh"), *arguments],
                                  text=True, capture_output=True, check=False)

    def test_build_frontend_preserves_wasm64_and_existing_wasm32_default(self):
        for arguments, architecture in ((["-os", "browser"], "wasm"),
                                        (["-os", "browser", "-arch", "wasm64"], "wasm64")):
            with self.subTest(architecture=architecture):
                result = self.invoke_build_frontend(*arguments)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"/p:TargetArchitecture={architecture}", result.stdout.splitlines())

    def test_build_frontend_rejects_wrong_os_without_downgrading_architecture(self):
        for target_os in ("wasi", "linux"):
            with self.subTest(target_os=target_os):
                result = self.invoke_build_frontend("-os", target_os, "-arch", "wasm64")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("wasm64 is supported only with -os browser", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
