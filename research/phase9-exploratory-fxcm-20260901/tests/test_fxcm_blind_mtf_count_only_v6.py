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
RUNNER = ROOT / "runner/fxcm_blind_mtf_count_only_v6.py"
CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v6.frozen.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch6-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_blind_mtf_count_only_v6_tests", RUNNER)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def h1_bars(start: datetime, count: int, value: float = 100.0) -> list[module.Bar]:
    return [module.Bar(start + timedelta(hours=i), value, value + 0.5, value - 0.5, value) for i in range(count)]


class BlindMtfCountOnlyV6Tests(unittest.TestCase):
    def test_contract_is_precount_independent_and_no_rescue(self):
        value = module.load_contract(CONTRACT)
        self.assertEqual(tuple(value["candidates"]), module.CANDIDATES)
        integrity = value["selection_integrity"]
        self.assertFalse(integrity["batch6_count_or_outcome_viewed_before_freeze"])
        self.assertFalse(integrity["prior_candidates_301_through_320_rescued"])
        self.assertFalse(integrity["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"])
        self.assertFalse(integrity["prior_outcomes_used_to_choose_batch6_rules_or_thresholds"])
        self.assertTrue(integrity["future_return_familywise_correction_must_include_prior_seven_outcome_candidates"])

    def test_321_path_efficiency_continues(self):
        start = datetime(2017, 1, 2, tzinfo=UTC)
        rows = h1_bars(start, 55)
        price = 100.0
        for index, row in enumerate(rows):
            if index >= 15:
                price += 0.2
            rows[index] = module.Bar(row.timestamp, price, price + 0.5, price - 0.5, price)
        rules = json.loads(CONTRACT.read_text())["candidates"]["EXP-P9-MTF-321"]
        found = module.scan_321("EURUSD", rows, rules)
        self.assertTrue(found)
        self.assertTrue(all(row.direction == "LONG" for row in found))

    def test_322_first_same_sign_run_reverses_once(self):
        start = datetime(2017, 1, 2, tzinfo=UTC)
        rows = h1_bars(start, 30)
        price = 100.0
        for index, row in enumerate(rows):
            if 18 <= index <= 23:
                price += 0.3
            rows[index] = module.Bar(row.timestamp, price, price + 0.5, price - 0.5, price)
        rules = json.loads(CONTRACT.read_text())["candidates"]["EXP-P9-MTF-322"]
        found = module.scan_322("EURUSD", rows, rules)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "SHORT")

    def test_323_uses_first_month_date_and_completed_d1_only(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        d1 = []
        price = 100.0
        for index in range(70):
            price += 0.1
            when = start + timedelta(days=index)
            d1.append(module.Bar(when, price, price + 0.5, price - 0.5, price))
        h1 = h1_bars(start, 70 * 24 + 2)
        rules = json.loads(CONTRACT.read_text())["candidates"]["EXP-P9-MTF-323"]
        found = module.scan_323("EURUSD", d1, h1, rules)
        self.assertTrue(found)
        self.assertTrue(all(row.direction == "LONG" for row in found))

    def test_324_fixed_friday_stretch_reverses(self):
        start = datetime(2017, 1, 2, tzinfo=UTC)
        rows = h1_bars(start, 120)
        start_index = 16
        end_index = 112
        for index in range(start_index, end_index + 1):
            fraction = (index - start_index) / (end_index - start_index)
            value = 100.0 + 2.0 * fraction
            rows[index] = module.Bar(rows[index].timestamp, value, value + 0.5, value - 0.5, value)
        row = rows[end_index]
        rows[end_index] = module.Bar(row.timestamp, row.open, row.high, row.low, 101.5)
        rules = json.loads(CONTRACT.read_text())["candidates"]["EXP-P9-MTF-324"]
        found = module.scan_324("EURUSD", rows, rules)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].direction, "SHORT")

    def test_report_rejects_any_outcome_surface(self):
        report = {
            "strategy_results": [{"strategy_id": candidate, "exploratory_frequency_pass": False} for candidate in module.CANDIDATES],
            "frequency_pass_candidates": [],
            "return_calculated": True,
            "research_outcomes_calculated": False,
            "outcome_fields": [],
            "persistent_price_files_after_cleanup": 0,
            "formal_phase9_authorization_effect": False,
            "prior_candidate_rescue_performed": False,
            "result_dependent_rule_change": False,
            "prior_outcome_tested_candidate_count": 7,
        }
        with self.assertRaises(module.Batch6CountError):
            module.validate_report(report)

    def test_runner_does_not_import_return_gate_or_metrics(self):
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
