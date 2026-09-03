#!/usr/bin/env python3
"""Synthetic regression tests for unified-backtest-v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runner"
if str(RUNNER) not in sys.path:
    sys.path.insert(0, str(RUNNER))

from core import Bar, CoreError, QuoteBar, Signal, atr_before, collapse_connected, evaluate_horizon, midpoint_series
import unified_backtest as engine
import verify_output
import drive_bundle


UTC = timezone.utc
START = datetime(2022, 1, 1, tzinfo=UTC)


def quote(stamp: datetime, mid: float, spread: float = 0.2, high_extra: float = 1.0, low_extra: float = 1.0) -> QuoteBar:
    bid_open = mid - spread / 2
    ask_open = mid + spread / 2
    bid = Bar(stamp, bid_open, bid_open + high_extra, bid_open - low_extra, bid_open + 0.1)
    ask = Bar(stamp, ask_open, ask_open + high_extra, ask_open - low_extra, ask_open + 0.1)
    return QuoteBar(stamp, bid, ask)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def manifest_template() -> dict:
    return {
        "schema_version": "unified-market-dataset-v1.0.0", "dataset_id": "D",
        "timezone": "UTC", "timestamp_semantics": "BAR_OPEN",
        "source_timestamp_semantics": "BAR_OPEN_VERIFIED",
        "timestamp_semantics_evidence": {"path": "evidence.json", "sha256": "0" * 64, "bytes": 1},
        "aggregation_profile_id": "UTC_FIXED_V1", "required_direct_timeframes": ["M1", "H1"],
        "start_inclusive": "2022-01-01T00:00:00Z", "end_exclusive": "2023-01-01T00:00:00Z",
        "instruments": [{
            "instrument_id": "X", "provider": "P", "provider_symbol": "X", "asset_class": "FX",
            "series_type": "SPOT", "quote_currency": "USD", "price_domain": "STRICTLY_POSITIVE",
            "tick_size": "0.00001", "roll_policy_id": None, "roll_policy_path": None,
            "roll_policy_sha256": None, "roll_policy_bytes": None,
        }],
        "files": [
            {"instrument_id": "X", "timeframe": timeframe, "source_role": "DIRECT_PROVIDER", "path": f"X_{timeframe}.csv", "sha256": "0" * 64, "bytes": 1, "row_count": 1}
            for timeframe in ("M1", "H1")
        ],
    }


class CoreTests(unittest.TestCase):
    def test_transitive_episode_and_exact_boundary(self):
        rows = [
            Signal("S", "X", "BUY", START + timedelta(hours=value), START + timedelta(hours=value), "H1")
            for value in (0, 11, 22, 34)
        ]
        collapsed = collapse_connected(rows, 12)
        self.assertEqual([row.entry_time for row in collapsed], [START, START + timedelta(hours=34)])

    def test_duplicate_signal_rejected(self):
        row = Signal("S", "X", "BUY", START, START, "H1")
        with self.assertRaises(CoreError):
            collapse_connected([row, row], 12)

    def test_exact_exit_no_roll_and_bar_off_by_one(self):
        quotes = [quote(START + timedelta(hours=value), 100 + value) for value in list(range(17)) + [18]]
        mids = midpoint_series(quotes)
        signal = Signal("S", "X", "BUY", START + timedelta(hours=14), START + timedelta(hours=15), "H1")
        self.assertIsNotNone(evaluate_horizon(signal, quotes, mids, "BAR_1", 14))
        self.assertIsNone(evaluate_horizon(signal, quotes, mids, "BAR_3", 14))
        self.assertIsNone(evaluate_horizon(signal, quotes, mids, "CLOCK_2H", 14))
        self.assertIsNone(evaluate_horizon(signal, quotes, mids, "CLOCK_3H", 14))

    def test_flat_midpoint_loses_spread(self):
        quotes = [quote(START + timedelta(hours=value), 100.0) for value in range(17)]
        mids = midpoint_series(quotes)
        for direction in ("BUY", "SELL"):
            signal = Signal("S", "X", direction, START + timedelta(hours=14), START + timedelta(hours=15), "H1")
            outcome = evaluate_horizon(signal, quotes, mids, "BAR_1", 14)
            self.assertIsNotNone(outcome)
            self.assertLess(outcome.r, 0)

    def test_exit_bar_extreme_is_excluded(self):
        quotes = [quote(START + timedelta(hours=value), 100.0) for value in range(17)]
        final = quotes[16]
        quotes[16] = QuoteBar(
            final.timestamp,
            Bar(final.timestamp, final.bid.open, 10000.0, final.bid.low, final.bid.close),
            Bar(final.timestamp, final.ask.open, 10000.2, final.ask.low, final.ask.close),
        )
        outcome = evaluate_horizon(
            Signal("S", "X", "BUY", START + timedelta(hours=14), START + timedelta(hours=15), "H1"),
            quotes, midpoint_series(quotes), "BAR_1", 14,
        )
        self.assertIsNotNone(outcome)
        self.assertLess(outcome.mfe_r, 10)

    def test_atr_requires_contiguous_pre_entry_and_excludes_entry(self):
        bars = [Bar(START + timedelta(hours=value), 100, 101, 99, 100) for value in range(16)]
        original = atr_before(bars, 15, 14, timedelta(hours=1))
        bars[15] = Bar(bars[15].timestamp, 100, 10000, -10000, 100)
        self.assertEqual(atr_before(bars, 15, 14, timedelta(hours=1)), original)
        broken = bars[:]
        broken[5] = Bar(broken[5].timestamp + timedelta(minutes=1), 100, 101, 99, 100)
        self.assertIsNone(atr_before(broken, 15, 14, timedelta(hours=1)))


class DataTests(unittest.TestCase):
    def test_aggregation_drops_incomplete_bucket(self):
        complete = [quote(START + timedelta(minutes=value), 100 + value) for value in range(15)]
        incomplete = [quote(START + timedelta(minutes=15 + value), 120 + value) for value in range(14)]
        rows, qc = engine.aggregate_quotes(complete + incomplete, "M1", "M15")
        self.assertEqual(len(rows), 1)
        self.assertEqual(qc["dropped_incomplete_bucket_count"], 1)
        self.assertEqual(rows[0].bid.open, complete[0].bid.open)
        self.assertEqual(rows[0].bid.close, complete[-1].bid.close)

    def test_negative_price_allowed_only_for_finite_real(self):
        self.assertEqual(engine.finite_decimal("-1.25", "FINITE_REAL", "x"), -1.25)
        with self.assertRaises(engine.BacktestError):
            engine.finite_decimal("-1.25", "STRICTLY_POSITIVE", "x")

    def test_manifest_requires_roll_policy_for_continuous_future(self):
        value = manifest_template()
        value["instruments"][0].update({
            "asset_class": "COMMODITY", "series_type": "FUTURES_CONTINUOUS", "price_domain": "FINITE_REAL",
        })
        with self.assertRaises(engine.BacktestError):
            engine.validate_manifest(value)

    def test_prederived_input_and_partial_matrix_are_rejected(self):
        value = manifest_template()
        value["files"][0]["timeframe"] = "D1"
        with self.assertRaises(engine.BacktestError):
            engine.validate_manifest(value)
        value = manifest_template()
        value["files"].pop()
        with self.assertRaises(engine.BacktestError):
            engine.validate_manifest(value)

    def test_strict_json_rejects_duplicate_key(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.json"
            path.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(engine.BacktestError):
                engine.strict_json(path)

    def test_drive_bundle_materializes_safe_members_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / "safe.tar.gz"
            with tarfile.open(bundle, "w:gz") as archive:
                body = b"{}\n"
                info = tarfile.TarInfo("DATASET_MANIFEST.json")
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
            output = root / "safe-output"
            drive_bundle.materialize(bundle, output)
            self.assertEqual((output / "DATASET_MANIFEST.json").read_bytes(), b"{}\n")
            bad = root / "bad.tar.gz"
            with tarfile.open(bad, "w:gz") as archive:
                body = b"x"
                info = tarfile.TarInfo("../escape")
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
            with self.assertRaises(drive_bundle.DriveBundleError):
                drive_bundle.materialize(bad, root / "bad-output")


class PluginTests(unittest.TestCase):
    def load(self, name: str):
        registry = json.loads((ROOT / "strategies" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(item for item in registry["strategies"] if item["plugin"] == name)
        return engine.load_plugin(ROOT / "strategies", row)

    def test_same_sign_plugin_detects_reversal_signal(self):
        quotes = [quote(START + timedelta(hours=value), 100.0) for value in range(30)]
        # index 20 starts after a negative prior change, then six strong positive closes through index 26.
        closes = [100.0] * 30
        closes[19] = 101.0
        closes[20] = 100.0
        for index in range(21, 27):
            closes[index] = closes[index - 1] + 3.0
        for index, close in enumerate(closes):
            row = quotes[index]
            quotes[index] = QuoteBar(
                row.timestamp,
                Bar(row.timestamp, row.bid.open, max(row.bid.high, close), min(row.bid.low, close), close - 0.1),
                Bar(row.timestamp, row.ask.open, max(row.ask.high, close + 0.2), min(row.ask.low, close + 0.2), close + 0.1),
            )
        strategy = {
            "strategy_id": "S", "required_timeframes": ["H1"], "execution_timeframe": "H1",
            "parameters": {"run_length": 6, "atr_period": 14, "minimum_move_atr": 1.25},
        }
        api = engine.StrategyAPI(strategy, {("X", "H1"): quotes})
        signals = self.load("same_sign_exhaustion_v1.py")(api, strategy)
        self.assertTrue(any(row.direction == "SELL" and row.entry_time == START + timedelta(hours=27) for row in signals))
        broken = quotes[:25] + quotes[26:]
        broken_api = engine.StrategyAPI(strategy, {("X", "H1"): broken})
        broken_signals = self.load("same_sign_exhaustion_v1.py")(broken_api, strategy)
        self.assertFalse(any(row.entry_time == START + timedelta(hours=27) for row in broken_signals))

    def test_turn_of_month_uses_only_completed_d1(self):
        h1 = [quote(START + timedelta(hours=value), 100 + value * 0.01) for value in range(24 * 35)]
        d1 = [quote(START + timedelta(days=value), 100 + value * 2.0) for value in range(35)]
        strategy = {
            "strategy_id": "S", "required_timeframes": ["H1", "D1"], "execution_timeframe": "H1",
            "parameters": {"decision_hour_utc": 8, "entry_hour_utc": 9, "completed_d1_count": 21, "atr_period": 14, "minimum_move_atr": 1.0},
        }
        api = engine.StrategyAPI(strategy, {("X", "H1"): h1, ("X", "D1"): d1})
        plugin = self.load("turn_of_month_momentum_v1.py")
        before = plugin(api, strategy)
        future = quote(datetime(2022, 3, 1, tzinfo=UTC), 100000.0)
        api2 = engine.StrategyAPI(strategy, {("X", "H1"): h1, ("X", "D1"): d1 + [future]})
        after = plugin(api2, strategy)
        self.assertEqual(before, after)
        self.assertTrue(all(row.entry_time - row.signal_time == timedelta(hours=1) for row in before))

    def test_turn_of_month_does_not_roll_after_missing_first_entry(self):
        h1 = [quote(START + timedelta(hours=value), 100 + value * 0.01) for value in range(24 * 70)]
        missing = datetime(2022, 2, 1, 9, tzinfo=UTC)
        h1 = [row for row in h1 if row.timestamp != missing]
        d1 = [quote(START + timedelta(days=value), 100 + value * 2.0) for value in range(70)]
        strategy = {
            "strategy_id": "S", "required_timeframes": ["H1", "D1"], "execution_timeframe": "H1",
            "parameters": {"decision_hour_utc": 8, "entry_hour_utc": 9, "completed_d1_count": 21, "atr_period": 14, "minimum_move_atr": 1.0},
        }
        api = engine.StrategyAPI(strategy, {("X", "H1"): h1, ("X", "D1"): d1})
        rows = self.load("turn_of_month_momentum_v1.py")(api, strategy)
        self.assertFalse(any(row.entry_time.year == 2022 and row.entry_time.month == 2 for row in rows))

    def test_restricted_plugin_rejects_file_access(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "bad.py"
            path.write_text("def generate_signals(api, strategy):\n    return open('/etc/passwd')\n", encoding="utf-8")
            with self.assertRaises(engine.BacktestError):
                engine.load_plugin(root, {"plugin": "bad.py", "plugin_sha256": sha(path), "strategy_id": "BAD"})

    def test_plugin_path_and_hash_are_fail_closed(self):
        registry = json.loads((ROOT / "strategies" / "registry.v1.json").read_text(encoding="utf-8"))
        row = registry["strategies"][0]
        self.assertTrue(callable(engine.load_plugin(ROOT / "strategies", row)))
        bad = dict(row, plugin="../core.py")
        with self.assertRaises(engine.BacktestError):
            engine.load_plugin(ROOT / "strategies", bad)
        bad = dict(row, plugin_sha256="0" * 64)
        with self.assertRaises(engine.BacktestError):
            engine.load_plugin(ROOT / "strategies", bad)


class EndToEndTests(unittest.TestCase):
    def create_fixture(self, root: Path):
        data_root = root / "data"
        data_root.mkdir()
        csv_path = data_root / "X_H1.csv"
        lines = [",".join(engine.CSV_HEADER)]
        for index in range(80):
            stamp = START + timedelta(hours=index)
            mid = 100 + index * 0.1
            lines.append(",".join([
                stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                f"{mid - 0.1}", f"{mid + 0.9}", f"{mid - 1.1}", f"{mid}",
                f"{mid + 0.1}", f"{mid + 1.1}", f"{mid - 0.9}", f"{mid + 0.2}",
            ]))
        csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        m1_path = data_root / "X_M1.csv"
        m1_lines = [",".join(engine.CSV_HEADER)]
        for index in range(80 * 60):
            stamp = START + timedelta(minutes=index)
            mid = 100 + index * 0.001
            m1_lines.append(",".join([
                stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                f"{mid - 0.1}", f"{mid + 0.9}", f"{mid - 1.1}", f"{mid}",
                f"{mid + 0.1}", f"{mid + 1.1}", f"{mid - 0.9}", f"{mid + 0.2}",
            ]))
        m1_path.write_text("\n".join(m1_lines) + "\n", encoding="utf-8")
        primary_source_path = data_root / "timestamp-primary-source.txt"
        primary_source_path.write_text("Synthetic fixture timestamps are UTC interval-open instants.\n", encoding="utf-8")
        evidence_path = data_root / "timestamp-semantics.json"
        json_write(evidence_path, {
            "schema_version": "timestamp-semantics-evidence-v1.0.0",
            "status": "VERIFIED",
            "providers": [{
                "provider": "SYNTHETIC", "dataset_or_endpoint": "synthetic fixture",
                "timestamp_column": "timestamp_utc", "timezone": "UTC",
                "timeframes": ["M1", "H1"],
                "semantics_by_timeframe": {
                    "M1": "INTERVAL_OPEN_INSTANT", "H1": "INTERVAL_OPEN_INSTANT",
                },
                "primary_source_locator": "https://example.invalid/synthetic-fixture",
                "primary_source_artifact_path": "timestamp-primary-source.txt",
                "primary_source_artifact_sha256": sha(primary_source_path),
                "primary_source_artifact_bytes": primary_source_path.stat().st_size,
                "review_status": "APPROVED_FOR_BACKTEST",
            }],
        })
        manifest = {
            "schema_version": "unified-market-dataset-v1.0.0", "dataset_id": "SYNTHETIC",
            "timezone": "UTC", "timestamp_semantics": "BAR_OPEN",
            "source_timestamp_semantics": "BAR_OPEN_VERIFIED",
            "timestamp_semantics_evidence": {"path": "timestamp-semantics.json", "sha256": sha(evidence_path), "bytes": evidence_path.stat().st_size},
            "aggregation_profile_id": "UTC_FIXED_V1", "required_direct_timeframes": ["M1", "H1"],
            "start_inclusive": "2022-01-01T00:00:00Z", "end_exclusive": "2022-01-05T00:00:00Z",
            "instruments": [{
                "instrument_id": "X", "provider": "SYNTHETIC", "provider_symbol": "X",
                "asset_class": "COMMODITY", "series_type": "SPOT", "quote_currency": "USD",
                "price_domain": "STRICTLY_POSITIVE", "tick_size": "0.1",
                "roll_policy_id": None, "roll_policy_path": None,
                "roll_policy_sha256": None, "roll_policy_bytes": None,
            }],
            "files": [{
                "instrument_id": "X", "timeframe": "M1", "source_role": "DIRECT_PROVIDER", "path": "X_M1.csv",
                "sha256": sha(m1_path), "bytes": m1_path.stat().st_size, "row_count": 80 * 60,
            }, {
                "instrument_id": "X", "timeframe": "H1", "source_role": "DIRECT_PROVIDER", "path": "X_H1.csv",
                "sha256": sha(csv_path), "bytes": csv_path.stat().st_size, "row_count": 80,
            }],
        }
        manifest_path = data_root / "DATASET_MANIFEST.json"
        json_write(manifest_path, manifest)
        config = json.loads((ROOT / "spec" / "backtest_config.v1.json").read_text(encoding="utf-8"))
        config["splits"] = [{
            "name": "REUSED_2022_2023",
            "start_inclusive": "2022-01-01T00:00:00Z",
            "end_exclusive": "2022-01-04T00:00:00Z",
        }]
        config["promotion_gate"]["required_splits"] = ["REUSED_2022_2023"]
        config["promotion_gate"]["minimum_positive_instrument_count"] = 1
        config["promotion_gate"]["minimum_positive_mean_r_quarters"] = 1
        config_path = root / "config.json"
        json_write(config_path, config)
        strategy_root = root / "strategies"
        strategy_root.mkdir()
        plugin_path = strategy_root / "fixture.py"
        plugin_path.write_text(
            "def generate_signals(api, strategy):\n"
            "    bars = api.series('X', 'H1')\n"
            "    return [api.signal(strategy['strategy_id'], 'X', 'BUY', bars[21].timestamp, bars[21].timestamp)]\n",
            encoding="utf-8",
        )
        registry = {
            "schema_version": "unified-strategy-registry-v1.0.0", "status": "FROZEN_BEFORE_FIRST_UNIFIED_BACKTEST",
            "strategies": [{
                "strategy_id": "FIXTURE-V1", "enabled": True, "plugin": "fixture.py", "plugin_sha256": sha(plugin_path),
                "name_ja": "合成", "hypothesis_ja": "合成テスト", "entry_logic_ja": ["固定"], "exit_logic_ja": ["12h"],
                "required_timeframes": ["H1"], "execution_timeframe": "H1", "episode_overlap_hours": 12,
                "signal_to_entry_hours": 0, "timestamp_geometry_gate": None,
                "frequency_gate_split": "REUSED_2022_2023", "minimum_primary_trades_per_split": 1,
                "parameters": {},
                "frequency_gate": {"episodes_min": 1, "active_dates_min": 1, "instruments_with_minimum_count": 1, "minimum_count_per_instrument": 1, "maximum_instrument_share": 1.0, "minimum_each_year_share": 0.0},
            }],
        }
        registry_path = strategy_root / "registry.json"
        json_write(registry_path, registry)
        return data_root, manifest_path, config_path, registry_path

    def test_complete_run_and_summary_has_no_trade_rows_or_prices(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_root, manifest, config, registry = self.create_fixture(root)
            output = root / "output"
            args = engine.parse_args([
                "--data-root", str(data_root), "--dataset-manifest", str(manifest),
                "--config", str(config), "--strategy-registry", str(registry),
                "--output-root", str(output),
            ])
            summary = engine.run(args)
            self.assertEqual(summary["status"], "COMPLETE")
            self.assertEqual(summary["strategies"][0]["status"], "REUSED_DATA_RETURN_EVALUATED")
            self.assertTrue((output / "phase1" / "FIXTURE-V1.json").is_file())
            self.assertTrue((output / "artifact_manifest_sha256.txt").is_file())
            verify_output.verify(output)
            text = (output / "BACKTEST_SUMMARY.json").read_text(encoding="utf-8")
            for forbidden in ('"entry_price"', '"exit_price"', '"entry_time"', '"exit_time"'):
                self.assertNotIn(forbidden, text)
            phase = json.loads((output / "phase1" / "FIXTURE-V1.json").read_text(encoding="utf-8"))
            self.assertTrue(all(candle["time"] < "2023-01-01T00:00:00Z" for chart in phase["charts"] for candle in chart["candles"]))

    def test_split_episode_identity_is_future_invariant(self):
        strategy = {"episode_overlap_hours": 12}
        before = [
            Signal("S", "X", "BUY", datetime(2023, 12, 30, 0, tzinfo=UTC), datetime(2023, 12, 30, 0, tzinfo=UTC), "H1"),
            Signal("S", "X", "BUY", datetime(2023, 12, 30, 6, tzinfo=UTC), datetime(2023, 12, 30, 6, tzinfo=UTC), "H1"),
        ]
        future = Signal("S", "X", "BUY", datetime(2024, 1, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 1, tzinfo=UTC), "H1")
        start = datetime(2022, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 1, tzinfo=UTC)
        _, left, _ = engine.episodes_for_interval(strategy, before, start, end)
        _, right, _ = engine.episodes_for_interval(strategy, before + [future], start, end)
        self.assertEqual(engine.signal_identity(left), engine.signal_identity(right))

    def test_episode_crossing_split_boundary_is_not_counted_twice(self):
        strategy = {"episode_overlap_hours": 12}
        old = Signal("S", "X", "BUY", datetime(2023, 12, 31, 20, tzinfo=UTC), datetime(2023, 12, 31, 20, tzinfo=UTC), "H1")
        new = Signal("S", "X", "BUY", datetime(2024, 1, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, 1, tzinfo=UTC), "H1")
        rows = [old, new]
        _, left, _ = engine.episodes_for_interval(
            strategy, rows, datetime(2022, 1, 1, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC)
        )
        _, right, purged = engine.episodes_for_interval(
            strategy, rows, datetime(2024, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC)
        )
        self.assertEqual(left, [old])
        self.assertEqual(right, [])
        self.assertEqual(purged, 1)

    def test_summary_verifier_rejects_extra_price_channel(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_root, manifest, config, registry = self.create_fixture(root)
            output = root / "output"
            engine.run(engine.parse_args([
                "--data-root", str(data_root), "--dataset-manifest", str(manifest),
                "--config", str(config), "--strategy-registry", str(registry),
                "--output-root", str(output),
            ]))
            summary_path = output / "BACKTEST_SUMMARY.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["raw_prices"] = [1.0, 2.0]
            json_write(summary_path, summary)
            manifest_path = output / "artifact_manifest_sha256.txt"
            lines = [
                f"{sha(path)}  {path.relative_to(output).as_posix()}"
                for path in sorted(item for item in output.rglob("*") if item.is_file() and item != manifest_path)
            ]
            manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(engine.BacktestError):
                verify_output.verify(output)

    def test_dataset_rejects_h1_without_exact_60_m1_bucket(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_root, manifest_path, config, registry = self.create_fixture(root)
            m1_path = data_root / "X_M1.csv"
            rows = m1_path.read_text(encoding="utf-8").splitlines()
            m1_path.write_text("\n".join([rows[0], *rows[2:]]) + "\n", encoding="utf-8")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            m1 = next(row for row in manifest["files"] if row["timeframe"] == "M1")
            m1.update({
                "sha256": sha(m1_path),
                "bytes": m1_path.stat().st_size,
                "row_count": m1["row_count"] - 1,
            })
            json_write(manifest_path, manifest)
            args = engine.parse_args([
                "--data-root", str(data_root), "--dataset-manifest", str(manifest_path),
                "--config", str(config), "--strategy-registry", str(registry),
                "--output-root", str(root / "output"),
            ])
            with self.assertRaises(engine.BacktestError):
                engine.run(args)

    def test_timestamp_geometry_requires_completed_d1(self):
        h1 = [quote(START + timedelta(hours=value), 100) for value in range(24 * 40)]
        d1 = [quote(START + timedelta(days=value), 100) for value in range(10)]
        strategy = {"timestamp_geometry_gate": {
            "kind": "MONTHLY_FIRST_ELIGIBLE_DATE", "decision_hour_utc": 8, "entry_hour_utc": 9,
            "completed_d1_count": 21, "slots_min": 1, "distinct_entry_utc_dates_min": 1,
            "each_evaluation_year_capacity_min": 1, "instruments_with_minimum_count": 1,
            "minimum_count_per_instrument": 1, "maximum_instrument_share": 1.0,
        }}
        split = {"start_inclusive": "2022-01-01T00:00:00Z", "end_exclusive": "2023-01-01T00:00:00Z"}
        result = engine.timestamp_geometry_result(strategy, {("X", "H1"): h1, ("X", "D1"): d1}, split)
        self.assertEqual(result["status"], "FAIL")

    def test_causality_audit_rejects_future_dependent_prefix(self):
        rows = [quote(START + timedelta(hours=value), -100 if value < 10 else 100) for value in range(20)]
        strategy = {
            "strategy_id": "S", "required_timeframes": ["H1"], "execution_timeframe": "H1",
        }

        def future_dependent(api, current):
            bars = api.series("X", "H1")
            if bars[-1].close > 0:
                return [api.signal("S", "X", "BUY", bars[1].timestamp, bars[1].timestamp)]
            return []

        api = engine.StrategyAPI(strategy, {("X", "H1"): rows})
        full = future_dependent(api, strategy)
        with self.assertRaises(engine.BacktestError):
            engine.causality_audit(
                future_dependent, strategy, {("X", "H1"): rows}, full,
                [START + timedelta(hours=10)],
            )

    def test_output_root_must_be_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / "keep.txt").write_text("x", encoding="utf-8")
            with self.assertRaises(engine.BacktestError):
                engine.prepare_output_root(path)

    def test_phase1_validator_rejects_result_sign_mismatch(self):
        payload = {
            "meta": {"report_title": "x", "status": "x"},
            "strategy": {"strategy_id": "S", "name": "n", "hypothesis": "h", "entry_logic": [], "exit_logic": [], "future_tests": []},
            "charts": [{
                "id": "c", "symbol": "X", "timeframe": "H1", "period": "p",
                "candles": [
                    {"time": "2022-01-01T00:00:00Z", "open": 1, "high": 2, "low": 0, "close": 1, "volume": None},
                    {"time": "2022-01-01T01:00:00Z", "open": 1, "high": 2, "low": 0, "close": 1, "volume": None},
                ], "overlays": [], "panes": [],
            }],
            "trades": [{
                "no": 1, "chart_id": "c", "side": "BUY", "entry_i": 0, "exit_i": 1,
                "entry_price": 1, "exit_price": 1, "stop": None, "target": None,
                "r": -1, "result": "WIN", "confidence": None, "setup": "s", "note": "n",
            }],
            "notes": [],
        }
        with self.assertRaises(engine.BacktestError):
            engine.validate_phase1(payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
