from __future__ import annotations

import csv
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_rr_count_only.py"
CONTRACT = ROOT / "spec/fxcm_rr201_rr202_count_only_contract.frozen.json"
ENTRY_GATE = ROOT / "spec/fxcm_count_only_entry_gate.frozen.json"
REGISTRY = REPO / "research/phase9-hypothesis-redesign-20260828/spec/candidate_registry.frozen.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-rr-count-only.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_rr_count_only", RUNNER)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def bar(timestamp: datetime, open_value: float, close_value: float, padding: float = 0.5) -> module.Bar:
    return module.Bar(
        timestamp,
        open_value,
        max(open_value, close_value) + padding,
        min(open_value, close_value) - padding,
        close_value,
    )


def write_working_pair(root: Path, symbol: str, timeframe: str, rows: list[module.Bar]) -> None:
    directory = root / ("direct" if timeframe == "H1" else "derived")
    directory.mkdir(parents=True, exist_ok=True)
    for side, offset in (("bid", -0.01), ("ask", 0.01)):
        path = directory / f"{symbol}_{timeframe}_{side}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(module.WORKING_HEADER)
            for row in rows:
                writer.writerow([
                    module.iso(row.timestamp),
                    row.open + offset,
                    row.high + offset,
                    row.low + offset,
                    row.close + offset,
                ])


