import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "acquisition_design_v1.preaudit.json"
VERIFIER = ROOT / "runner" / "verify_price_free_acquisition_design_v1.py"

module_spec = importlib.util.spec_from_file_location("design_verifier", VERIFIER)
design_verifier = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(design_verifier)


class PriceFreeAcquisitionDesignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(SPEC.read_text(encoding="utf-8"))

    def test_offline_verifier(self):
        self.assertEqual(design_verifier.verify()["status"], "PASS")

    def test_exact_half_open_interval(self):
        self.assertEqual(self.contract["interval"]["start_inclusive"], "2022-01-01T00:00:00Z")
        self.assertEqual(self.contract["interval"]["end_exclusive"], "2026-01-01T00:00:00Z")

    def test_only_gate_one_is_complete(self):
        gates = self.contract["approval_gates"]
        self.assertEqual(gates[0]["state"], "COMPLETED_WITH_BLOCKERS")
        self.assertEqual(gates[1]["state"], "AUTHORIZED_SIMPLE_FX_IMPLEMENTATION")
        self.assertTrue(all(gate["state"] == "NOT_AUTHORIZED" for gate in gates[2:]))

    def test_all_authorizations_false(self):
        authorization = self.contract["current_authorization"]
        self.assertTrue(all(authorization[name] for name in ("fx_implementation", "fx_commit", "fx_push")))
        self.assertTrue(all(not authorization[name] for name in (
            "commodity_implementation", "commodity_commit", "commodity_push",
            "workflow_dispatch", "price_access", "oauth_token_exchange", "drive_access",
            "drive_write", "drive_content_download", "transaction_finalization", "cleanup", "research_use",
        )))

    def test_fx_counts(self):
        counts = self.contract["fx_recovery"]["counts"]
        self.assertEqual(counts["new_archives"], 200)
        self.assertEqual(counts["new_year_manifests"], 4)
        self.assertEqual(counts["frozen_present_source_identities"], 10084)
        self.assertEqual(counts["frozen_known_missing_source_identities"], 316)

    def test_commodity_counts(self):
        counts = self.contract["commodity"]["counts"]
        self.assertEqual(counts["new_archives_if_fully_available"], 112)
        self.assertEqual(counts["new_year_manifests_if_fully_available"], 14)
        self.assertEqual(counts["private_objects_to_upload_and_redownload_if_fully_available"], 126)

    def test_no_research_authority(self):
        self.assertFalse(self.contract["formal_phase9_authorization_effect"])
        self.assertFalse(self.contract["current_authorization"]["research_use"])

    def test_batch6_denylist(self):
        self.assertEqual(len(self.contract["batch6_denylist"]), 5)


if __name__ == "__main__":
    unittest.main()
