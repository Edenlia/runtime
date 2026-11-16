#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Test Memory64 sysroot preparation without building real system libraries.

Set DOTNET_HOST_PATH, EMSDK_PATH and the normal pinned-SDK host environment.
The default Memory64 ICU dependency must already exist. A private SDK fixture
records embuilder arguments and creates archives containing objects compiled by
the real LLVM compiler. Production archive verification and MSBuild preparation
targets run unchanged; no test writes to the real SDK or Emscripten cache.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPOSITORY = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY / "eng/wasm/build-memory64-icu.py"
ICU = REPOSITORY / "artifacts/bin/icu/browser-wasm64/Release/native"
TARGETS = ("libstubs", "libc", "libdlmalloc", "libclang_rt.builtins-wasmsjlj", "libc++-wasmexcept",
           "libc++abi-wasmexcept", "libunwind-wasmexcept")
CONSUMERS = ("BuildRuntime", "BuildNativeCommon")


BACKEND = '''import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
with Path(os.environ["MEMORY64_SYSROOT_FIXTURE_EVENTS"]).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"phase": "embuilder", "argv": sys.argv[1:],
        "cache": os.environ.get("EM_CACHE"), "frozen": os.environ.get("EM_FROZEN_CACHE"),
        "cores": os.environ.get("EMCC_CORES")}) + "\\n")
mode = os.environ.get("MEMORY64_SYSROOT_FIXTURE_MODE", "success")
if mode == "failure":
    sys.exit(7)
cache = Path(os.environ["EM_CACHE"]) / "sysroot/lib/wasm64-emscripten"
cache.mkdir(parents=True, exist_ok=True)
names = sys.argv[sys.argv.index("build") + 1:]
for index, name in enumerate(names):
    obj = root / ("fixture32.o" if mode == "wasm32" else "fixture64.o")
    members = [obj]
    if mode == "mixed" and index == 0:
        members.append(root / "fixture-bitcode.o")
    subprocess.run([str(root / "bin/llvm-ar"), "rcs", str(cache / (name + ".a")),
                    *map(str, members)], check=True)
'''


