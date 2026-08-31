from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate_b = load_module("phase9_gate_b", ROOT / "runner/verify_phase9_gate_b.py")


class GateBExactMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allowlist_path = ROOT / "data_manifest/native_entry_allowlist.run33376110507.json"
        cls.allowlist = json.loads(cls.allowlist_path.read_text(encoding="utf-8"))
        cls.evidence = ROOT / "results/s1b-run-33376110507"

    def write_allowlist(self, value):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "allowlist.json"
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.addCleanup(directory.cleanup)
        return path

    def assert_rejected(self, mutate):
        value = copy.deepcopy(self.allowlist)
        mutate(value)
        with self.assertRaises(gate_b.GateBError):
            gate_b.validate_allowlist(self.write_allowlist(value), self.evidence)

    def test_frozen_run2_inventory_is_an_exact_match(self):
        result = gate_b.validate_allowlist(self.allowlist_path, self.evidence)
        self.assertEqual(result["status"], "GATE_B_EXACT_MATCH_PASS_ACQUISITION_BLOCKED")
        self.assertEqual(result["source_run_id"], 33376110507)
        self.assertEqual(result["native_archive_count"], 2)
        self.assertEqual(result["native_entry_count"], 28)
        self.assertFalse(result["artifact_zip_verified"])
        self.assertFalse(result["acquisition_authorized"])
        self.assertEqual(result["phase9_price_files_acquired"], 0)
        self.assertFalse(result["research_outcomes_calculated"])
        self.assertEqual(result["outcome_fields"], [])

    def test_source_anchors_are_exact(self):
        self.assertEqual(gate_b.sha256_file(self.allowlist_path), gate_b.EXPECTED_ALLOWLIST_SHA256)
        self.assertEqual(self.allowlist["source_evidence"], gate_b.EXPECTED_SOURCE_ANCHORS)
        self.assertEqual(self.allowlist["source_evidence"]["head_sha"], "951c38aaa875180fa7dbbe498866a4e3ece50e9c")
        self.assertEqual(
            self.allowlist["source_evidence"]["locked_jar_manifest_sha256"],
            "8a6fca0cf65d80fc7ca0459ff56cf35ec6f92fe89b8f516de7bc8905ab941aeb",
        )
        self.assertEqual(
            self.allowlist["source_evidence"]["artifact_zip_sha256"],
            "ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a",
        )

    def test_every_entry_has_explicit_os_arch_and_reviewed_format(self):
        entries = [entry for archive in self.allowlist["archives"] for entry in archive["entries"]]
        self.assertEqual(len(entries), 28)
        self.assertTrue(all(entry["target_os"] != "unknown" for entry in entries))
        self.assertTrue(all(entry["target_arches"] for entry in entries))
        self.assertTrue(all("unknown" not in entry["target_arches"] for entry in entries))
        self.assertTrue(all(entry["reviewed_binary_format"] for entry in entries))
        suffix_only = [entry for entry in entries if entry["magic"] is None]
        self.assertEqual(len(suffix_only), 1)
        self.assertEqual(suffix_only[0]["target_os"], "aix")
        self.assertEqual(suffix_only[0]["target_arches"], ["ppc64"])
        self.assertEqual(suffix_only[0]["reviewed_binary_format"], "XCOFF64")

    def test_reviewed_target_fields_are_immutable(self):
        mutations = (
            lambda entry: entry.__setitem__("target_os", "linux"),
            lambda entry: entry.__setitem__("target_arches", ["x86_64"]),
            lambda entry: entry.__setitem__("reviewed_binary_format", "NOT_A_REAL_FORMAT"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_rejected(lambda value, mutation=mutation: mutation(value["archives"][0]["entries"][1]))

    def test_scope_freeze_date_and_blockers_are_immutable(self):
        mutations = (
            lambda value: value["scope"].__setitem__("native_execution_allowed", True),
            lambda value: value["scope"].__setitem__("market_or_jnlp_access_allowed", True),
            lambda value: value.__setitem__("frozen_at", "2026-09-01"),
            lambda value: value.__setitem__("remaining_blockers", []),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_rejected(mutation)

    def test_unknown_archive_is_rejected(self):
        self.assert_rejected(lambda value: value["archives"][0].__setitem__("path", "locked-jar/unknown.jar"))

    def test_additional_entry_is_rejected(self):
        def mutate(value):
            extra = copy.deepcopy(value["archives"][0]["entries"][0])
            extra["entry"] = "aix/ppc64/additional.so"
            value["archives"][0]["entries"].append(extra)
            value["archives"][0]["entry_count"] += 1

        self.assert_rejected(mutate)

    def test_missing_entry_is_rejected(self):
        def mutate(value):
            value["archives"][0]["entries"].pop()
            value["archives"][0]["entry_count"] -= 1

        self.assert_rejected(mutate)

    def test_duplicate_entry_is_rejected(self):
        def mutate(value):
            value["archives"][0]["entries"].append(copy.deepcopy(value["archives"][0]["entries"][0]))
            value["archives"][0]["entry_count"] += 1

        self.assert_rejected(mutate)

    def test_case_collision_is_rejected(self):
        def mutate(value):
            extra = copy.deepcopy(value["archives"][0]["entries"][0])
            extra["entry"] = extra["entry"].upper()
            value["archives"][0]["entries"].append(extra)
            value["archives"][0]["entry_count"] += 1

        self.assert_rejected(mutate)

    def test_sha_size_magic_and_target_mutations_are_rejected(self):
        mutations = (
            lambda entry: entry.__setitem__("entry_sha256", "0" * 64),
            lambda entry: entry.__setitem__("entry_size", entry["entry_size"] + 1),
            lambda entry: entry.__setitem__("magic", "PE"),
            lambda entry: entry.__setitem__("target_os", "unknown"),
            lambda entry: entry.__setitem__("target_arches", ["unknown"]),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_rejected(lambda value, mutation=mutation: mutation(value["archives"][0]["entries"][1]))

    def test_gate_b_cannot_flip_any_authorization(self):
        for field in gate_b.FALSE_AUTHORIZATION_FIELDS:
            with self.subTest(field=field):
                self.assert_rejected(lambda value, field=field: value["authorization_state"].__setitem__(field, True))

    def test_committed_audit_and_session_state_remain_blocked(self):
        audit = json.loads(
            (ROOT / "results/gate-b-native-allowlist/GATE_B_AUDIT.json").read_text(encoding="utf-8")
        )
        self.assertEqual(audit["conclusion"], "GATE_B_EXACT_MATCH_PASS_ACQUISITION_BLOCKED")
        self.assertEqual(audit["native_inventory"]["entry_count"], 28)
        self.assertFalse(audit["implementation"]["same_run_inventory_self_authorization_used"])
        self.assertTrue(all(value is False for field, value in audit["authorization_state"].items() if field in gate_b.FALSE_AUTHORIZATION_FIELDS))
        self.assertEqual(audit["authorization_state"]["phase9_price_files_acquired"], 0)
        self.assertFalse(audit["authorization_state"]["research_outcomes_calculated"])
        self.assertEqual(audit["authorization_state"]["outcome_fields"], [])
        state = json.loads((ROOT / "SESSION_STATE.json").read_text(encoding="utf-8"))
        self.assertFalse(state["provider_acquisition"]["gate_b_native_allowlist"]["acquisition_authorized"])
        self.assertEqual(state["provider_acquisition"]["phase9_price_files_acquired"], 0)
        self.assertFalse(state["phase9"]["outcome_accessed"])

    def test_fail_closed_rule_cannot_be_removed_or_disabled(self):
        key = "same_run_inventory_self_authorization_prohibited"
        self.assert_rejected(lambda value: value["fail_closed_rules"].__setitem__(key, False))
        self.assert_rejected(lambda value: value["fail_closed_rules"].pop(key))

    def test_artifact_zip_validator_rejects_wrong_sha_and_extra_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("unexpected.txt", b"x")
            with self.assertRaises(gate_b.GateBError):
                gate_b.validate_artifact_zip(path, "0" * 64)
            with self.assertRaises(gate_b.GateBError):
                gate_b.validate_artifact_zip(path, gate_b.sha256_file(path))

    def test_artifact_manifest_and_payload_hashes_are_independently_anchored(self):
        self.assertEqual(
            gate_b.sha256_file(self.evidence / "artifact_manifest_sha256.txt"),
            gate_b.EXPECTED_ARTIFACT_MANIFEST_SHA256,
        )
        self.assertEqual(
            gate_b.parse_sha_manifest(self.evidence / "artifact_manifest_sha256.txt"),
            gate_b.EXPECTED_ARTIFACT_PAYLOAD_SHA256,
        )

    def test_inventory_and_manifest_co_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "evidence"
            shutil.copytree(self.evidence, copied)
            inventory_path = copied / "native_library_inventory.json"
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["native_entries"][0]["entry_sha256"] = "0" * 64
            inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            manifest_path = copied / "artifact_manifest_sha256.txt"
            manifest = gate_b.parse_sha_manifest(manifest_path)
            manifest["native_library_inventory.json"] = gate_b.sha256_file(inventory_path)
            manifest_path.write_text(
                "".join(f"{digest}  {name}\n" for name, digest in sorted(manifest.items())),
                encoding="utf-8",
            )
            with self.assertRaises(gate_b.GateBError):
                gate_b.validate_allowlist(self.allowlist_path, copied)

    def test_checker_has_no_network_process_or_market_runtime(self):
        source = (ROOT / "runner/verify_phase9_gate_b.py").read_text(encoding="utf-8")
        for prohibited in (
            "urllib",
            "requests",
            "socket",
            "subprocess",
            "DUKASCOPY_USERNAME",
            "DUKASCOPY_PASSWORD",
            "client.connect",
            "downloadData",
            "startStrategy",
            "Phase9JForexAcquirer",
        ):
            self.assertNotIn(prohibited, source)


if __name__ == "__main__":
    unittest.main()
