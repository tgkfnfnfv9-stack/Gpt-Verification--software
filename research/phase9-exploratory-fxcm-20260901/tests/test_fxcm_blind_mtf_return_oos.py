from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_return_oos.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_return_oos_v1.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-return-oos.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_return_oos_tests", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def execution_bar(at: datetime, value: float) -> module.ExecutionBar:
    return module.ExecutionBar(at, value, value + 0.1, value - 0.1, value)


class BlindMtfReturnOosTests(unittest.TestCase):
    def test_contract_is_frozen_after_count_before_return(self):
        value = module.validate_contract(CONTRACT)
        self.assertEqual(tuple(value["selection_integrity"]["selected_candidates"]), module.SELECTED)
        self.assertFalse(value["selection_integrity"]["candidate_return_or_outcome_viewed_before_freeze"])
        self.assertEqual(value["split"]["out_of_sample"], "2018")
        self.assertEqual(value["execution_model"]["fixed_horizon_hours"], 12)

    def test_long_return_uses_ask_entry_bid_exit_and_preentry_atr(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        mid = [module.blind.base.Bar(start + timedelta(hours=i), 100.0, 100.5, 99.5, 100.0) for i in range(31)]
        bid = [execution_bar(start + timedelta(hours=i), 99.9) for i in range(31)]
        ask = [execution_bar(start + timedelta(hours=i), 100.1) for i in range(31)]
        bid[28] = execution_bar(start + timedelta(hours=28), 101.0)
        signal = SimpleNamespace(
            strategy_id="EXP-P9-MTF-302", symbol="EURUSD", direction="LONG",
            entry_time=start + timedelta(hours=16),
        )
        outcome = module.compute_outcome(signal, mid, bid, ask, 12)
        self.assertIsNotNone(outcome)
        self.assertAlmostEqual(outcome.r, 0.9)

    def test_short_return_uses_bid_entry_ask_exit(self):
        start = datetime(2018, 1, 1, tzinfo=UTC)
        mid = [module.blind.base.Bar(start + timedelta(hours=i), 100.0, 100.5, 99.5, 100.0) for i in range(31)]
        bid = [execution_bar(start + timedelta(hours=i), 99.9) for i in range(31)]
        ask = [execution_bar(start + timedelta(hours=i), 100.1) for i in range(31)]
        bid[16] = execution_bar(start + timedelta(hours=16), 100.0)
        bid[28] = execution_bar(start + timedelta(hours=28), 98.9)
        ask[28] = execution_bar(start + timedelta(hours=28), 99.0)
        signal = SimpleNamespace(
            strategy_id="EXP-P9-MTF-304", symbol="USDJPY", direction="SHORT",
            entry_time=start + timedelta(hours=16),
        )
        outcome = module.compute_outcome(signal, mid, bid, ask, 12)
        self.assertIsNotNone(outcome)
        self.assertAlmostEqual(outcome.r, 1.0)

    def test_date_cluster_bootstrap_is_deterministic(self):
        start = datetime(2018, 1, 1, tzinfo=UTC)
        rows = [
            module.Outcome("EXP-P9-MTF-302", "EURUSD", "LONG", start + timedelta(days=i), 0.2)
            for i in range(20)
        ]
        left = module.clustered_lower_bound(rows, 500, 0.025, 9302)
        right = module.clustered_lower_bound(rows, 500, 0.025, 9302)
        self.assertEqual(left, right)
        self.assertAlmostEqual(left, 0.2)

    def test_report_rejects_trade_rows_or_price_persistence(self):
        results = [{"strategy_id": candidate, "exploratory_edge_pass": False} for candidate in module.SELECTED]
        report = {
            "strategy_results": results,
            "exploratory_edge_pass_candidates": [],
            "return_calculated": True,
            "research_outcomes_calculated": True,
            "persistent_price_files_after_cleanup": 0,
            "trade_rows_in_artifact": True,
            "price_values_in_artifact": False,
            "signal_or_entry_timestamps_in_artifact": False,
            "formal_phase9_authorization_effect": False,
        }
        with self.assertRaises(module.ReturnGateError):
            module.validate_report(report)
        report["trade_rows_in_artifact"] = False
        report["persistent_price_files_after_cleanup"] = 1
        with self.assertRaises(module.ReturnGateError):
            module.validate_report(report)

    def test_workflow_is_manual_single_use_separate_return_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("EXP-P9-MTF-302", text)
        self.assertIn("EXP-P9-MTF-304", text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertNotIn("schedule:", text)


if __name__ == "__main__":
    unittest.main()
