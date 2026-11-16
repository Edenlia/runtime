#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Exercise the ICU archive boundary with real wasm32, wasm64 and host objects.

These fixtures deliberately contain placeholder data/header files. A successful
fixture tests the archive verifier, not an ICU build or ICU API execution.
"""

import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "build-memory64-icu.py"
SPEC = importlib.util.spec_from_file_location("memory64_icu", SCRIPT)
ICU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ICU)


class Memory64IcuVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sdk_path = os.environ.get("EMSDK_PATH")
        if not sdk_path:
            raise RuntimeError("Set EMSDK_PATH to the repository-pinned SDK; these tests require real LLVM tools.")
        cls.sdk = Path(sdk_path).resolve()
        cls.temporary = tempfile.TemporaryDirectory(prefix="memory64-icu-tests-")
        cls.root = Path(cls.temporary.name)
        source = cls.root / "fixture.c"
        source.write_text("int icu_archive_boundary_fixture(void) { return 7; }\n")
        cls.objects = {}
        for name, target in (("wasm32", "wasm32-unknown-emscripten"),
                             ("wasm64", "wasm64-unknown-emscripten"),
                             ("host", "x86_64-unknown-linux-gnu")):
            output = cls.root / (name + ".o")
            subprocess.run([str(ICU.sdk_tool(cls.sdk, "clang")), "--target=" + target,
                            "-c", str(source), "-o", str(output)], check=True,
                           capture_output=True, text=True)
            cls.objects[name] = output
        bitcode = cls.root / "bitcode.bc"
        subprocess.run([str(ICU.sdk_tool(cls.sdk, "clang")), "--target=wasm64-unknown-emscripten",
                        "-emit-llvm", "-c", str(source), "-o", str(bitcode)], check=True,
                       capture_output=True, text=True)
        cls.objects["bitcode"] = bitcode
        unknown = cls.root / "unknown.txt"
        unknown.write_text("not an object\n")
        cls.objects["unknown"] = unknown

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.directory = self.root / self._testMethodName
        (self.directory / "lib").mkdir(parents=True)
        (self.directory / "include/unicode").mkdir(parents=True)
        (self.directory / "include/unicode/uversion.h").write_text("fixture\n")
        for name in ICU.DATA:
            (self.directory / "lib" / name).write_bytes(b"fixture data\n")

    def archives(self, members):
        for name in ICU.ARCHIVES:
            subprocess.run([str(ICU.sdk_tool(self.sdk, "llvm-ar")), "rcs",
                            str(self.directory / "lib" / name),
                            *[str(self.objects[member]) for member in members]],
                           check=True, capture_output=True, text=True)

    def test_accepts_all_wasm64_members(self):
        self.archives(["wasm64"])
        files = ICU.verify_icu(self.directory, self.sdk)
        self.assertEqual([files[name]["wasm64_members"] for name in ICU.ARCHIVES], [1, 1, 1])

    def test_rejects_wasm32(self):
        self.archives(["wasm32"])
        with self.assertRaisesRegex(RuntimeError, "expected only wasm64.*wasm32"):
            ICU.verify_icu(self.directory, self.sdk)

    def test_rejects_mixed_width_archive(self):
        self.archives(["wasm64", "wasm32"])
        with self.assertRaisesRegex(RuntimeError, "expected only wasm64.*wasm32"):
            ICU.verify_icu(self.directory, self.sdk)

    def test_rejects_host_archive(self):
        self.archives(["host"])
        with self.assertRaisesRegex(RuntimeError, "expected only wasm64"):
            ICU.verify_icu(self.directory, self.sdk)

    def test_rejects_empty_archive(self):
        self.archives([])
        with self.assertRaisesRegex(RuntimeError, "no recognized objects"):
            ICU.verify_icu(self.directory, self.sdk)

    def test_rejects_silently_unrecognized_bitcode_member(self):
        self.archives(["wasm64", "bitcode"])
        with self.assertRaisesRegex(RuntimeError, "recognized 1 of 2 members"):
            ICU.verify_icu(self.directory, self.sdk)

    def test_rejects_silently_unrecognized_unknown_member(self):
        self.archives(["wasm64", "unknown"])
        with self.assertRaisesRegex(RuntimeError, "recognized 1 of 2 members"):
            ICU.verify_icu(self.directory, self.sdk)

    def test_rejects_incomplete_layout(self):
        self.archives(["wasm64"])
        (self.directory / "lib" / ICU.DATA[0]).unlink()
        with self.assertRaisesRegex(RuntimeError, "Incomplete Memory64 ICU dependency"):
            ICU.verify_icu(self.directory, self.sdk)

    def test_refuses_stock_sdk_cache(self):
        with self.assertRaisesRegex(RuntimeError, "separate Memory64"):
            ICU.sdk_environment(self.sdk, self.sdk / "emscripten/cache", 2)

    def test_rejects_additional_target_flags(self):
        with patch.dict(os.environ, {"EMCC_CFLAGS": "-pthread"}):
            with self.assertRaisesRegex(RuntimeError, "Unset EMCC_CFLAGS"):
                ICU.sdk_environment(self.sdk, self.directory / "system-cache", 2)

    def test_rejects_archive_link(self):
        archive = self.directory / "link.tar"
        with tarfile.open(archive, "w") as output:
            link = tarfile.TarInfo("icu/redirect")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            output.addfile(link)
        with self.assertRaisesRegex(RuntimeError, "Unexpected ICU archive member"):
            ICU.extract_source(archive, self.directory / "source")

    def test_rejects_archive_path_escape(self):
        archive = self.directory / "escape.tar"
        with tarfile.open(archive, "w") as output:
            member = tarfile.TarInfo("../outside")
            member.size = 1
            output.addfile(member, io.BytesIO(b"x"))
        with self.assertRaisesRegex(RuntimeError, "Unexpected ICU archive member"):
            ICU.extract_source(archive, self.directory / "source")
        self.assertFalse((self.directory / "outside").exists())


if __name__ == "__main__":
    unittest.main()
