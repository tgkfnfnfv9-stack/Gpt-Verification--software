from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_batch5_return_oos.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_batch5_return_oos_v1.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch5-return-oos.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_batch5_return_oos_tests", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def execution_bar(at: datetime, value: float) -> module.ExecutionBar:
    return module.ExecutionBar(at, value, value + 0.1, value - 0.1, value)


class BlindMtfBatch5ReturnOosTests(unittest.TestCase):
    def test_contract_selects_only_319_before_first_batch5_return(self):
        value = module.validate_contract(CONTRACT)
        selection = value["selection_integrity"]
        self.assertEqual(tuple(selection["selected_candidates"]), module.SELECTED)
        self.assertFalse(selection["candidate_return_or_outcome_viewed_before_freeze"])
        self.assertFalse(selection["nonpasser_rescue_allowed"])
        self.assertEqual(selection["excluded_frequency_failures"], [
            "EXP-P9-MTF-317", "EXP-P9-MTF-318", "EXP-P9-MTF-320",
        ])
        self.assertEqual(selection["prior_outcome_tested_rejections"], [
            "EXP-P9-MTF-302", "EXP-P9-MTF-304", "EXP-P9-MTF-305",
            "EXP-P9-MTF-311", "EXP-P9-MTF-312", "EXP-P9-MTF-316",
        ])

    def test_contract_uses_cumulative_seven_candidate_bonferroni(self):
        value = module.validate_contract(CONTRACT)
        inference = value["inference"]
        self.assertEqual(inference["prior_outcome_tested_candidate_count"], 6)
        self.assertEqual(inference["new_selected_candidate_count"], 1)
        self.assertEqual(inference["cumulative_outcome_tested_candidate_count"], 7)
        self.assertEqual(inference["bonferroni_one_sided_alpha_each"], 0.05 / 7)
        self.assertEqual(value["candidate_pass_gate"]["minimum_oos_outcomes"], 220)
        self.assertTrue(value["selection_integrity"]["minimum_oos_outcomes_selected_from_count_only_not_outcome"])

    def test_long_return_uses_ask_entry_bid_exit(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        mid = [module.batch5.base.Bar(start + timedelta(hours=i), 100.0, 100.5, 99.5, 100.0) for i in range(31)]
        bid = [execution_bar(start + timedelta(hours=i), 99.9) for i in range(31)]
        ask = [execution_bar(start + timedelta(hours=i), 100.1) for i in range(31)]
        bid[28] = execution_bar(start + timedelta(hours=28), 101.0)
        signal = SimpleNamespace(strategy_id="EXP-P9-MTF-319", symbol="EURUSD", direction="LONG", entry_time=start + timedelta(hours=16))
        outcome = module.legacy.compute_outcome(signal, mid, bid, ask, 12)
        self.assertIsNotNone(outcome)
        self.assertAlmostEqual(outcome.r, 0.9)

    def test_bootstrap_uses_locked_stricter_alpha_and_seed(self):
        start = datetime(2018, 1, 1, tzinfo=UTC)
        rows = [module.Outcome("EXP-P9-MTF-319", "EURUSD", "LONG", start + timedelta(days=i), 0.2) for i in range(20)]
        left = module.legacy.clustered_lower_bound(rows, 500, 0.05 / 7, 9319)
        right = module.legacy.clustered_lower_bound(rows, 500, 0.05 / 7, 9319)
        self.assertEqual(left, right)
        self.assertAlmostEqual(left, 0.2)

    def test_report_rejects_disclosure_wrong_multiplicity_or_alpha(self):
        report = {
            "selected_candidates": list(module.SELECTED),
            "strategy_results": [{"strategy_id": "EXP-P9-MTF-319", "exploratory_edge_pass": False}],
            "exploratory_edge_pass_candidates": [],
            "cumulative_outcome_tested_candidate_count": 7,
            "bonferroni_one_sided_alpha_each": 0.05 / 7,
            "return_calculated": True,
            "research_outcomes_calculated": True,
            "persistent_price_files_after_cleanup": 0,
            "trade_rows_in_artifact": True,
            "price_values_in_artifact": False,
            "signal_or_entry_timestamps_in_artifact": False,
            "formal_phase9_authorization_effect": False,
            "nonpasser_rescue_performed": False,
            "result_dependent_rule_change": False,
        }
        with self.assertRaises(module.Batch5ReturnGateError):
            module.validate_report(report)
        report["trade_rows_in_artifact"] = False
        report["cumulative_outcome_tested_candidate_count"] = 6
        with self.assertRaises(module.Batch5ReturnGateError):
            module.validate_report(report)
        report["cumulative_outcome_tested_candidate_count"] = 7
        report["bonferroni_one_sided_alpha_each"] = 0.05
        with self.assertRaises(module.Batch5ReturnGateError):
            module.validate_report(report)

    def test_runner_rebuilds_only_319(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("batch5.scan_319", text)
        self.assertNotIn("batch5.scan_317", text)
        self.assertNotIn("batch5.scan_318", text)
        self.assertNotIn("batch5.scan_320", text)

    def test_workflow_is_manual_single_use_and_hash_locked(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("EXP-P9-MTF-319", text)
        self.assertNotIn("EXP-P9-MTF-317", text)
        self.assertNotIn("EXP-P9-MTF-318", text)
        self.assertNotIn("EXP-P9-MTF-320", text)
        self.assertNotIn("concurrency:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("Destroy all working prices before upload", text)
        for path in (CONTRACT, RUNNER):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(digest, text)


if __name__ == "__main__":
    unittest.main()
