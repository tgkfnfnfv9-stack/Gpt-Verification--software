from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_count_only_v3.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v3.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch3-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_count_only_v3_tests", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def bar(at: datetime, open_value: float, close_value: float, padding: float = 0.2) -> module.Bar:
    return module.Bar(
        at, open_value, max(open_value, close_value) + padding,
        min(open_value, close_value) - padding, close_value,
    )


class BlindMtfBatch3CountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_freezes_four_independent_mechanisms_without_rescue(self):
        value = module.load_contract(CONTRACT)
        self.assertEqual(tuple(value["candidates"]), module.CANDIDATES)
        self.assertEqual(
            {row["mechanism_family"] for row in value["mechanism_independence"].values()},
            {
                "OVEREXTENSION_MEAN_REVERSION",
                "ACCEPTED_BREAKOUT_FAILURE_REVERSAL",
                "FIXED_UTC_SESSION_EFFECT",
                "CROSS_PAIR_SYNCHRONIZED_BREADTH",
            },
        )
        self.assertFalse(value["selection_integrity"]["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"])
        self.assertFalse(value["selection_integrity"]["batch3_count_or_outcome_viewed_before_freeze"])
        self.assertTrue(value["selection_integrity"]["future_return_familywise_correction_must_include_prior_three_outcome_candidates"])
        self.assertEqual(value["candidates"]["EXP-P9-MTF-312"]["frequency_gate_unit"], "SYNCHRONIZED_UTC_DATE_PLUS_DIRECTION")
        self.assertFalse(value["candidates"]["EXP-P9-MTF-312"]["instrument_breadth_gate_applicable"])

    def test_d1_overextension_exhaustion_recapture_is_detected(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        d1 = [bar(start + timedelta(days=i), 100.0, 100.0) for i in range(39)]
        d1.append(bar(start + timedelta(days=39), 100.0, 105.0, 0.2))
        available = start + timedelta(days=40)
        h4 = [bar(available - timedelta(hours=4 * (16 - i)), 105.0, 105.0) for i in range(16)]
        h4.append(module.Bar(available, 105.0, 107.5, 104.9, 106.0))
        confirm_at = available + timedelta(hours=4)
        h1 = [bar(confirm_at - timedelta(hours=16 - i), 106.0, 106.0) for i in range(16)]
        h1.extend([bar(confirm_at, 106.5, 105.0, 0.1), bar(confirm_at + timedelta(hours=1), 105.0, 105.0)])
        rules = self.contract["candidates"]["EXP-P9-MTF-309"]
        signals = module.scan_309("EURUSD", d1, h4, h1, rules)
        self.assertTrue(any(row.direction == "SHORT" for row in signals))

    def test_accepted_h4_break_then_failure_and_m15_reversal_is_detected(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        h4 = [bar(start + timedelta(hours=4 * i), 100.0, 100.0) for i in range(30)]
        break_at = start + timedelta(hours=4 * 30)
        h4.extend([
            bar(break_at, 100.0, 101.0, 0.1),
            bar(break_at + timedelta(hours=4), 101.0, 100.0, 0.1),
        ])
        confirm_at = break_at + timedelta(hours=8)
        m15 = [bar(confirm_at - timedelta(minutes=15 * (16 - i)), 100.4, 100.4, 0.1) for i in range(16)]
        m15.extend([bar(confirm_at, 100.4, 100.0, 0.05), bar(confirm_at + timedelta(minutes=15), 100.0, 100.0, 0.05)])
        rules = self.contract["candidates"]["EXP-P9-MTF-310"]
        signals = module.scan_310("EURUSD", h4, m15, rules)
        self.assertTrue(any(row.direction == "SHORT" for row in signals))

    def test_fixed_session_scanner_never_uses_another_h1_hour(self):
        rules = self.contract["candidates"]["EXP-P9-MTF-311"]
        start = datetime(2017, 1, 1, tzinfo=UTC)
        h4 = [bar(start + timedelta(hours=4 * i), 100.0 + i * 0.1, 100.1 + i * 0.1) for i in range(70)]
        h1_start = datetime(2017, 1, 11, 0, tzinfo=UTC)
        h1 = [bar(h1_start + timedelta(hours=i), 107.0, 107.0, 0.4) for i in range(40)]
        h1[37] = bar(h1[37].timestamp, 107.0, 107.8, 0.05)
        signals = module.scan_311("EURUSD", h1, h4, rules)
        self.assertTrue(signals)
        self.assertTrue(all(row.signal_time.hour == 14 for row in signals))

    def test_cross_pair_breadth_uses_other_pairs_and_can_confirm_target(self):
        rules = self.contract["candidates"]["EXP-P9-MTF-312"]
        start = datetime(2017, 1, 1, tzinfo=UTC)
        slopes = {
            "AUDJPY": 0.20, "AUDUSD": 0.20, "EURGBP": 0.05, "EURJPY": 0.15,
            "EURUSD": 0.20, "GBPJPY": 0.15, "GBPUSD": 0.20, "USDJPY": -0.20,
        }
        series = {}
        for symbol, slope in slopes.items():
            rows = []
            for index in range(20):
                open_value = 100.0 + slope * index
                rows.append(bar(start + timedelta(hours=index), open_value, open_value + slope * 0.8, 0.05))
            series[symbol] = rows
        signals = module.scan_312(series, rules)
        self.assertTrue(any(row.symbol == "AUDUSD" and row.direction == "LONG" for row in signals))

    def test_report_rejects_any_prohibited_metric_field_or_price_persistence(self):
        rows = [{"strategy_id": candidate, "exploratory_frequency_pass": False} for candidate in module.CANDIDATES]
        report = {
            "strategy_results": rows,
            "frequency_pass_candidates": [],
            "return_calculated": False,
            "research_outcomes_calculated": False,
            "outcome_fields": [],
            "persistent_price_files_after_cleanup": 0,
            "formal_phase9_authorization_effect": False,
            "prior_candidate_rescue_performed": False,
            "result_dependent_rule_change": False,
        }
        module.validate_report(report)
        report["profit_factor"] = 1.1
        with self.assertRaises(Exception):
            module.validate_report(report)
        del report["profit_factor"]
        report["persistent_price_files_after_cleanup"] = 1
        with self.assertRaises(module.Batch3CountError):
            module.validate_report(report)

    def test_workflow_is_manual_single_use_count_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn(module.OUTPUT, text)
        self.assertIn(hashlib.sha256(CONTRACT.read_bytes()).hexdigest(), text)
        self.assertIn(hashlib.sha256(RUNNER.read_bytes()).hexdigest(), text)
        self.assertNotIn("schedule:", text)


if __name__ == "__main__":
    unittest.main()
