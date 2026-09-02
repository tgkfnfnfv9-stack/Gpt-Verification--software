from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_blind_mtf_count_only_v5.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v5.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch5-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_count_only_v5_tests", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def bars(start: datetime, count: int, value: float = 100.0) -> list[module.Bar]:
    return [module.Bar(start + timedelta(hours=i), value, value + 0.5, value - 0.5, value) for i in range(count)]


class BlindMtfCountOnlyV5Tests(unittest.TestCase):
    def test_contract_is_precount_independent_and_no_rescue(self):
        value = module.load_contract(CONTRACT)
        self.assertEqual(tuple(value["candidates"]), module.CANDIDATES)
        integrity = value["selection_integrity"]
        self.assertFalse(integrity["batch5_count_or_outcome_viewed_before_freeze"])
        self.assertFalse(integrity["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"])
        self.assertTrue(integrity["future_return_familywise_correction_must_include_prior_six_outcome_candidates"])

    def test_317_fixed_session_breakout_signal(self):
        start = datetime(2017, 1, 2, tzinfo=UTC)
        rows = bars(start, 54)
        rows[32] = module.Bar(rows[32].timestamp, 100.0, 102.0, 99.5, 102.0)
        rules = json.loads(CONTRACT.read_text())["candidates"]["EXP-P9-MTF-317"]
        found = module.scan_317("EURUSD", rows, rules)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "LONG")

    def test_319_semivariance_imbalance_reverts(self):
        start = datetime(2017, 1, 2, tzinfo=UTC)
        rows = bars(start, 50)
        price = 100.0
        for i, row in enumerate(rows):
            price += 0.2 if i >= 15 else 0.0
            rows[i] = module.Bar(row.timestamp, price, price + 0.5, price - 0.5, price)
        rules = json.loads(CONTRACT.read_text())["candidates"]["EXP-P9-MTF-319"]
        found = module.scan_319("EURUSD", rows, rules)
        self.assertTrue(found)
        self.assertTrue(all(row.direction == "SHORT" for row in found))

    def test_report_rejects_any_outcome_surface(self):
        report = {
            "strategy_results": [{"strategy_id": c, "exploratory_frequency_pass": False} for c in module.CANDIDATES],
            "frequency_pass_candidates": [],
            "return_calculated": True,
            "research_outcomes_calculated": False,
            "outcome_fields": [],
            "persistent_price_files_after_cleanup": 0,
            "formal_phase9_authorization_effect": False,
            "prior_candidate_rescue_performed": False,
            "result_dependent_rule_change": False,
            "prior_outcome_tested_candidate_count": 6,
        }
        with self.assertRaises(module.Batch5CountError):
            module.validate_report(report)

    def test_runner_does_not_import_return_gate(self):
        text = RUNNER.read_text(encoding="utf-8").lower()
        self.assertNotIn("fxcm_blind_mtf_return_oos.py", text)
        self.assertNotIn("profit_factor", text)
        self.assertNotIn("win_rate", text)
        self.assertNotIn("p_value", text)

    def test_workflow_is_manual_single_use_and_price_free(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("github.run_number == 1", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("concurrency:", text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn("research_outcomes_calculated\"] is False", text)
        self.assertIn("outcome_fields\"] == []", text)

    def test_workflow_hash_locks_contract_and_runner(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for path in (CONTRACT, RUNNER):
            self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), text)


if __name__ == "__main__":
    unittest.main()
