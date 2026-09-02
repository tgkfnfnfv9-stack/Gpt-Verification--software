from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_batch2_return_oos.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_batch2_return_oos_v1.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch2-return-oos.yml"
RECOVERY_WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch2-return-oos-recovery.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_batch2_return_oos_tests", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def execution_bar(at: datetime, value: float) -> module.ExecutionBar:
    return module.ExecutionBar(at, value, value + 0.1, value - 0.1, value)


class BlindMtfBatch2ReturnOosTests(unittest.TestCase):
    def test_contract_selects_only_305_before_first_batch2_return(self):
        value = module.validate_contract(CONTRACT)
        self.assertEqual(tuple(value["selection_integrity"]["selected_candidates"]), module.SELECTED)
        self.assertFalse(value["selection_integrity"]["candidate_return_or_outcome_viewed_before_freeze"])
        self.assertEqual(value["selection_integrity"]["excluded_frequency_failures"], [
            "EXP-P9-MTF-306", "EXP-P9-MTF-307", "EXP-P9-MTF-308",
        ])

    def test_contract_uses_cumulative_three_candidate_bonferroni(self):
        value = module.validate_contract(CONTRACT)
        inference = value["inference"]
        self.assertEqual(inference["prior_outcome_tested_candidate_count"], 2)
        self.assertEqual(inference["cumulative_outcome_tested_candidate_count"], 3)
        self.assertAlmostEqual(inference["bonferroni_one_sided_alpha_each"], 0.05 / 3)

    def test_long_return_uses_ask_entry_bid_exit(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        mid = [module.batch2.base.Bar(start + timedelta(hours=i), 100.0, 100.5, 99.5, 100.0) for i in range(31)]
        bid = [execution_bar(start + timedelta(hours=i), 99.9) for i in range(31)]
        ask = [execution_bar(start + timedelta(hours=i), 100.1) for i in range(31)]
        bid[28] = execution_bar(start + timedelta(hours=28), 101.0)
        signal = SimpleNamespace(
            strategy_id="EXP-P9-MTF-305", symbol="EURUSD", direction="LONG",
            entry_time=start + timedelta(hours=16),
        )
        outcome = module.legacy.compute_outcome(signal, mid, bid, ask, 12)
        self.assertIsNotNone(outcome)
        self.assertAlmostEqual(outcome.r, 0.9)

    def test_bootstrap_uses_locked_stricter_alpha(self):
        start = datetime(2018, 1, 1, tzinfo=UTC)
        rows = [
            module.Outcome("EXP-P9-MTF-305", "EURUSD", "LONG", start + timedelta(days=i), 0.2)
            for i in range(20)
        ]
        alpha = 0.05 / 3
        left = module.legacy.clustered_lower_bound(rows, 500, alpha, 9305)
        right = module.legacy.clustered_lower_bound(rows, 500, alpha, 9305)
        self.assertEqual(left, right)
        self.assertAlmostEqual(left, 0.2)

    def test_report_rejects_disclosure_or_wrong_multiplicity(self):
        report = {
            "selected_candidates": ["EXP-P9-MTF-305"],
            "strategy_results": [{"strategy_id": "EXP-P9-MTF-305", "exploratory_edge_pass": False}],
            "exploratory_edge_pass_candidates": [],
            "cumulative_outcome_tested_candidate_count": 3,
            "return_calculated": True,
            "research_outcomes_calculated": True,
            "persistent_price_files_after_cleanup": 0,
            "trade_rows_in_artifact": True,
            "price_values_in_artifact": False,
            "signal_or_entry_timestamps_in_artifact": False,
            "formal_phase9_authorization_effect": False,
        }
        with self.assertRaises(module.Batch2ReturnGateError):
            module.validate_report(report)
        report["trade_rows_in_artifact"] = False
        report["cumulative_outcome_tested_candidate_count"] = 1
        with self.assertRaises(module.Batch2ReturnGateError):
            module.validate_report(report)

    def test_runner_rebuilds_305_only(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("batch2.scan_305", text)
        self.assertNotIn("batch2.scan_306", text)
        self.assertNotIn("batch2.scan_307", text)
        self.assertNotIn("batch2.scan_308", text)

    def test_workflow_is_manual_single_use_separate_return_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("EXP-P9-MTF-305", text)
        self.assertNotIn("EXP-P9-MTF-306", text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertNotIn("schedule:", text)

    def test_recovery_workflow_is_single_use_without_pending_replacement_group(self):
        text = RECOVERY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn("RECOVERY_PREOUTCOME_CANCEL", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertNotIn("concurrency:", text)
        self.assertIn("BATCH2_RETURN_PREOUTCOME_CANCELLATION_AUDIT.json", text)
        self.assertNotIn("schedule:", text)


if __name__ == "__main__":
    unittest.main()
