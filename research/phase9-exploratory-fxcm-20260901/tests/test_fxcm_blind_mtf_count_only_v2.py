from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_count_only_v2.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v2.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch2-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_count_only_v2_tests", RUNNER)
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


class BlindMtfBatch2CountTests(unittest.TestCase):
    def test_contract_is_new_batch_without_v1_rescue_or_outcome(self):
        value = module.load_contract(CONTRACT)
        self.assertEqual(tuple(value["candidates"]), module.CANDIDATES)
        self.assertFalse(value["selection_integrity"]["v1_threshold_direction_symbol_or_exit_rescue_allowed"])
        self.assertFalse(value["selection_integrity"]["v2_candidate_return_or_outcome_viewed"])
        self.assertTrue(value["selection_integrity"]["future_return_familywise_correction_must_include_prior_two_outcome_candidates"])

    def test_nr7_compression_release_can_be_detected(self):
        d1_start = datetime(2017, 1, 1, tzinfo=UTC)
        d1 = [bar(d1_start + timedelta(days=i), 100.0 + 0.2 * i, 100.1 + 0.2 * i, 0.2) for i in range(45)]
        event_time = d1_start + timedelta(days=44, hours=4)
        h4 = [bar(event_time - timedelta(hours=4 * (20 - i)), 108.0, 108.0, 0.3) for i in range(20)]
        h4.append(module.Bar(event_time, 108.0, 108.1, 107.9, 108.0))
        available = event_time + timedelta(hours=4)
        h1 = [bar(available - timedelta(hours=16 - i), 108.0, 108.0, 0.2) for i in range(16)]
        h1.extend([
            bar(available, 108.0, 108.8, 0.05),
            bar(available + timedelta(hours=1), 108.8, 108.9, 0.1),
        ])
        rules = json.loads(CONTRACT.read_text(encoding="utf-8"))["candidates"]["EXP-P9-MTF-305"]
        signals = module.scan_305("EURUSD", h1, h4, d1, rules)
        self.assertTrue(any(row.direction == "LONG" for row in signals))

    def test_frequency_result_remains_count_only(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        rows = []
        for index in range(300):
            year = 2017 if index < 150 else 2018
            when = datetime(year, 1, 1, tzinfo=UTC) + timedelta(days=index % 150)
            rows.append(module.Signal(
                "EXP-P9-MTF-305", module.SYMBOLS[index % 8], "H1",
                "LONG" if index % 2 == 0 else "SHORT", when, when + timedelta(hours=1), 0,
            ))
        result = module.frequency_result("EXP-P9-MTF-305", rows, contract)
        self.assertFalse(result["formal_phase9_effect"])
        self.assertNotIn("return", result)

    def test_report_rejects_outcome_or_persistent_price(self):
        report = {
            "strategy_results": [], "frequency_pass_candidates": [],
            "return_calculated": True, "research_outcomes_calculated": False,
            "outcome_fields": [], "persistent_price_files_after_cleanup": 0,
            "formal_phase9_authorization_effect": False,
        }
        with self.assertRaises(module.Batch2CountError):
            module.validate_report(report)
        report["return_calculated"] = False
        report["persistent_price_files_after_cleanup"] = 1
        with self.assertRaises(module.Batch2CountError):
            module.validate_report(report)

    def test_workflow_is_manual_single_use_count_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn(module.OUTPUT, text)
        self.assertNotIn("schedule:", text)


if __name__ == "__main__":
    unittest.main()
