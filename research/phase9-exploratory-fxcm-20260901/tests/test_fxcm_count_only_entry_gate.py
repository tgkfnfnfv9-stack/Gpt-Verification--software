from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
GATE_PATH = ROOT / "spec/fxcm_count_only_entry_gate.frozen.json"


class FxcmCountOnlyEntryGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))

    def test_all_source_anchor_hashes_match_repository_files(self):
        for name, anchor in self.gate["source_anchors"].items():
            with self.subTest(anchor=name):
                payload = (REPO / anchor["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), anchor["sha256"])

    def test_original_failed_exact_reconciliation_gate_is_not_rewritten(self):
        original = self.gate["preserved_original_run"]
        adjudication = self.gate["prospective_technical_adjudication"]
        self.assertFalse(original["original_run_reclassified_as_pass"])
        self.assertFalse(original["original_exact_h1_reconciliation_gate_passed"])
        self.assertEqual(original["h1_ohlc_mismatch_count"], 4297)
        self.assertFalse(adjudication["adjudication_applies_retroactively_to_original_status"])
        self.assertEqual(adjudication["canonical_h1"], "DIRECT_H1")

    def test_two_year_fx8_data_cannot_be_called_formal_count_only(self):
        eligibility = self.gate["formal_count_only_eligibility"]
        state = self.gate["scientific_state"]
        self.assertFalse(eligibility["authorized"])
        self.assertFalse(eligibility["coverage_gate_can_pass_with_observed_interval"])
        self.assertLess(
            eligibility["maximum_registered_12_month_blocks_touched_by_observed_interval"],
            eligibility["registered_12_month_blocks_required_with_episodes"],
        )
        self.assertFalse(state["formal_count_only_authorized"])
        self.assertFalse(state["formal_phase9_authorization_effect"])

    def test_only_exact_universe_price_only_candidates_are_marked_implementable(self):
        compatible = self.gate["candidate_data_compatibility_without_counting"]
        self.assertEqual(
            [row["strategy_id"] for row in compatible["exact_fx8_price_only_candidates"]],
            ["STRAT-P9-RR-201", "STRAT-P9-RR-202"],
        )
        self.assertTrue(all(not row["formal_coverage_complete"] for row in compatible["exact_fx8_price_only_candidates"]))
        self.assertEqual(len(compatible["excluded_from_exploratory_fx8_count_only"]), 10)

    def test_gate_itself_contains_no_counts_returns_or_outcomes(self):
        state = self.gate["scientific_state"]
        self.assertFalse(state["exploratory_count_only_executed"])
        self.assertFalse(state["candidate_signal_counts_calculated"])
        self.assertFalse(state["return_calculated"])
        self.assertFalse(state["research_outcomes_calculated"])
        self.assertEqual(state["outcome_fields"], [])
        self.assertFalse(self.gate["next_route_boundary"]["automatic_count_only_continuation_allowed"])


if __name__ == "__main__":
    unittest.main()
