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
RUNNER = ROOT / "runner/fxcm_single_pair_count_only.py"
CONTRACT = ROOT / "spec/fxcm_single_pair_count_only_contract.frozen.json"
ENTRY_GATE = ROOT / "spec/fxcm_count_only_entry_gate.frozen.json"
RR_AUDIT = ROOT / "results/run-33558592191/FXCM_RR_COUNT_ONLY_RUN_AUDIT.json"
REGISTRY = REPO / "research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-single-pair-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_single_pair_count_only", RUNNER)
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


class FxcmSinglePairCountOnlyTests(unittest.TestCase):
    def test_frozen_subset_contract_and_repository_anchors(self):
        contract = module.validate_contract(CONTRACT, REGISTRY, ENTRY_GATE, RR_AUDIT, CANONICAL_MTF)
        module.validate_registry(REGISTRY)
        self.assertTrue(contract["scope_amendment"]["prior_entry_gate_exclusion_is_preserved"])
        self.assertTrue(contract["scope_amendment"]["registered_ALL_UNIVERSE_is_not_redefined_as_FX8"])
        self.assertFalse(contract["scope_amendment"]["formal_phase9_promotion_or_rejection_effect"])
        self.assertFalse(contract["common_rules"]["forward_outcome_access"])

    def test_linear_percentile_and_latest_completed_regime_are_exact(self):
        self.assertEqual(module.linear_percentile([0.0, 10.0], 20), 2.0)
        base = datetime(2017, 1, 1, tzinfo=UTC)
        availability = [base, base + timedelta(hours=4), base + timedelta(hours=8)]
        states = ["LONG", None, "SHORT"]
        self.assertEqual(module.latest_state(availability, states, base), "LONG")
        self.assertIsNone(module.latest_state(availability, states, base + timedelta(hours=6)))
        self.assertEqual(module.latest_state(availability, states, base + timedelta(hours=8)), "SHORT")

    def test_ps202_detects_failed_upside_break_and_reclaim(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        rows = [bar(start + timedelta(hours=index), 100.0, 100.0, 0.5) for index in range(20)]
        rows.extend([
            bar(start + timedelta(hours=20), 100.0, 101.0, 0.1),
            bar(start + timedelta(hours=21), 101.0, 100.2, 0.1),
            bar(start + timedelta(hours=22), 100.2, 100.1, 0.1),
        ])
        signals = module.scan_ps202("EURUSD", "H1", rows)
        self.assertTrue(any(signal.direction == "SHORT" for signal in signals))

    def test_ps203_detects_two_bar_pullback_in_completed_higher_regime(self):
        higher_start = datetime(2017, 1, 1, tzinfo=UTC)
        higher = []
        previous = 100.0
        for index in range(100):
            close = 100.0 + 0.1 * index
            higher.append(bar(higher_start + timedelta(hours=4 * index), previous, close, 0.1))
            previous = close
        start = datetime(2017, 1, 18, tzinfo=UTC)
        rows = []
        previous = 100.0
        for index in range(60):
            close = 100.0 + 0.02 * index
            rows.append(bar(start + timedelta(minutes=15 * index), previous, close, 0.1))
            previous = close
        rows.extend([
            bar(start + timedelta(minutes=15 * 60), previous, previous - 0.10, 0.1),
            bar(start + timedelta(minutes=15 * 61), previous - 0.10, previous - 0.20, 0.1),
            bar(start + timedelta(minutes=15 * 62), previous - 0.20, previous + 0.22, 0.05),
            bar(start + timedelta(minutes=15 * 63), previous + 0.22, previous + 0.24, 0.1),
        ])
        signals = module.scan_ps203("EURUSD", "M15", rows, higher, "H4")
        self.assertTrue(any(signal.direction == "LONG" for signal in signals))

    def test_ps205_detects_pullback_in_completed_d1_long_trend(self):
        d1_start = datetime(2017, 1, 1, tzinfo=UTC)
        d1 = []
        previous = 100.0
        for index in range(100):
            close = 100.0 + index
            d1.append(bar(d1_start + timedelta(days=index), previous, close, 0.1))
            previous = close
        start = datetime(2017, 3, 15, tzinfo=UTC)
        rows = []
        previous = 100.0
        for index in range(16):
            close = 100.0 + 0.1 * index
            rows.append(bar(start + timedelta(hours=index), previous, close, 0.1))
            previous = close
        rows.extend([
            bar(start + timedelta(hours=16), previous, previous - 0.10, 0.1),
            bar(start + timedelta(hours=17), previous - 0.10, previous - 0.20, 0.1),
            bar(start + timedelta(hours=18), previous - 0.20, previous + 0.30, 0.05),
            bar(start + timedelta(hours=19), previous + 0.30, previous + 0.32, 0.1),
        ])
        signals = module.scan_ps205("EURUSD", "H1", rows, d1)
        self.assertTrue(any(signal.direction == "LONG" for signal in signals))

    def test_lv202_detects_compression_break_retest_confirmation(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        rows = [bar(start + timedelta(hours=index), 100.0, 100.0, 0.5) for index in range(241)]
        rows.extend(bar(start + timedelta(hours=index), 100.0, 100.0, 0.1) for index in range(241, 253))
        rows.extend([
            bar(start + timedelta(hours=253), 100.0, 101.0, 0.05),
            bar(start + timedelta(hours=254), 100.5, 100.9, 0.05),
            bar(start + timedelta(hours=255), 100.9, 101.0, 0.1),
            bar(start + timedelta(hours=256), 101.0, 101.1, 0.1),
        ])
        signals = module.scan_lv202("EURUSD", "H1", rows)
        self.assertTrue(any(signal.direction == "LONG" for signal in signals))

    def test_overlap_primary_priority_and_frequency_gate_are_deterministic(self):
        base = datetime(2017, 1, 1, tzinfo=UTC)
        same_episode = [
            module.Signal("STRAT-P9-PS-202", "EURUSD", "M15", "LONG", base, base + timedelta(minutes=15), 0),
            module.Signal("STRAT-P9-PS-202", "GBPUSD", "H4", "LONG", base, base + timedelta(hours=4), 0),
        ]
        primary = module.primary_episodes(same_episode)
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0].timeframe, "H4")

        signals = []
        for index in range(600):
            signal_time = base + timedelta(days=index)
            timeframe = module.SIGNAL_TIMEFRAMES[index % 3]
            signals.append(module.Signal(
                "STRAT-P9-PS-202", module.SYMBOLS[index % 8], timeframe,
                "LONG" if index % 2 == 0 else "SHORT", signal_time,
                signal_time + module.TIMEFRAME_DELTA[timeframe], 0,
            ))
        result = module.frequency_result("STRAT-P9-PS-202", signals, json.loads(CONTRACT.read_text(encoding="utf-8")))
        self.assertTrue(result["exploratory_fx8_frequency_pass"])
        self.assertFalse(result["formal_count_only_gate_passed"])

    def test_outcome_fields_and_extra_artifact_files_fail_closed(self):
        with self.assertRaises(module.SinglePairCountError):
            module.reject_outcomes({"forward_return": 0})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY.json").write_text("{}\n", encoding="utf-8")
            module.validate_report_tree(root, False)
            (root / "prices.csv").write_text("forbidden\n", encoding="utf-8")
            with self.assertRaises(module.SinglePairCountError):
                module.validate_report_tree(root, False)

    def test_end_to_end_synthetic_run_writes_exact_price_free_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            for timeframe, count, delta in (
                ("M15", 260, timedelta(minutes=15)),
                ("H1", 260, timedelta(hours=1)),
                ("H4", 260, timedelta(hours=4)),
                ("D1", 100, timedelta(days=1)),
            ):
                for symbol_index, symbol in enumerate(module.SYMBOLS):
                    rows = []
                    previous = 100.0 + symbol_index
                    for index in range(count):
                        close = 100.0 + symbol_index + 0.01 * index
                        rows.append(bar(datetime(2017, 1, 1, tzinfo=UTC) + index * delta, previous, close, 0.1))
                        previous = close
                    write_pair(work, symbol, timeframe, rows)
            report_dir = root / "report"
            report = module.run(
                CONTRACT, REGISTRY, ENTRY_GATE, RR_AUDIT, CANONICAL_MTF,
                CANONICAL_MTF, work, report_dir,
            )
            self.assertTrue(report["candidate_signal_counts_calculated"])
            self.assertFalse(report["formal_count_only_authorized"])
            self.assertFalse(report["return_calculated"])
            self.assertFalse(report["research_outcomes_calculated"])
            self.assertEqual(
                {path.name for path in report_dir.iterdir()},
                {"EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY.json", "artifact_manifest_sha256.txt"},
            )

    def test_workflow_is_manual_separate_gate_and_cleans_before_upload(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("pull_request:", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn("EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY.json", text)
        self.assertNotIn("forward_return", text)


if __name__ == "__main__":
    unittest.main()
