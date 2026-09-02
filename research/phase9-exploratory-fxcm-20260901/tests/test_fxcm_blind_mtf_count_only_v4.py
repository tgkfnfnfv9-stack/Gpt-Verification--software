from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_count_only_v4.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v4.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch4-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_count_only_v4_tests", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def bar(at: datetime, open_value: float, close_value: float, padding: float = 0.1) -> module.Bar:
    return module.Bar(
        at, open_value, max(open_value, close_value) + padding,
        min(open_value, close_value) - padding, close_value,
    )


class BlindMtfBatch4CountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_freezes_four_new_mechanisms_after_five_outcome_rejections(self):
        value = module.load_contract(CONTRACT)
        self.assertEqual(tuple(value["candidates"]), module.CANDIDATES)
        self.assertEqual(len(value["selection_integrity"]["outcome_tested_rejections_acknowledged"]), 5)
        self.assertFalse(value["selection_integrity"]["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"])
        self.assertFalse(value["selection_integrity"]["prior_outcomes_used_to_choose_batch4_thresholds"])
        self.assertFalse(value["selection_integrity"]["batch4_count_or_outcome_viewed_before_freeze"])
        self.assertEqual(
            {row["mechanism_family"] for row in value["mechanism_independence"].values()},
            {
                "WEEKEND_GAP_REVERSION",
                "MONTH_END_FIXING_REVERSAL",
                "WEEKLY_CROSS_SECTIONAL_RELATIVE_MOMENTUM",
                "TRIANGULAR_PARITY_DISLOCATION_REVERSION",
            },
        )

    def test_weekend_gap_reversion_is_detected(self):
        start = datetime(2017, 1, 2, tzinfo=UTC)
        rows = [bar(start + timedelta(hours=i), 100.0, 100.0) for i in range(16)]
        reopen = rows[-1].timestamp + timedelta(hours=49)
        rows.extend([bar(reopen, 101.0, 100.5, 0.05), bar(reopen + timedelta(hours=1), 100.5, 100.5)])
        signals = module.scan_313("EURUSD", rows, self.contract["candidates"]["EXP-P9-MTF-313"])
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].direction, "SHORT")

    def test_month_end_fixing_reversal_is_detected(self):
        start = datetime(2017, 1, 30, 21, tzinfo=UTC)
        rows = [bar(start + timedelta(hours=i), 100.0, 100.0) for i in range(20)]
        index = next(i for i, row in enumerate(rows) if row.timestamp == datetime(2017, 1, 31, 16, tzinfo=UTC))
        for offset in range(5, 0, -1):
            value = 100.0 + (5 - offset) * 0.3
            rows[index - offset] = bar(rows[index - offset].timestamp, value, value + 0.2, 0.02)
        rows[index - 1] = bar(rows[index - 1].timestamp, 101.0, 101.2, 0.02)
        rows[index] = bar(rows[index].timestamp, 101.2, 100.8, 0.02)
        rows.append(bar(rows[-1].timestamp + timedelta(hours=1), 100.8, 100.8))
        signals = module.scan_314("EURUSD", rows, self.contract["candidates"]["EXP-P9-MTF-314"])
        self.assertTrue(any(row.direction == "SHORT" for row in signals))

    def test_monday_cross_section_ranks_exactly_two_long_and_two_short(self):
        d1_start = datetime(2017, 1, 1, tzinfo=UTC)
        slopes = {symbol: index + 1 for index, symbol in enumerate(module.SYMBOLS)}
        d1_by_symbol = {
            symbol: [bar(d1_start + timedelta(days=i), 100.0 + slope * i, 100.0 + slope * i, 0.5) for i in range(20)]
            for symbol, slope in slopes.items()
        }
        when = datetime(2017, 1, 16, 8, tzinfo=UTC)
        h1_by_symbol = {
            symbol: [bar(when, 100.0, 100.0), bar(when + timedelta(hours=1), 100.0, 100.0)]
            for symbol in module.SYMBOLS
        }
        signals = module.scan_315(h1_by_symbol, d1_by_symbol, self.contract["candidates"]["EXP-P9-MTF-315"])
        self.assertEqual(sum(row.direction == "LONG" for row in signals), 2)
        self.assertEqual(sum(row.direction == "SHORT" for row in signals), 2)

    def test_triangular_residual_spike_assigns_parity_restoring_legs(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        series = {}
        for symbol in module.SYMBOLS:
            rows = []
            for index in range(122):
                value = 100.0
                if symbol == "AUDJPY":
                    value += 0.01 * math.sin(index)
                    if index == 120:
                        value = 105.0
                rows.append(bar(start + timedelta(hours=index), value, value, 0.01))
            series[symbol] = rows
        signals = module.scan_316(series, self.contract["candidates"]["EXP-P9-MTF-316"])
        at_spike = [row for row in signals if row.signal_time == start + timedelta(hours=121)]
        directions = {(row.symbol, row.direction) for row in at_spike}
        self.assertIn(("AUDJPY", "SHORT"), directions)
        self.assertIn(("AUDUSD", "LONG"), directions)
        self.assertIn(("USDJPY", "LONG"), directions)

    def test_report_rejects_outcomes_or_wrong_prior_family_count(self):
        report = {
            "strategy_results": [{"strategy_id": candidate, "exploratory_frequency_pass": False} for candidate in module.CANDIDATES],
            "frequency_pass_candidates": [],
            "return_calculated": False,
            "research_outcomes_calculated": False,
            "outcome_fields": [],
            "persistent_price_files_after_cleanup": 0,
            "formal_phase9_authorization_effect": False,
            "prior_candidate_rescue_performed": False,
            "result_dependent_rule_change": False,
            "prior_outcome_tested_candidate_count": 5,
        }
        module.validate_report(report)
        report["profit_factor"] = 1.1
        with self.assertRaises(Exception):
            module.validate_report(report)
        del report["profit_factor"]
        report["prior_outcome_tested_candidate_count"] = 3
        with self.assertRaises(module.Batch4CountError):
            module.validate_report(report)

    def test_workflow_is_manual_single_use_count_only_and_hash_locked(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn(module.OUTPUT, text)
        self.assertNotIn("concurrency:", text)
        self.assertNotIn("schedule:", text)
        for path in (CONTRACT, RUNNER):
            self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), text)


if __name__ == "__main__":
    unittest.main()