class Memory64SysrootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [name for name in ("DOTNET_HOST_PATH", "EMSDK_PATH") if not os.environ.get(name)]
        if missing:
            raise RuntimeError("Missing test prerequisites: " + ", ".join(missing))
        cls.dotnet = Path(os.environ["DOTNET_HOST_PATH"]).resolve()
        cls.sdk = Path(os.environ["EMSDK_PATH"]).resolve()
        for path in (cls.dotnet, cls.sdk / "bin/clang", cls.sdk / "bin/llvm-ar",
                     cls.sdk / "bin/llvm-readobj", cls.sdk / "node/bin/node",
                     cls.sdk / "emscripten/emcc", ICU / "icu-memory64.json"):
            if not path.is_file():
                raise RuntimeError(f"Missing test prerequisite: {path}")
        cls.objects = tempfile.TemporaryDirectory(prefix="memory64 sysroot objects ")
        cls.addClassCleanup(cls.objects.cleanup)
        cls.object_dir = Path(cls.objects.name)
        for width in (32, 64):
            source = cls.object_dir / f"fixture{width}.c"
            source.write_text(f'_Static_assert(sizeof(void*) == {width // 8}, "wrong target");\n'
                              'void *sysroot_fixture(void *value) { return value; }\n', encoding="utf-8")
            result = subprocess.run(
                [str(cls.sdk / "bin/clang"), f"--target=wasm{width}-unknown-emscripten", "-c",
                 str(source), "-o", str(cls.object_dir / f"fixture{width}.o")],
                text=True, capture_output=True, check=False)
            if result.returncode:
                raise RuntimeError("Real LLVM fixture compilation failed:\n" + result.stdout + result.stderr)
        result = subprocess.run(
            [str(cls.sdk / "bin/clang"), "--target=wasm64-unknown-emscripten", "-c", "-emit-llvm",
             str(cls.object_dir / "fixture64.c"), "-o", str(cls.object_dir / "fixture-bitcode.o")],
            text=True, capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError("Real LLVM bitcode fixture compilation failed:\n" + result.stdout + result.stderr)

    def setUp(self):
        # Repository-local harnesses resolve the NoTargets SDK version from
        # global.json; the separate fixture SDK contains no downloaded payload.
        parent = REPOSITORY / "artifacts/obj/wasm64-sysroot-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="private fixture ", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def fixture(self, name="fixture"):
        directory = self.directory / name
        sdk = directory / "SDK with spaces"
        (sdk / "emscripten").mkdir(parents=True)
        (sdk / "bin").symlink_to(self.sdk / "bin", target_is_directory=True)
        (sdk / "node").symlink_to(self.sdk / "node", target_is_directory=True)
        (sdk / "emscripten/emcc").symlink_to(self.sdk / "emscripten/emcc")
        (sdk / "emscripten/embuilder.py").write_text(BACKEND, encoding="utf-8")
        for filename in ("fixture32.o", "fixture64.o", "fixture-bitcode.o"):
            shutil.copy2(self.object_dir / filename, sdk / filename)
        return {"root": directory, "sdk": sdk, "cache": directory / "cold cache with spaces",
                "events": directory / "events.jsonl"}

    def environment(self, fixture, mode):
        environment = os.environ.copy()
        # Deliberately supply conflicting caller settings. Production must pass
        # the selected private cache, an empty frozen flag, and requested jobs.
        environment.update({"EM_CACHE": str(fixture["root"] / "unselected caller cache"),
                            "EM_FROZEN_CACHE": "caller-frozen", "EMCC_CORES": "99",
                            "MEMORY64_SYSROOT_FIXTURE_EVENTS": str(fixture["events"]),
                            "MEMORY64_SYSROOT_FIXTURE_MODE": mode})
        return environment

    def events(self, fixture):
        if not fixture["events"].exists():
            return []
        return [json.loads(line) for line in fixture["events"].read_text(encoding="utf-8").splitlines()]

    def cli(self, fixture, mode="success", cache=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "prepare-sysroot", "--emsdk", str(fixture["sdk"]),
             "--emscripten-cache", str(cache or fixture["cache"]), "--jobs", "2"],
            env=self.environment(fixture, mode), cwd=REPOSITORY,
            text=True, capture_output=True, check=False)

    def assert_builder(self, fixture):
        builders = [event for event in self.events(fixture) if event["phase"] == "embuilder"]
        self.assertEqual(len(builders), 1)
        self.assertEqual(builders[0]["argv"], ["--wasm64", "build", *TARGETS])
        self.assertEqual(Path(builders[0]["cache"]).resolve(), fixture["cache"].resolve())
        self.assertEqual(builders[0]["frozen"], "")
        self.assertEqual(builders[0]["cores"], "2")
        return builders[0]

    def assert_wasm64_archives(self, fixture):
        directory = fixture["cache"] / "sysroot/lib/wasm64-emscripten"
        self.assertEqual({path.name for path in directory.glob("*.a")}, {name + ".a" for name in TARGETS})
        for target in TARGETS:
            result = subprocess.run(
                [str(self.sdk / "bin/llvm-readobj"), "--file-header", str(directory / (target + ".a"))],
                text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Arch: wasm64", result.stdout)
            self.assertNotIn("Arch: wasm32", result.stdout)

    def msbuild(self, fixture, consumer, architecture="wasm64", mode="success"):
        project = ET.Element("Project", {"Sdk": "Microsoft.Build.NoTargets"})
        ET.SubElement(project, "Import", {"Project": str(REPOSITORY / "eng/native.wasm.targets")})
        acquire = ET.SubElement(project, "Target", {"Name": "AcquireEmscriptenSdk"})
        ET.SubElement(acquire, "WriteLinesToFile", {
            "File": "$(FixtureEvents)", "Lines": json.dumps({"phase": "acquire"}), "Overwrite": "false"})
        verified = ET.SubElement(project, "Target", {
            "Name": "RecordActualIcuVerification", "AfterTargets": "PrepareMemory64Icu",
            "Condition": "'$(TargetsWasm64)' == 'true'"})
        ET.SubElement(verified, "WriteLinesToFile", {
            "File": "$(FixtureEvents)", "Overwrite": "false",
            "Lines": '{"phase":"icu-verified","operation":"$(_Memory64IcuOperation)","path":"$(_IcuDir)"}'})
        for name in CONSUMERS:
            target = ET.SubElement(project, "Target", {"Name": name, "DependsOnTargets": "AcquireEmscriptenSdk"})
            ET.SubElement(target, "WriteLinesToFile", {
                "File": "$(FixtureEvents)", "Lines": json.dumps({"phase": "consumer", "name": name}),
                "Overwrite": "false"})
        harness = fixture["root"] / "native-preparation.proj"
        ET.ElementTree(project).write(harness, encoding="unicode")
        properties = {"TargetOS": "browser", "TargetArchitecture": architecture, "Configuration": "Release",
                      "RuntimeFlavor": "CoreCLR", "EMSDK_PATH": str(fixture["sdk"]),
                      "Memory64EmscriptenCacheDir": str(fixture["cache"]), "Memory64IcuDir": str(ICU),
                      "Memory64IcuBuildJobs": "2", "FixtureEvents": str(fixture["events"]),
                      "PythonExecutable": sys.executable}
        return subprocess.run(
            [str(self.dotnet), "msbuild", str(harness), "-nologo", "-v:q", f"-t:{consumer}",
             *[f"-p:{key}={value}" for key, value in properties.items()]],
            env=self.environment(fixture, mode), cwd=REPOSITORY,
            text=True, capture_output=True, check=False)

    def test_cli_cold_cache_uses_official_targets_and_selected_environment(self):
        fixture = self.fixture()
        self.assertFalse(fixture["cache"].exists())
        result = self.cli(fixture)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_builder(fixture)
        self.assert_wasm64_archives(fixture)
        self.assertFalse((fixture["root"] / "unselected caller cache").exists())

    def test_cli_rejects_sdk_stock_cache_without_calling_builder(self):
        fixture = self.fixture()
        stock = fixture["sdk"] / "emscripten/cache"
        result = self.cli(fixture, cache=stock)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("separate Memory64 system-library cache", result.stdout + result.stderr)
        self.assertEqual(self.events(fixture), [])
        self.assertFalse(stock.exists())

    def test_cli_builder_failure_propagates(self):
        fixture = self.fixture()
        result = self.cli(fixture, "failure")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_builder(fixture)
        self.assertIn("7", result.stdout + result.stderr)
        self.assertFalse(fixture["cache"].exists())

    def test_cli_rejects_actual_wasm32_archive_members(self):
        fixture = self.fixture()
        result = self.cli(fixture, "wasm32")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_builder(fixture)
        self.assertIn("wasm32", result.stdout + result.stderr)

    def test_cli_rejects_mixed_wasm64_and_unrecognized_bitcode_members(self):
        fixture = self.fixture()
        result = self.cli(fixture, "mixed")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_builder(fixture)
        self.assertIn("recognized", result.stdout + result.stderr)

    def test_msbuild_prepares_cold_cache_and_verifies_icu_before_each_consumer(self):
        for consumer in CONSUMERS:
            with self.subTest(consumer=consumer):
                fixture = self.fixture(consumer)
                result = self.msbuild(fixture, consumer)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                events = self.events(fixture)
                self.assertEqual([event["phase"] for event in events],
                                 ["acquire", "embuilder", "icu-verified", "consumer"])
                self.assertEqual(events[2]["operation"], "verify")
                self.assertEqual(Path(events[2]["path"]).resolve(), ICU.resolve())
                self.assertEqual(events[3]["name"], consumer)
                self.assert_builder(fixture)
                self.assert_wasm64_archives(fixture)

    def test_msbuild_builder_failure_prevents_each_consumer(self):
        for consumer in CONSUMERS:
            with self.subTest(consumer=consumer):
                fixture = self.fixture(consumer)
                result = self.msbuild(fixture, consumer, mode="failure")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual([event["phase"] for event in self.events(fixture)], ["acquire", "embuilder"])
                self.assert_builder(fixture)

    def test_msbuild_wrong_width_prevents_each_consumer(self):
        for consumer in CONSUMERS:
            with self.subTest(consumer=consumer):
                fixture = self.fixture(consumer)
                result = self.msbuild(fixture, consumer, mode="wasm32")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("wasm32", result.stdout + result.stderr)
                self.assertEqual([event["phase"] for event in self.events(fixture)], ["acquire", "embuilder"])

    def test_msbuild_wasm32_consumers_do_not_prepare_memory64_cache(self):
        for consumer in CONSUMERS:
            with self.subTest(consumer=consumer):
                fixture = self.fixture(consumer)
                result = self.msbuild(fixture, consumer, architecture="wasm")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual([event["phase"] for event in self.events(fixture)], ["acquire", "consumer"])
                self.assertFalse(fixture["cache"].exists())


if __name__ == "__main__":
    unittest.main()
