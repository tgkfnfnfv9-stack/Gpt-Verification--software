from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_ps204_count_only.py"
CONTRACT = ROOT / "spec/fxcm_ps204_count_only_contract.frozen.json"
ENTRY_GATE = ROOT / "spec/fxcm_count_only_entry_gate.frozen.json"
PRIOR_AUDIT = ROOT / "results/run-33563507883/FXCM_SINGLE_PAIR_COUNT_ONLY_RUN_AUDIT.json"
PRIOR_RESULT = ROOT / "results/run-33563507883/artifact/EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY.json"
REGISTRY = REPO / "research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-ps204-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_ps204_count_only", RUNNER)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def bar(timestamp: datetime, open_value: float, close_value: float, padding: float = 0.1) -> module.Bar:
    return module.Bar(
        timestamp,
        open_value,
        max(open_value, close_value) + padding,
        min(open_value, close_value) - padding,
        close_value,
    )


def write_pair(root: Path, symbol: str, timeframe: str, rows: list[module.Bar]) -> None:
    directory = root / ("direct" if timeframe == "H1" else "derived")
    directory.mkdir(parents=True, exist_ok=True)
    for side, offset in (("bid", -0.01), ("ask", 0.01)):
        with (directory / f"{symbol}_{timeframe}_{side}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(module.utility.WORKING_HEADER)
            for row in rows:
                writer.writerow([
                    module.iso(row.timestamp), row.open + offset, row.high + offset,
                    row.low + offset, row.close + offset,
                ])


def false_break_series(timeframe: str) -> list[module.Bar]:
    delta = module.TIMEFRAME_DELTA[timeframe]
    start = datetime(2017, 1, 1, 12, tzinfo=UTC)
    end = datetime(2017, 1, 2, 10, tzinfo=UTC)
    rows = []
    current = start
    previous = 100.0
    while current < end:
        if current == datetime(2017, 1, 2, 6, tzinfo=UTC):
            current_bar = bar(current, 100.0, 100.20, 0.02)
        elif current == datetime(2017, 1, 2, 6, tzinfo=UTC) + delta:
            current_bar = bar(current, 100.20, 100.05, 0.02)
        elif current == datetime(2017, 1, 2, 6, tzinfo=UTC) + 2 * delta:
            current_bar = bar(current, 100.05, 100.06, 0.02)
        else:
            current_bar = bar(current, previous, 100.0, 0.1)
        rows.append(current_bar)
        previous = current_bar.close
        current += delta
    return rows


class FxcmPs204CountOnlyTests(unittest.TestCase):
    def test_frozen_contract_preserves_registered_scope_and_unseen_state(self):
        contract = module.validate_contract(
            CONTRACT, REGISTRY, ENTRY_GATE, PRIOR_AUDIT, PRIOR_RESULT, CANONICAL_MTF,
        )
        module.validate_registry(REGISTRY)
        self.assertFalse(contract["selection_integrity"]["candidate_signal_count_previously_calculated"])
        self.assertFalse(contract["selection_integrity"]["candidate_return_or_outcome_previously_calculated"])
        self.assertTrue(contract["scope_amendment"]["registered_fx8_plus_metals_universe_is_not_redefined_as_fx8"])
        self.assertFalse(contract["scope_amendment"]["formal_phase9_promotion_or_rejection_effect"])
        self.assertFalse(contract["common_rules"]["forward_outcome_access"])

    def test_ps204_detects_upside_false_break_and_short_reclaim_on_both_timeframes(self):
        for timeframe in module.TIMEFRAMES:
            signals, diagnostics = module.scan_ps204("EURUSD", timeframe, false_break_series(timeframe))
            self.assertEqual(len(signals), 1, timeframe)
            self.assertEqual(signals[0].direction, "SHORT")
            self.assertEqual(diagnostics["complete_pre_session_date_count"], 1)
            self.assertEqual(diagnostics["range_eligible_date_count"], 1)

    def test_missing_pre_session_slot_invalidates_date_without_fill(self):
        rows = false_break_series("H1")
        rows = [row for row in rows if row.timestamp != datetime(2017, 1, 2, 3, tzinfo=UTC)]
        signals, diagnostics = module.scan_ps204("EURUSD", "H1", rows)
        self.assertEqual(signals, [])
        self.assertEqual(diagnostics["complete_pre_session_date_count"], 0)

    def test_reclaim_requires_exact_nominal_b_plus_one_or_two(self):
        rows = false_break_series("H1")
        rows = [row for row in rows if row.timestamp != datetime(2017, 1, 2, 7, tzinfo=UTC)]
        signals, _ = module.scan_ps204("EURUSD", "H1", rows)
        self.assertEqual(signals, [])

    def test_overlap_primary_priority_and_two_timeframe_gate_are_deterministic(self):
        base = datetime(2017, 1, 1, 8, tzinfo=UTC)
        same_episode = [
            module.Signal(module.STRATEGY_ID, "EURUSD", "M15", "LONG", base, base + timedelta(minutes=15), 0),
            module.Signal(module.STRATEGY_ID, "GBPUSD", "H1", "LONG", base, base + timedelta(hours=1), 0),
        ]
        primary = module.primary_episodes(same_episode)
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0].timeframe, "H1")

        signals = []
        for index in range(600):
            signal_time = datetime(2017, 1, 1, 8, tzinfo=UTC) + timedelta(days=index)
            timeframe = module.TIMEFRAMES[index % 2]
            signals.append(module.Signal(
                module.STRATEGY_ID, module.SYMBOLS[index % 8], timeframe,
                "LONG" if index % 2 == 0 else "SHORT", signal_time,
                signal_time + module.TIMEFRAME_DELTA[timeframe], 0,
            ))
        result = module.frequency_result(signals, json.loads(CONTRACT.read_text(encoding="utf-8")))
        self.assertTrue(result["exploratory_fx8_frequency_pass"])
        self.assertFalse(result["formal_count_only_gate_passed"])

    def test_outcome_fields_and_extra_artifact_files_fail_closed(self):
        with self.assertRaises(module.Ps204CountError):
            module.reject_outcomes({"forward_return": 0})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "EXPLORATORY_FXCM_PS204_COUNT_ONLY.json").write_text("{}\n", encoding="utf-8")
            module.validate_report_tree(root, False)
            (root / "prices.csv").write_text("forbidden\n", encoding="utf-8")
            with self.assertRaises(module.Ps204CountError):
                module.validate_report_tree(root, False)

    def test_end_to_end_synthetic_run_writes_exact_price_free_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            for timeframe, count, delta in (
                ("M15", 400, timedelta(minutes=15)),
                ("H1", 120, timedelta(hours=1)),
            ):
                for symbol_index, symbol in enumerate(module.SYMBOLS):
                    rows = []
                    previous = 100.0 + symbol_index
                    for index in range(count):
                        close = 100.0 + symbol_index + 0.001 * index
                        rows.append(bar(datetime(2017, 1, 1, tzinfo=UTC) + index * delta, previous, close, 0.1))
                        previous = close
                    write_pair(work, symbol, timeframe, rows)
            report_dir = root / "report"
            report = module.run(
                CONTRACT, REGISTRY, ENTRY_GATE, PRIOR_AUDIT, PRIOR_RESULT,
                CANONICAL_MTF, CANONICAL_MTF, work, report_dir,
            )
            self.assertTrue(report["candidate_signal_counts_calculated"])
            self.assertFalse(report["formal_count_only_authorized"])
            self.assertFalse(report["return_calculated"])
            self.assertFalse(report["research_outcomes_calculated"])
            self.assertEqual(
                {path.name for path in report_dir.iterdir()},
                {"EXPLORATORY_FXCM_PS204_COUNT_ONLY.json", "artifact_manifest_sha256.txt"},
            )

    def test_workflow_is_manual_separate_gate_and_cleans_before_upload(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("pull_request:", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn("EXPLORATORY_FXCM_PS204_COUNT_ONLY.json", text)
        self.assertNotIn("forward_return", text)


if __name__ == "__main__":
    unittest.main()
