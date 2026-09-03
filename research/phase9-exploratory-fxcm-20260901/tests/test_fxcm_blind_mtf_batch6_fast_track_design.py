import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TRACK = Path(__file__).resolve().parents[1]
RUNNER_DIR = TRACK / "runner"
sys.path.insert(0, str(RUNNER_DIR))

import verify_fxcm_blind_mtf_batch6_fast_track_design as verifier  # noqa: E402


CONTRACT = TRACK / "spec/fxcm_blind_mtf_batch6_fast_track_design_v1.frozen.json"
VERIFY = RUNNER_DIR / "verify_fxcm_blind_mtf_batch6_fast_track_design.py"


class Batch6FastTrackDesignTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def _verify_changed_contract(self, change):
        changed = copy.deepcopy(self.contract)
        change(changed)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changed.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            verifier.verify(path, REPOSITORY_ROOT)

    def test_exact_design_passes_offline(self):
        result = verifier.verify(CONTRACT, REPOSITORY_ROOT)
        self.assertEqual(result["status"], "PASS_DESIGN_AND_PRICE_FREE_PREAUDIT_ONLY")
        self.assertEqual(result["candidate_count"], 4)
        self.assertEqual(result["route_a_archive_count"], 32)
        self.assertEqual(result["route_b_source_request_count"], 1664)
        self.assertEqual(result["final_side_series_count"], 64)
        for field in (
            "implementation_paths_present",
            "network_price_requests_performed",
            "drive_file_content_gets_performed",
            "drive_mutations_performed",
            "workflow_dispatches_performed",
            "count_analyses_performed",
            "return_or_outcome_analyses_performed",
        ):
            self.assertEqual(result[field], 0)

    def test_rejects_scope_or_boundary_change(self):
        changes = (
            lambda value: value["immutable_batch6_scope"]["candidate_ids"].pop(),
            lambda value: value["immutable_batch6_scope"]["symbols"].pop(),
            lambda value: value["immutable_batch6_scope"].__setitem__("end_exclusive", "2019-01-01T00:00:00Z"),
            lambda value: value["immutable_batch6_scope"].__setitem__("expected_archive_count_route_a", 31),
            lambda value: value["immutable_batch6_scope"].__setitem__("direction_flip_allowed", True),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(change)

    def test_rejects_provider_fallback_or_route_activation(self):
        changes = (
            lambda value: value["source_route_decision"].__setitem__("automatic_fallback_from_a_to_b", True),
            lambda value: value["source_route_decision"].__setitem__("incomplete_transaction_may_be_called_canonical_or_committed", True),
            lambda value: value["route_b_fxcm_reacquisition_design_boundary"].__setitem__("current_state", "AUTHORIZED"),
            lambda value: value["route_b_fxcm_reacquisition_design_boundary"].__setitem__("reuse_of_route_a_approval_allowed", True),
            lambda value: value["source_route_decision"].__setitem__("may_proceed_before_all_p0_findings_are_resolved", True),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(change)

    def test_rejects_drive_scope_or_count_execution_authorization(self):
        changes = (
            lambda value: value["route_a_existing_drive_design"]["gate_a1_manifest_selection"].__setitem__("archive_content_get", 1),
            lambda value: value["route_a_existing_drive_design"]["gate_a1_manifest_selection"].__setitem__("drive_mutation_allowed", True),
            lambda value: value["route_a_existing_drive_design"]["gate_a2_archive_qc_and_count"].__setitem__("archive_content_get_exact", 33),
            lambda value: value["route_a_existing_drive_design"]["gate_a2_archive_qc_and_count"].__setitem__("count_execution_authorized_at_preaudit_time", True),
            lambda value: value["route_a_existing_drive_design"]["gate_a2_archive_qc_and_count"].__setitem__("automatic_return_oos_continuation_allowed", True),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(change)

    def test_rejects_any_preaudit_authorization_or_performed_operation(self):
        for field in self.contract["authorization_at_preaudit_time"]:
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(
                    lambda value, field=field: value["authorization_at_preaudit_time"].__setitem__(field, True)
                )
        for field in self.contract["operations_performed_by_this_design_preaudit"]:
            with self.subTest(field=field), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(
                    lambda value, field=field: value["operations_performed_by_this_design_preaudit"].__setitem__(field, 1)
                )

    def test_rejects_missing_or_unknown_authorization_and_performed_keys(self):
        changes = (
            lambda value: value["authorization_at_preaudit_time"].pop("push"),
            lambda value: value["authorization_at_preaudit_time"].__setitem__("unknown_operation", False),
            lambda value: value["operations_performed_by_this_design_preaudit"].pop("push"),
            lambda value: value["operations_performed_by_this_design_preaudit"].__setitem__("unknown_operation", 0),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(change)

    def test_rejects_outcome_or_artifact_leak(self):
        changes = (
            lambda value: value["count_only_boundary"]["forbidden_calculations"].remove("FORWARD_RETURN"),
            lambda value: value["count_only_boundary"].__setitem__("return_gate_only_for_frequency_passers", False),
            lambda value: value["future_artifact_policy"].__setitem__("raw_or_derived_price_allowed", True),
            lambda value: value["future_artifact_policy"].__setitem__("event_timestamp_allowed", True),
            lambda value: value["future_artifact_policy"].__setitem__("drive_file_or_folder_id_allowed", True),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(change)

    def test_rejects_p0_removal_or_legacy_runner_activation(self):
        changes = (
            lambda value: value["price_free_preaudit_decision"]["p0_findings"].pop(),
            lambda value: value["price_free_preaudit_decision"]["p0_findings"][0].__setitem__(
                "closure_stage", "CONTROL_IMPLEMENTATION_AND_STATIC_AUDIT_AFTER_SEPARATE_APPROVAL"
            ),
            lambda value: value["price_free_preaudit_decision"]["p0_closure_model"][
                "scientific_specification_p0_ids"
            ].pop(),
            lambda value: value["price_free_preaudit_decision"]["p1_constraints"].pop(),
            lambda value: value["price_free_preaudit_decision"].__setitem__("verdict", "PASS"),
            lambda value: value["price_free_preaudit_decision"].__setitem__("old_workflow_or_runner_reuse_allowed", True),
            lambda value: value["frozen_research_anchors"]["legacy_count_runner_reference"].__setitem__("required_state", "EXECUTABLE"),
            lambda value: value["mtf_reconstruction_and_qc"].__setitem__("legacy_structural_qc_pass_may_be_claimed", True),
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(verifier.VerificationError):
                self._verify_changed_contract(change)

    def test_design_verifier_has_no_external_or_research_execution_surface(self):
        source = VERIFY.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*(?:from|import)\s+(?:urllib|requests|httpx|googleapiclient)\b", source))
        for forbidden in (
            "DUKASCOPY_PASSWORD",
            "PHASE9_GDRIVE_OAUTH_CLIENT_SECRET",
            "api.github.com",
            "drive.google.com",
            "candledata.fxcorporate.com",
            "subprocess",
        ):
            self.assertNotIn(forbidden, source)

    def test_design_gate_contains_no_new_executable_paths(self):
        implementation = self.contract["implementation_boundary"]
        for field in ("new_standalone_count_runner_path", "new_workflow_path", "new_execution_contract_path"):
            self.assertFalse((REPOSITORY_ROOT / implementation[field]).exists(), implementation[field])


if __name__ == "__main__":
    unittest.main()
