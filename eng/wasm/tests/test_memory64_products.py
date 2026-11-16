#!/usr/bin/env python3
# Licensed to the .NET Foundation under one or more agreements.
# The .NET Foundation licenses this file to you under the MIT license.

"""Real LLVM/Node fixtures for the product inspector; no CoreCLR guest is executed."""

import importlib.util
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("memory64_products", Path(__file__).with_name("check_memory64_products.py"))
PRODUCTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRODUCTS)


class Memory64ProductInspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("EMSDK_PATH"):
            raise RuntimeError("Set EMSDK_PATH to the selected SDK; these tests need real LLVM tools.")
        cls.sdk = Path(os.environ["EMSDK_PATH"]).resolve()
        cls.temporary = tempfile.TemporaryDirectory(prefix="memory64-product-fixtures-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.node = Path(os.environ.get("WASM_PRODUCT_NODE", str(cls.sdk / "node/bin/node")))
        source = cls.root / "fixture.c"
        source.write_text("typedef long (*callback)(long);\nlong indirect(callback target, long value) { return target(value); }\n")
        cls.objects = {}
        cls.modules = {}
        for arch in ("wasm32", "wasm64"):
            output = cls.root / (arch + ".o")
            cls.run_tool([cls.sdk / "bin/clang", "--target=" + arch + "-unknown-emscripten",
                          "-O1", "-c", source, "-o", output])
            cls.objects[arch] = output
            module = cls.root / (arch + ".wasm")
            cls.run_tool([cls.sdk / "bin/wasm-ld", "-m" + arch, "--no-entry", "--export=indirect",
                          "--export-memory", output, "-o", module])
            cls.modules[arch] = module
        cls.bitcode = cls.root / "wasm64.bc"
        cls.run_tool([cls.sdk / "bin/clang", "--target=wasm64-unknown-emscripten",
                      "-emit-llvm", "-c", source, "-o", cls.bitcode])

    @staticmethod
    def run_tool(command):
        return subprocess.run(list(map(str, command)), check=True, capture_output=True, text=True)

    def setUp(self):
        self.work = self.root / self._testMethodName
        self.work.mkdir()

    def archive(self, members):
        output = self.work / "fixture.a"
        self.run_tool([self.sdk / "bin/llvm-ar", "qc", output, *members])
        return output

    def test_accepts_actual_wasm64_archive_members(self):
        result = PRODUCTS.verify_archive(self.archive([self.objects["wasm64"]]), self.sdk)
        self.assertEqual(result["member_types"], {"wasm64_objects": 1})

    def test_rejects_actual_wasm32_archive_members(self):
        with self.assertRaisesRegex(RuntimeError, "expected wasm64 object.*wasm32"):
            PRODUCTS.verify_archive(self.archive([self.objects["wasm32"]]), self.sdk)

    def test_rejects_mixed_width_archive(self):
        with self.assertRaisesRegex(RuntimeError, "expected wasm64 object.*wasm32"):
            PRODUCTS.verify_archive(self.archive(list(self.objects.values())), self.sdk)

    def test_duplicate_name_cannot_hide_wrong_width_member(self):
        wrong = self.work / "first/same.o"
        right = self.work / "second/same.o"
        wrong.parent.mkdir()
        right.parent.mkdir()
        shutil.copy2(self.objects["wasm32"], wrong)
        shutil.copy2(self.objects["wasm64"], right)
        with self.assertRaisesRegex(RuntimeError, r"same.o#1.*expected wasm64 object.*wasm32"):
            PRODUCTS.verify_archive(self.archive([wrong, right]), self.sdk)

    def test_unknown_member_cannot_be_silently_skipped(self):
        unknown = self.work / "unknown.o"
        unknown.write_bytes(b"unrecognized object fixture\n")
        with self.assertRaisesRegex(RuntimeError, "neither a Wasm64 object nor LLVM bitcode"):
            PRODUCTS.verify_archive(self.archive([self.objects["wasm64"], unknown]), self.sdk)

    def test_final_linked_module_is_not_an_archive_object(self):
        with self.assertRaisesRegex(RuntimeError, "expected relocatable Wasm linking metadata"):
            PRODUCTS.verify_archive(self.archive([self.modules["wasm64"]]), self.sdk)

    def test_bitcode_is_blocked_without_a_matching_reader(self):
        with self.assertRaisesRegex(PRODUCTS.Blocked, "LLVM bitcode needs --llvm-dis"):
            PRODUCTS.verify_archive(self.archive([self.bitcode]), self.sdk)

    def test_rejects_empty_archive(self):
        with self.assertRaisesRegex(RuntimeError, "no object members"):
            PRODUCTS.verify_archive(self.archive([]), self.sdk)

    def test_rejects_missing_product(self):
        with self.assertRaisesRegex(RuntimeError, "Missing or empty product"):
            PRODUCTS.verify_archive(self.work / "missing.a", self.sdk)

    def test_actual_module_is_memory64_table64_and_independently_validated(self):
        result = PRODUCTS.verify_module(self.modules["wasm64"], self.sdk, self.node, [])
        self.assertEqual([memory["address_bits"] for memory in result["memories"]], [64])
        self.assertEqual([table["address_bits"] for table in result["tables"]], [64])
        self.assertFalse(result["guest_instantiated"])
        self.assertFalse(result["guest_executed"])

    def test_actual_wasm32_module_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "expected Memory64 and table64"):
            PRODUCTS.module_address_types(self.modules["wasm32"])

    def test_memory64_does_not_imply_table64(self):
        module = self.work / "mixed-address-types.wasm"
        module.write_bytes(b"\0asm\x01\0\0\0\x04\x04\x01\x70\x00\x01\x05\x03\x01\x04\x01")
        with self.assertRaisesRegex(RuntimeError, "expected Memory64 and table64"):
            PRODUCTS.module_address_types(module)

    def test_wrong_kit_marker_is_rejected_before_archive_validation(self):
        (self.work / "target-architecture.txt").write_text("wasm\n")
        with self.assertRaisesRegex(RuntimeError, "does not target wasm64"):
            PRODUCTS.verify_kit(self.work, self.sdk)

    def test_marker_cannot_hide_wrong_width_kit_archive(self):
        self.prepare_kit()
        self.archive([self.objects["wasm32"]]).rename(self.work / "libcorerun_static.a")
        with self.assertRaisesRegex(RuntimeError, "expected wasm64 object.*wasm32"):
            PRODUCTS.verify_kit(self.work, self.sdk)

    def prepare_kit(self):
        (self.work / "target-architecture.txt").write_text("wasm64\n")
        for name in ("corerun-link.rsp", "corerun-compile-user.rsp"):
            (self.work / name).write_text("-m64\n")
        (self.work / "corerun-compile.rsp").write_text(
            "-m64\n-DTARGET_WASM\n-DTARGET_WASM64\n-DTARGET_64BIT\n-DTARGET_POINTER_SIZE=8\n")

    def test_missing_host_archive_is_rejected(self):
        self.prepare_kit()
        self.archive([self.objects["wasm64"]])
        with self.assertRaisesRegex(RuntimeError, "missing libcorerun_static.a"):
            PRODUCTS.verify_kit(self.work, self.sdk)

    def test_missing_runtime_copy_is_rejected(self):
        self.prepare_kit()
        runtime = self.archive([self.objects["wasm64"]])
        shutil.copy2(runtime, self.work / "libcorerun_static.a")
        (self.work / "products").mkdir()
        runtime = runtime.rename(self.work / "products/libcoreclr_static.a")
        kit = PRODUCTS.verify_kit(self.work, self.sdk)
        with self.assertRaisesRegex(RuntimeError, "missing the selected runtime archive copy"):
            PRODUCTS.verify_runtime_kit_copies([PRODUCTS.verify_archive(runtime, self.sdk)], kit)

    def producer_evidence(self):
        patch = self.work / "producer.patch"
        patch.write_text("producer metadata fixture; no patched compilation is performed\n")
        repository = Path(__file__).resolve().parents[3]
        identity = lambda path: {"path": str(path), "sha256": PRODUCTS.ICU.sha256(path)}
        return {"build_lane": "patched", "build_status": "success", "source_repo": str(repository),
                "source_revision": self.run_tool(["git", "-C", repository, "rev-parse", "HEAD"]).stdout.strip(),
                "patch": identity(patch), "tools": {"compiler": identity(self.sdk / "bin/clang"),
                "assembler": identity(self.sdk / "bin/wasm-ld")}, "command": ["metadata-fixture-only"]}

    def test_empty_patched_evidence_is_rejected(self):
        evidence = self.work / "producer.json"
        evidence.write_text("{}\n")
        with self.assertRaisesRegex(RuntimeError, "patched evidence needs"):
            PRODUCTS.verify_toolchain_evidence(evidence, "patched")

    def test_patched_tool_hash_must_match_actual_file(self):
        record = self.producer_evidence()
        record["tools"]["compiler"]["sha256"] = "0" * 64
        evidence = self.work / "producer.json"
        evidence.write_text(json.dumps(record))
        with self.assertRaisesRegex(RuntimeError, "producer file SHA256 changed"):
            PRODUCTS.verify_toolchain_evidence(evidence, "patched")

    def test_prepared_build_is_not_completed_producer_evidence(self):
        record = self.producer_evidence()
        record["build_status"] = "prepared"
        evidence = self.work / "producer.json"
        evidence.write_text(json.dumps(record))
        with self.assertRaisesRegex(RuntimeError, "does not record a successful patched build"):
            PRODUCTS.verify_toolchain_evidence(evidence, "patched")

    def test_patched_source_revision_must_match_checkout(self):
        record = self.producer_evidence()
        record["source_revision"] = "0" * 40
        evidence = self.work / "producer.json"
        evidence.write_text(json.dumps(record))
        with self.assertRaisesRegex(RuntimeError, "source revision does not match"):
            PRODUCTS.verify_toolchain_evidence(evidence, "patched")

    def icu_manifest_fixture(self):
        directory = self.work / "icu"
        (directory / "lib").mkdir(parents=True)
        (directory / "include/unicode").mkdir(parents=True)
        (directory / "include/unicode/uversion.h").write_text("metadata fixture, not an ICU build\n")
        for name in PRODUCTS.ICU.ARCHIVES:
            self.run_tool([self.sdk / "bin/llvm-ar", "qc", directory / "lib" / name, self.objects["wasm64"]])
        for name in PRODUCTS.ICU.DATA:
            (directory / "lib" / name).write_bytes(b"metadata fixture\n")
        identity = {"icu_commit": PRODUCTS.ICU.ICU_COMMIT, "icu_version": PRODUCTS.ICU.ICU_VERSION,
                    "source_archive_sha256": PRODUCTS.ICU.ICU_ARCHIVE_SHA256,
                    "recipe_version": PRODUCTS.ICU.RECIPE_VERSION, "pointer_size": 8,
                    "emcc_version": "metadata-fixture-only", "clang_sha256": PRODUCTS.ICU.sha256(self.sdk / "bin/clang"),
                    "wasm_ld_sha256": PRODUCTS.ICU.sha256(self.sdk / "bin/wasm-ld")}
        with contextlib.redirect_stdout(io.StringIO()):
            files = PRODUCTS.ICU.verify_icu(directory, self.sdk)
        return directory, {**identity, "target": "browser-wasm64", "emsdk_path": str(self.sdk),
                           "command": ["metadata-fixture-only"], "files": files,
                           "fingerprint": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()}

    def test_incomplete_icu_identity_cannot_be_rehashed_into_acceptance(self):
        directory, record = self.icu_manifest_fixture()
        record["clang_sha256"] = None
        identity_keys = ("icu_commit", "icu_version", "source_archive_sha256", "recipe_version",
                         "pointer_size", "emcc_version", "clang_sha256", "wasm_ld_sha256")
        record["fingerprint"] = hashlib.sha256(json.dumps({key: record.get(key) for key in identity_keys}, sort_keys=True).encode()).hexdigest()
        (directory / "icu-memory64.json").write_text(json.dumps(record))
        with self.assertRaisesRegex(RuntimeError, "incomplete ICU producer identity"):
            PRODUCTS.verify_icu_manifest(directory, self.sdk)

    def test_missing_icu_producer_probe_record_is_rejected(self):
        directory, record = self.icu_manifest_fixture()
        (directory / "icu-memory64.json").write_text(json.dumps(record))
        with self.assertRaisesRegex(RuntimeError, "missing successful producer Memory64 ICU probe record"):
            PRODUCTS.verify_icu_manifest(directory, self.sdk)


if __name__ == "__main__":
    unittest.main()
