from __future__ import annotations

import copy
import importlib.util
import json
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


gate_c2 = load_module("phase9_gate_c2", ROOT / "runner/verify_phase9_gate_c2.py")


class GateC2ExactMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "data_manifest/runtime_mapping_allowlist.run33451221995.json"
        cls.value = json.loads(cls.path.read_text(encoding="utf-8"))

    def mutated_path(self, mutate):
        value = copy.deepcopy(self.value)
        mutate(value)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "allowlist.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path

    def assert_rejected(self, mutate):
        with self.assertRaises(gate_c2.GateC2Error):
            gate_c2.validate_allowlist(self.mutated_path(mutate))

    def test_frozen_runtime_inventory_is_exact_and_blocked(self):
        result = gate_c2.validate_allowlist(self.path)
        self.assertEqual(result["status"], "GATE_C2_EXACT_MATCH_PASS_ACQUISITION_BLOCKED")
        self.assertEqual(result["source_run_id"], 33451221995)
        self.assertEqual(result["executable_mapping_count"], 15)
        self.assertFalse(result["artifact_zip_verified"])
        self.assertFalse(result["acquisition_authorized"])
        self.assertEqual(result["phase9_price_files_acquired"], 0)
        self.assertFalse(result["research_outcomes_calculated"])
        self.assertEqual(result["outcome_fields"], [])

    def test_source_run_job_head_artifact_and_payload_hashes_are_exact(self):
        self.assertEqual(gate_c2.sha256_file(self.path), gate_c2.EXPECTED_ALLOWLIST_SHA256)
        self.assertEqual(self.value["source_evidence"], gate_c2.EXPECTED_SOURCE)
        self.assertEqual(self.value["source_evidence"]["run_id"], 33451221995)
        self.assertEqual(self.value["source_evidence"]["job_id"], 99681326258)
        self.assertEqual(
            self.value["source_evidence"]["head_sha"],
            "9699c64b9133482caf22cef07dc9b3bc2fe33a1a",
        )
        self.assertEqual(
            self.value["source_evidence"]["artifact_zip_sha256"],
            "d5ea84805732209e85340376de98788f897eba411a3170b300600767252d60f0",
        )

    def test_all_15_mapping_path_sha_size_target_tuples_are_unique(self):
        rows = self.value["executable_file_mappings"]
        self.assertEqual(len(rows), 15)
        identities = {(row["path_scope"], row["path"]) for row in rows}
        self.assertEqual(len(identities), 15)
        self.assertEqual(sum(row["path_scope"] == "GATE_C_ROOT_RELATIVE" for row in rows), 1)
        self.assertTrue(all(row["target_os"] == "linux" for row in rows))
        self.assertTrue(all(row["target_arch"] == "x86_64" for row in rows))
        self.assertTrue(all(len(row["sha256"]) == 64 for row in rows))
        self.assertTrue(all(row["bytes"] > 0 for row in rows))

    def test_unknown_additional_missing_duplicate_and_case_collision_are_rejected(self):
        self.assert_rejected(lambda value: value["executable_file_mappings"][0].__setitem__("path", "native/unknown.so"))
        self.assert_rejected(lambda value: value["executable_file_mappings"].append(copy.deepcopy(value["executable_file_mappings"][0])))
        self.assert_rejected(lambda value: value["executable_file_mappings"].pop())
        self.assert_rejected(lambda value: value["executable_file_mappings"].append(copy.deepcopy(value["executable_file_mappings"][0])))

        def collide(value):
            extra = copy.deepcopy(value["executable_file_mappings"][0])
            extra["path"] = extra["path"].upper()
            value["executable_file_mappings"].append(extra)

        self.assert_rejected(collide)

    def test_path_scope_sha_size_os_arch_and_signature_mutations_are_rejected(self):
        mutations = (
            lambda value: value["executable_file_mappings"][0].__setitem__("path_scope", "ABSOLUTE"),
            lambda value: value["executable_file_mappings"][0].__setitem__("observed_path", "/tmp/other/native/libjnidispatch.so"),
            lambda value: value["executable_file_mappings"][0].__setitem__("sha256", "0" * 64),
            lambda value: value["executable_file_mappings"][0].__setitem__("bytes", 1),
            lambda value: value["executable_file_mappings"][0].__setitem__("target_os", "unknown"),
            lambda value: value["executable_file_mappings"][0].__setitem__("target_arch", "unknown"),
            lambda value: value["observed_inert_network_syscall_signatures"].append("socket:AF_INET:SOCK_RAW:IPPROTO_RAW:SUCCESS:COUNT_1"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assert_rejected(mutation)

    def test_gate_c2_cannot_flip_authorization_or_remove_blockers(self):
        for field in gate_c2.FALSE_FIELDS:
            with self.subTest(field=field):
                self.assert_rejected(lambda value, field=field: value["authorization_state"].__setitem__(field, True))
        self.assert_rejected(lambda value: value.__setitem__("remaining_blockers", []))
        self.assert_rejected(lambda value: value["fail_closed_rules"].__setitem__("same_run_inventory_self_authorization_prohibited", False))

    def test_committed_audit_is_separate_run_and_acquisition_blocked(self):
        audit = json.loads(
            (ROOT / "results/gate-c-runtime-allowlist/GATE_C_AUDIT.json").read_text(encoding="utf-8")
        )
        self.assertEqual(audit["conclusion"], "GATE_C2_EXACT_MATCH_PASS_ACQUISITION_BLOCKED")
        self.assertFalse(audit["implementation"]["same_run_inventory_self_authorization_used"])
        self.assertEqual(audit["source_evidence"]["run_id"], 33451221995)
        self.assertFalse(audit["authorization_state"]["acquisition_authorized"])
        self.assertEqual(audit["authorization_state"]["phase9_price_files_acquired"], 0)
        self.assertEqual(audit["authorization_state"]["outcome_fields"], [])

    def test_artifact_zip_validator_rejects_wrong_or_additional_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("unexpected.txt", b"x")
            with self.assertRaises(gate_c2.GateC2Error):
                gate_c2.validate_artifact_zip(path)

    def test_artifact_payload_cross_check_rejects_mapping_signature_and_identity_changes(self):
        state = self.value["authorization_state"]
        runtime = {
            "executable_file_mapping_count": 15,
            "executable_file_mappings": [
                {"path": row["observed_path"], "sha256": row["sha256"], "bytes": row["bytes"]}
                for row in self.value["executable_file_mappings"]
            ],
            "observed_inert_network_syscall_signatures": self.value["observed_inert_network_syscall_signatures"],
            "child_process_spawned": False,
            "external_network_io_succeeded": False,
            "acquisition_authorized": False,
            "count_only_authorized": False,
            "outcomes_authorized": False,
            "phase9_price_files_acquired": 0,
            "outcome_fields": [],
            "same_run_runtime_inventory_may_authorize": False,
        }
        identity = (
            "git_sha=9699c64b9133482caf22cef07dc9b3bc2fe33a1a\n"
            "run_id=33451221995\n"
            "run_attempt=1\n"
            "runner_os=Linux\n"
            "runner_arch=X64\n"
            "image_os=ubuntu24\n"
            "image_version=20260823.283.1\n"
            "java_home=/opt/hostedtoolcache/Java_Zulu_jdk/8.0.504-1/x64\n"
            "java_sha256=fb161b5d5cafb223f1ce680eb121f04ab5ea9ca172f51053942df64cbd587e78\n"
        )
        payloads = {
            "runtime_observation.json": json.dumps(runtime).encode(),
            "authorization_state.json": json.dumps(state).encode(),
            "shaded_runner_inventory.json": json.dumps({
                "runner_sha256": self.value["scope"]["shaded_runner_sha256"],
                "acquisition_authorized": False,
                "phase9_price_files_acquired": 0,
                "outcome_fields": [],
                "same_run_inventory_may_authorize": False,
            }).encode(),
            "runtime_identity.txt": identity.encode(),
        }
        gate_c2.cross_check_artifact_payloads(payloads, self.value)
        mutations = []
        changed_mapping = copy.deepcopy(runtime)
        changed_mapping["executable_file_mappings"][0]["sha256"] = "0" * 64
        mutations.append(("runtime_observation.json", changed_mapping))
        changed_signature = copy.deepcopy(runtime)
        changed_signature["observed_inert_network_syscall_signatures"].append("socket:AF_INET:SOCK_RAW:IPPROTO_RAW:SUCCESS:COUNT_1")
        mutations.append(("runtime_observation.json", changed_signature))
        authorization = json.loads(payloads["authorization_state.json"])
        changed_authorization = copy.deepcopy(authorization)
        changed_authorization["acquisition_authorized"] = True
        mutations.append(("authorization_state.json", changed_authorization))
        for name, value in mutations:
            with self.subTest(name=name):
                changed = dict(payloads)
                changed[name] = (json.dumps(value) + "\n").encode()
                with self.assertRaises(gate_c2.GateC2Error):
                    gate_c2.cross_check_artifact_payloads(changed, self.value)

        changed = dict(payloads)
        changed["runtime_identity.txt"] = payloads["runtime_identity.txt"].replace(
            b"runner_arch=X64", b"runner_arch=ARM64"
        )
        with self.assertRaises(gate_c2.GateC2Error):
            gate_c2.cross_check_artifact_payloads(changed, self.value)

    def test_verifier_has_no_network_process_market_or_outcome_runtime(self):
        source = (ROOT / "runner/verify_phase9_gate_c2.py").read_text(encoding="utf-8")
        for prohibited in (
            "urllib", "requests", "subprocess", "DUKASCOPY_USERNAME", "DUKASCOPY_PASSWORD",
            "client.connect", "downloadData", "startStrategy", "Phase9JForexAcquirer",
            "profit_factor", "drawdown", "p_value",
        ):
            self.assertNotIn(prohibited, source)


if __name__ == "__main__":
    unittest.main()