class FxcmRrCountOnlyTests(unittest.TestCase):
    def test_frozen_route_one_contract_and_repository_anchors(self):
        contract = module.validate_contract(CONTRACT, ENTRY_GATE, REGISTRY, CANONICAL_MTF)
        module.validate_registry(REGISTRY, contract)
        self.assertEqual(contract["route_decision"]["selected_route"], 1)
        self.assertFalse(contract["route_decision"]["formal_phase9_promotion_effect"])
        self.assertFalse(contract["coverage_reporting"]["formal_block_gate_possible"])
        self.assertFalse(contract["common_rules"]["forward_outcome_access"])

    def test_currency_strength_recovers_connected_sum_zero_network(self):
        scores = {"AUD": 0.03, "EUR": 0.02, "GBP": 0.01, "JPY": -0.04, "USD": -0.02}
        changes = {symbol: scores[symbol[:3]] - scores[symbol[3:]] for symbol in module.SYMBOLS}
        recovered = module.currency_strength(changes)
        self.assertIsNotNone(recovered)
        for currency in module.CURRENCIES:
            self.assertAlmostEqual(recovered[currency], scores[currency], places=10)
        self.assertAlmostEqual(sum(recovered.values()), 0.0, places=10)

    def test_mid_loader_requires_exact_bid_ask_alignment_and_uses_fieldwise_mid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bid = root / "bid.csv"
            ask = root / "ask.csv"
            for path, values in ((bid, ["100", "102", "99", "101"]), (ask, ["100.2", "102.2", "99.2", "101.2"])):
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle, lineterminator="\n")
                    writer.writerow(module.WORKING_HEADER)
                    writer.writerow(["2017-01-02T00:00:00Z", *values])
            output = module.load_mid_series(bid, ask)
            self.assertEqual(len(output), 1)
            self.assertAlmostEqual(output[0].open, 100.1)
            self.assertAlmostEqual(output[0].close, 101.1)
            ask.write_text(ask.read_text().replace("2017-01-02T00:00:00Z", "2017-01-02T01:00:00Z"), encoding="utf-8")
            with self.assertRaises(module.CountOnlyError):
                module.load_mid_series(bid, ask)

    def test_rr201_two_bar_pullback_and_three_bar_break_confirmation(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        bars = []
        for index in range(16):
            bars.append(bar(start + timedelta(hours=4 * index), 100.0, 100.0, 0.5))
        bars.append(bar(start + timedelta(hours=64), 100.0, 99.6, 0.1))
        bars.append(bar(start + timedelta(hours=68), 99.6, 99.2, 0.2))
        bars.append(bar(start + timedelta(hours=72), 99.2, 101.0, 0.1))
        self.assertTrue(module.h4_trigger(bars, 18, "LONG"))
        self.assertFalse(module.h4_trigger(bars, 18, "SHORT"))

    def test_rr202_detects_large_leave_one_out_residual_then_reversion_confirmation(self):
        start = datetime(2017, 1, 1, tzinfo=UTC)
        count = 290
        series = {}
        for symbol in module.SYMBOLS:
            rows = []
            previous = None
            for index in range(count):
                currency_levels = {
                    "AUD": 0.00025 * index + 0.0020 * math.sin(index * 0.071),
                    "EUR": 0.00010 * index + 0.0017 * math.sin(index * 0.053 + 0.4),
                    "GBP": 0.00018 * index + 0.0015 * math.sin(index * 0.083 + 1.1),
                    "JPY": -0.00012 * index + 0.0018 * math.sin(index * 0.061 + 2.2),
                    "USD": -0.00005 * index + 0.0014 * math.sin(index * 0.097 + 0.7),
                }
                log_price = currency_levels[symbol[:3]] - currency_levels[symbol[3:]]
                if symbol == "EURUSD":
                    log_price += 0.0008 * math.sin(index * 0.41)
                    if index == 270:
                        log_price += 0.025
                close = math.exp(log_price) * 100
                open_value = close if previous is None else previous
                rows.append(bar(start + timedelta(hours=index), open_value, close, 0.01))
                previous = close
            series[(symbol, "H1")] = rows
        signals, sync = module.rr202_timeframe_signals(series, "H1")
        self.assertEqual(sync["all_eight_synchronization_ratio"], 1.0)
        self.assertTrue(any(signal.symbol == "EURUSD" and signal.direction == "SHORT" for signal in signals))

    def test_overlap_and_primary_episode_rules_are_deterministic(self):
        base = datetime(2017, 3, 1, 10, tzinfo=UTC)
        rows = [
            module.Signal("STRAT-P9-RR-202", "EURUSD", "H1", "LONG", base, base + timedelta(hours=1), 3),
            module.Signal("STRAT-P9-RR-202", "EURUSD", "H1", "LONG", base + timedelta(hours=2), base + timedelta(hours=3), 3),
            module.Signal("STRAT-P9-RR-202", "GBPUSD", "H4", "LONG", base, base + timedelta(hours=4), 3),
            module.Signal("STRAT-P9-RR-202", "USDJPY", "H1", "SHORT", base + timedelta(hours=1), base + timedelta(hours=2), 3),
        ]
        deduplicated = module.collapse_overlaps(rows)
        self.assertEqual(len(deduplicated), 3)
        episodes = module.primary_episodes(deduplicated)
        self.assertEqual(len(episodes), 2)
        long_episode = next(row for row in episodes if row.direction == "LONG")
        self.assertEqual(long_episode.timeframe, "H4")
        self.assertEqual(long_episode.symbol, "GBPUSD")

    def test_formal_blocks_make_two_year_scope_structurally_ineligible(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        blocks = contract["coverage_reporting"]["formal_discovery_blocks"]
        touched = {
            module.formal_block(datetime(2017, 1, 1, tzinfo=UTC), blocks),
            module.formal_block(datetime(2017, 9, 1, tzinfo=UTC), blocks),
            module.formal_block(datetime(2018, 9, 1, tzinfo=UTC), blocks),
        }
        self.assertEqual(touched, {"B3", "B4", "B5"})
        self.assertLess(len(touched), contract["coverage_reporting"]["formal_blocks_required_with_at_least_25_episodes"])

    def test_outcome_fields_and_extra_artifact_files_fail_closed(self):
        with self.assertRaises(module.CountOnlyError):
            module.reject_outcome_fields({"forward_return": 0})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "EXPLORATORY_FXCM_RR_COUNT_ONLY.json").write_text("{}\n", encoding="utf-8")
            module.validate_report_tree(root, False)
            (root / "prices.csv").write_text("forbidden\n", encoding="utf-8")
            with self.assertRaises(module.CountOnlyError):
                module.validate_report_tree(root, False)

    def test_end_to_end_synthetic_count_run_writes_exact_price_free_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            for timeframe, count, delta in (
                ("H1", 290, timedelta(hours=1)),
                ("H4", 290, timedelta(hours=4)),
                ("D1", 100, timedelta(days=1)),
            ):
                for symbol in module.SYMBOLS:
                    rows = []
                    previous = None
                    for index in range(count):
                        level = 100 + 0.01 * index + 0.2 * math.sin(index * 0.11 + module.SYMBOLS.index(symbol))
                        open_value = level if previous is None else previous
                        rows.append(bar(datetime(2017, 1, 1, tzinfo=UTC) + index * delta, open_value, level, 0.1))
                        previous = level
                    write_working_pair(work, symbol, timeframe, rows)
            report_dir = root / "report"
            report = module.run(CONTRACT, ENTRY_GATE, REGISTRY, CANONICAL_MTF, CANONICAL_MTF, work, report_dir)
            self.assertTrue(report["candidate_signal_counts_calculated"])
            self.assertFalse(report["formal_count_only_authorized"])
            self.assertFalse(report["return_calculated"])
            self.assertFalse(report["research_outcomes_calculated"])
            self.assertEqual(
                {path.name for path in report_dir.iterdir()},
                {"EXPLORATORY_FXCM_RR_COUNT_ONLY.json", "artifact_manifest_sha256.txt"},
            )

    def test_workflow_is_manual_separate_gate_and_cleans_before_upload(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("pull_request:", text)
        self.assertIn(module.CONFIRMATION, text)
        self.assertIn("Destroy all working prices before upload", text)
        self.assertIn("EXPLORATORY_FXCM_RR_COUNT_ONLY.json", text)
        self.assertNotIn("EXPLORATORY_FXCM_MTF_QC.json\n          EXPLORATORY_FXCM_RR_COUNT_ONLY.json", text)


if __name__ == "__main__":
    unittest.main()
