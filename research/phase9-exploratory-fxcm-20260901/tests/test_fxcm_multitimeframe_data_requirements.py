from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "spec/fxcm_multitimeframe_data_requirements.frozen.json"


class FxcmMultiTimeframeDataRequirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_exact_mtf_scope(self):
        value = self.value
        self.assertEqual(value["provider"]["requested_direct_periodicities"], ["m1", "H1"])
        self.assertEqual(value["final_timeframes"], ["M15", "H1", "H4", "D1"])
        self.assertEqual(value["series_inventory"]["expected_final_series_count"], 64)
        self.assertEqual(value["coverage"]["expected_direct_source_object_count"], 1664)

    def test_complete_bucket_derivations_and_no_fill(self):
        rules = self.value["derivation_rules"]
        self.assertEqual(rules["M15"]["required_complete_source_bars"], 15)
        self.assertEqual(rules["H4"]["required_complete_source_bars"], 4)
        self.assertEqual(rules["D1"]["required_complete_source_bars"], 24)
        self.assertFalse(rules["forward_fill_allowed"])
        self.assertFalse(rules["price_interpolation_allowed"])

    def test_acquisition_does_not_authorize_counts_or_outcomes(self):
        gates = self.value["research_gates"]
        self.assertFalse(self.value["formal_phase9_authorization_effect"])
        self.assertFalse(gates["acquisition_run_may_calculate_signal_counts"])
        self.assertFalse(gates["acquisition_run_may_calculate_returns_or_outcomes"])
        self.assertFalse(gates["research_outcomes_calculated"])
        self.assertEqual(gates["outcome_fields"], [])

    def test_raw_prices_are_not_git_or_public_artifacts(self):
        policy = self.value["storage_policy"]
        self.assertFalse(policy["raw_or_derived_price_files_may_be_committed_to_git"])
        self.assertFalse(policy["raw_or_derived_price_files_may_be_uploaded_to_public_artifact"])


if __name__ == "__main__":
    unittest.main()
