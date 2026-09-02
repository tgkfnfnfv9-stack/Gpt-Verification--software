from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_count_only.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v1.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_count_only_tests", RUNNER)
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


class BlindMtfCountTests(unittest.TestCase):
    def test_frozen_contract_and_anchors_pass(self):
        value = module.load_contract(CONTRACT)
        self.assertEqual(tuple(value["candidates"]), module.CANDIDATES)
        self.assertFalse(value["common_rules"]["forward_outcome_access"])
        self.assertFalse(value["design_boundary"]["formal_authorization_effect"])
        self.assertEqual(
            value["candidates"]["EXP-P9-MTF-301"]["break_selection"],
            "EARLIEST_DIRECTIONALLY_ELIGIBLE_BREAK_PER_UTC_DATE_ONLY",
        )

    def test_d1_inside_compression_h4_break_is_detected(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        d1 = [bar(start + timedelta(days=i), 100.0, 100.0, 0.5) for i in range(15)]
        d1.append(module.Bar(start + timedelta(days=15), 100.0, 100.2, 99.8, 100.0))
        h4_start = start + timedelta(days=16)
        h4 = [bar(h4_start - timedelta(hours=4 * (15 - i)), 100.0, 100.0, 0.1) for i in range(15)]
        h4.extend([
            bar(h4_start, 100.0, 100.8, 0.05),
            bar(h4_start + timedelta(hours=4), 100.8, 100.9, 0.1),
        ])
        rules = json.loads(CONTRACT.read_text(encoding="utf-8"))["candidates"]["EXP-P9-MTF-303"]
        signals = module.scan_303("EURUSD", d1, h4, rules)
        self.assertTrue(any(row.direction == "LONG" for row in signals))

    def test_frequency_gate_is_deterministic_and_price_free(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        signals = []
        for index in range(400):
            year = 2017 if index < 200 else 2018
            when = datetime(year, 1, 1, tzinfo=UTC) + timedelta(days=index % 200)
            signals.append(module.Signal(
                "EXP-P9-MTF-301", module.SYMBOLS[index % 8], "M15",
                "LONG" if index % 2 == 0 else "SHORT", when,
                when + timedelta(minutes=15), 0,
            ))
        result = module.frequency_result("EXP-P9-MTF-301", signals, contract)
        self.assertTrue(result["exploratory_frequency_pass"])
        self.assertFalse(result["formal_phase9_effect"])

    def test_report_rejects_outcome_or_persistent_price(self):
        report = {
            "strategy_results": [], "frequency_pass_candidates": [],
            "return_calculated": True, "research_outcomes_calculated": False,
            "outcome_fields": [], "formal_count_only_authorized": False,
            "formal_phase9_authorization_effect": False,
            "persistent_price_files_after_cleanup": 0,
        }
        with self.assertRaises(module.BlindCountError):
            module.validate_report(report)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "report"
            safe = dict(report)
            safe["return_calculated"] = False
            safe["persistent_price_files_after_cleanup"] = 1
            with self.assertRaises(module.BlindCountError):
                module.validate_report(safe)

    def test_workflow_is_manual_single_use_count_only_and_cleans_prices(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn(module.OUTPUT, text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("Return/OOS", text)


if __name__ == "__main__":
    unittest.main()
