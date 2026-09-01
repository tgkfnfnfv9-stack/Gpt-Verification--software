from __future__ import annotations

import csv
import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RUNNER = ROOT / "runner/fxcm_multitimeframe_qc.py"
REQUIREMENTS = ROOT / "spec/fxcm_multitimeframe_data_requirements.frozen.json"
EXECUTION = ROOT / "spec/fxcm_multitimeframe_execution_contract.frozen.json"
PRIOR_H1 = ROOT / "results/run-33482595275/artifact/EXPLORATORY_FXCM_INVENTORY.json"
WORKFLOW = REPO / ".github/workflows/phase9-exploratory-fxcm-mtf-qc.yml"
SPEC = importlib.util.spec_from_file_location("fxcm_mtf_qc", RUNNER)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
UTC = timezone.utc


def fxcm_row(timestamp: datetime, bid_open: str = "1.0000", ask_open: str = "1.0002") -> list[str]:
    stamp = timestamp.strftime("%m/%d/%Y %H:%M:%S.000")
    return [
        stamp, bid_open, "1.0020", "0.9990", "1.0010",
        ask_open, "1.0022", "0.9992", "1.0012",
    ]


def write_gzip(path: Path, rows: list[list[str]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(module.EXPECTED_HEADER)
        writer.writerows(rows)


def write_working(path: Path, bars: list[module.Bar]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(module.WORKING_HEADER)
        for bar in bars:
            module.write_bar(writer, bar)


def bar(timestamp: datetime, base: int) -> module.Bar:
    value = Decimal(base)
    return module.Bar(timestamp, value, value + 2, value - 1, value + 1)


def final_row(symbol: str, timeframe: str, side: str) -> dict:
    source = "DIRECT_M1" if timeframe == "M15" else "DIRECT_H1"
    return {
        "symbol": symbol, "timeframe": timeframe, "side": side, "source": source,
        "working_filename": f"{symbol}_{timeframe}_{side}.csv", "bar_count": 1,
        "first_timestamp_utc": "2017-01-01T00:00:00Z",
        "last_timestamp_utc": "2017-01-01T00:00:00Z",
        "timestamp_sha256": module.EMPTY_SHA256, "working_file_sha256": module.EMPTY_SHA256,
        "gap_segment_count": 0, "missing_nominal_slot_count": 0,
    }


def valid_report() -> dict:
    source_downloads = [{} for _ in range(1664)]
    direct = [
        {"symbol": symbol, "periodicity": periodicity}
        for symbol in module.SYMBOLS for periodicity in module.DIRECT_PERIODICITIES
    ]
    derivations = [
        {"symbol": symbol, "output_timeframe": timeframe, "side": side}
        for symbol in module.SYMBOLS for timeframe in module.FINAL_TIMEFRAMES for side in module.SIDES
    ]
    final = [
        final_row(symbol, timeframe, side)
        for symbol in module.SYMBOLS for timeframe in module.FINAL_TIMEFRAMES for side in module.SIDES
    ]
    h1 = [
        {
            "symbol": symbol, "side": side, "matched_timestamp_count": 1,
            "exact_ohlc_match_count": 1, "ohlc_mismatch_count": 0,
            "m1_derived_only_count": 0, "direct_h1_only_count": 0,
            "ohlc_mismatch_event_sha256": module.EMPTY_SHA256,
            "role": "QC_ONLY_DIRECT_H1_REMAINS_CANONICAL",
        }
        for symbol in module.SYMBOLS for side in module.SIDES
    ]
    return {
        "schema_version": "phase9-exploratory-fxcm-mtf-qc-v1.0.0",
        "status": "MTF_64_SERIES_STRUCTURAL_QC_PASS_WITH_QUARANTINE_AND_INCOMPLETE_BUCKET_DROPS",
        "track": "EXPLORATORY_FX8_MULTI_TIMEFRAME_NOT_FORMAL_PHASE9",
        "run_identity": {"run_id": "LOCAL", "run_attempt": "LOCAL", "head_sha": "LOCAL"},
        "contract_sha256": module.EMPTY_SHA256,
        "execution_contract_sha256": module.EMPTY_SHA256,
        "prior_h1_inventory_sha256": module.EMPTY_SHA256,
        "h1_source_identity_exact_match": True,
        "provider": {}, "coverage": {}, "source_download_count": 1664,
        "source_download_total_bytes": 0, "source_downloads": source_downloads,
        "direct_series_inventory": direct, "direct_series_inventory_sha256": module.EMPTY_SHA256,
        "crossed_open_quote_total_count": 0,
        "crossed_open_quote_inventory_sha256": module.EMPTY_SHA256,
        "derivation_inventory": derivations, "derivation_inventory_sha256": module.EMPTY_SHA256,
        "final_series_count": 64, "final_series_inventory": final,
        "final_series_inventory_sha256": module.EMPTY_SHA256,
        "bid_ask_reconciliation": [{} for _ in range(32)],
        "m1_derived_h1_vs_direct_h1": h1,
        "mtf_qc_execution_completed": True, "exploratory_mtf_structural_qc_passed": True,
        "forward_fill_count": 0, "price_interpolation_count": 0,
        "persistent_price_files": 0, "formal_phase9_price_files_acquired": 0,
        "provider_schedule_inventory_claimed": False,
        "provider_schedule_version_status": "UNPROVEN_NOT_EVALUATED",
        "formal_phase9_authorization_effect": False, "acquisition_authorized": False,
        "count_only_authorized": False, "formal_full_quality_gate_passed": False,
        "candidate_signal_counts_calculated": False, "research_outcomes_calculated": False,
        "outcome_fields": [], "forbidden_market_period_request_attempted": False,
        "official_candledata_out_of_scope_not_requested": [
            "XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD"
        ],
        "tick_volume_available": False,
    }


class FxcmMultiTimeframeQcTests(unittest.TestCase):
    def test_frozen_requirements_and_prospective_execution_contract(self):
        requirements = module.load_contract(REQUIREMENTS)
        execution = module.load_execution_contract(EXECUTION, REQUIREMENTS)
        self.assertEqual(requirements["coverage"]["expected_direct_source_object_count"], 1664)
        self.assertEqual(execution["bucket_population"]["rule"], "SOURCE_TOUCHED_FIXED_UTC_BUCKETS_ONLY")
        self.assertEqual(execution["h1_reconciliation"]["tolerance"], "NONE")
        self.assertFalse(execution["scientific_state"]["count_only_authorized"])

    def test_prior_h1_exact_source_identity_is_required(self):
        execution = module.load_execution_contract(EXECUTION, REQUIREMENTS)
        prior = json.loads(PRIOR_H1.read_text(encoding="utf-8"))
        downloads = [
            {**row, "periodicity": "H1", "working_filename": "unused.csv.gz"}
            for row in prior["source_downloads"]
        ]
        self.assertEqual(
            module.validate_prior_h1_identity(downloads, PRIOR_H1, execution),
            execution["prior_h1_identity"]["canonical_inventory_sha256"],
        )
        mutated = [{**downloads[0], "bytes": downloads[0]["bytes"] + 1}, *downloads[1:]]
        with self.assertRaises(module.FxcmMtfError):
            module.validate_prior_h1_identity(mutated, PRIOR_H1, execution)

    def test_direct_m1_crossed_quote_quarantines_both_sides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "EURUSD_m1_2017_01.csv.gz"
            start = datetime(2017, 1, 1, tzinfo=UTC)
            rows = [fxcm_row(start), fxcm_row(start + timedelta(minutes=1), "1.0000", "0.9999")]
            write_gzip(source, rows)
            output = root / "direct"; output.mkdir()
            result = module.process_direct_series("EURUSD", "m1", [source], output)
            self.assertEqual(result["observed_bar_count"], 2)
            self.assertEqual(result["usable_bar_count"], 1)
            self.assertEqual(result["crossed_open_quote_count"], 1)
            self.assertNotEqual(result["crossed_open_quote_event_sha256"], module.EMPTY_SHA256)
            self.assertEqual(len((output / "EURUSD_m1_bid.csv").read_text().splitlines()), 2)
            self.assertEqual(len((output / "EURUSD_m1_ask.csv").read_text().splitlines()), 2)

    def test_direct_alignment_order_geometry_and_boundary_are_fail_closed(self):
        cases = [
            [fxcm_row(datetime(2017, 1, 1, 0, 1, 1, tzinfo=UTC))],
            [fxcm_row(datetime(2017, 1, 1, tzinfo=UTC)), fxcm_row(datetime(2017, 1, 1, tzinfo=UTC))],
            [fxcm_row(datetime(2016, 12, 31, 23, 59, tzinfo=UTC))],
        ]
        for index, rows in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); source = root / "bad.csv.gz"; write_gzip(source, rows)
                output = root / "direct"; output.mkdir()
                with self.assertRaises(module.FxcmMtfError):
                    module.process_direct_series("EURUSD", "m1", [source], output)

    def test_m1_complete_15_bucket_created_and_incomplete_bucket_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = datetime(2017, 1, 2, tzinfo=UTC)
            bars = [bar(start + timedelta(minutes=index), index + 2) for index in range(15)]
            bars += [bar(start + timedelta(minutes=index), index + 2) for index in range(16, 30)]
            source = root / "m1.csv"; destination = root / "M15.csv"
            write_working(source, bars)
            result = module.aggregate_complete(source, destination, "M15")
            self.assertEqual(result["candidate_bucket_count"], 2)
            self.assertEqual(result["complete_bucket_count"], 1)
            self.assertEqual(result["dropped_incomplete_bucket_count"], 1)
            output = list(module.iter_working(destination))
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0].open, Decimal(2))
            self.assertEqual(output[0].high, Decimal(18))
            self.assertEqual(output[0].low, Decimal(1))
            self.assertEqual(output[0].close, Decimal(17))

    def test_exact_60_m1_h1_and_h1_h4_d1_buckets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = datetime(2017, 1, 2, tzinfo=UTC)
            minute_source = root / "m1.csv"
            write_working(minute_source, [bar(start + timedelta(minutes=index), index + 2) for index in range(60)])
            h1_qc = root / "m1_H1.csv"
            self.assertEqual(module.aggregate_complete(minute_source, h1_qc, "H1")["complete_bucket_count"], 1)
            hour_source = root / "H1.csv"
            write_working(hour_source, [bar(start + timedelta(hours=index), index + 2) for index in range(24)])
            h4 = root / "H4.csv"; d1 = root / "D1.csv"
            self.assertEqual(module.aggregate_complete(hour_source, h4, "H4")["complete_bucket_count"], 6)
            self.assertEqual(module.aggregate_complete(hour_source, d1, "D1")["complete_bucket_count"], 1)
            self.assertEqual([item.timestamp.hour for item in module.iter_working(h4)], [0, 4, 8, 12, 16, 20])
            self.assertEqual(list(module.iter_working(d1))[0].timestamp.hour, 0)

    def test_h1_reconciliation_counts_exact_mismatch_and_one_side_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = datetime(2017, 1, 2, tzinfo=UTC)
            derived = root / "derived.csv"; direct = root / "direct.csv"
            write_working(derived, [bar(start, 2), bar(start + timedelta(hours=1), 3)])
            write_working(direct, [bar(start, 2), bar(start + timedelta(hours=1), 30), bar(start + timedelta(hours=2), 4)])
            result = module.reconcile_h1(derived, direct, "EURUSD", "bid")
            self.assertEqual(result["matched_timestamp_count"], 2)
            self.assertEqual(result["exact_ohlc_match_count"], 1)
            self.assertEqual(result["ohlc_mismatch_count"], 1)
            self.assertEqual(result["direct_h1_only_count"], 1)
            self.assertNotEqual(result["ohlc_mismatch_event_sha256"], module.EMPTY_SHA256)

    def test_bid_ask_timestamp_and_crossed_open_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); start = datetime(2017, 1, 2, tzinfo=UTC)
            bid = root / "bid.csv"; ask = root / "ask.csv"
            write_working(bid, [bar(start, 3)])
            write_working(ask, [bar(start + timedelta(hours=1), 4)])
            with self.assertRaises(module.FxcmMtfError):
                module.reconcile_pair(bid, ask, "EURUSD", "H1")

    def test_report_exact_64_series_and_research_prohibitions(self):
        report = valid_report()
        module.validate_report(report)
        with self.assertRaises(module.FxcmMtfError):
            module.validate_report({**report, "signal_count": 1})
        blocked = json.loads(json.dumps(report))
        blocked["m1_derived_h1_vs_direct_h1"][0]["ohlc_mismatch_count"] = 1
        blocked["exploratory_mtf_structural_qc_passed"] = False
        module.validate_report(blocked)
        blocked["exploratory_mtf_structural_qc_passed"] = True
        with self.assertRaises(module.FxcmMtfError):
            module.validate_report(blocked)

    def test_price_free_exact_two_file_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "EXPLORATORY_FXCM_MTF_QC.json"
            payload.write_text("{}\n", encoding="utf-8")
            module.validate_report_tree(root, False)
            module.seal_manifest(root)
            module.validate_report_tree(root, True)
            self.assertEqual(
                (root / "artifact_manifest_sha256.txt").read_text(encoding="utf-8"),
                f"{module.sha256_file(payload)}  {payload.name}\n",
            )
            (root / "raw.csv").write_text("forbidden\n", encoding="utf-8")
            with self.assertRaises(module.FxcmMtfError):
                module.validate_report_tree(root, True)

    def test_workflow_is_manual_only_and_stops_after_price_free_qc(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        trigger = workflow.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
        trigger_keys = [
            line.strip()[:-1] for line in trigger.splitlines()
            if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":")
        ]
        self.assertEqual(trigger_keys, ["workflow_dispatch"])
        self.assertIn(module.CONFIRMATION, workflow)
        self.assertIn(module.USAGE_CONFIRMATION, workflow)
        self.assertNotIn("repository_dispatch", workflow)
        self.assertNotIn("workflow_run", workflow)
        self.assertNotIn("DUKASCOPY_", workflow)
        self.assertIn("Destroy all working prices before upload", workflow)


if __name__ == "__main__":
    unittest.main()
