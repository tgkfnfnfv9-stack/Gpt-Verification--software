from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN_SYMBOLS = [
    "AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY",
    "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD",
]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


acquire = load_module("phase9_acquire", ROOT / "runner" / "acquire_phase9_data.py")
validate_mod = load_module("phase9_validate", ROOT / "runner" / "validate_phase9_acquisition.py")


class Phase9AcquisitionTests(unittest.TestCase):
    def write_series(
        self,
        path: Path,
        timeframe: str,
        invalid_time: str | None = None,
        repeated_time: bool = False,
        ask_below_bid: bool = False,
    ) -> None:
        times = (
            ["2013-01-01T00:00:00Z", "2013-01-01T00:15:00Z"]
            if timeframe == "M15"
            else ["2013-01-01T00:00:00Z", "2013-01-01T01:00:00Z"]
        )
        if invalid_time:
            times[0] = invalid_time
        if repeated_time:
            times[1] = times[0]
        ask = path.stem.endswith("_ask")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for timestamp in times:
                base = 1.1 + ((-0.0002 if ask_below_bid else 0.0002) if ask else 0.0)
                writer.writerow([timestamp, base, base + 0.001, base - 0.001, base + 0.0001, 10])

    def create_complete_fixture(self, directory: Path) -> None:
        symbols, names = validate_mod.expected_files()
        self.assertEqual(len(symbols), 12)
        for name in names:
            timeframe = name.split("_")[1]
            self.write_series(directory / name, timeframe)

    def test_frozen_boundaries_and_exact_plan(self):
        acquire.assert_frozen_configuration()
        base = ROOT.parents[2] / "phase9-plan-test"
        output_dir = base / "raw"
        cache_root = base / "cache"
        jar_path = base / "phase9-jforex-acquirer.jar"
        plan = acquire.build_plan(output_dir, cache_root, jar_path)
        self.assertEqual(len(plan), 4)
        self.assertEqual(sum(len(row["output_files"]) for row in plan), 48)
        expected = []
        for timeframe in ("M15", "H1"):
            for side in ("bid", "ask"):
                expected.append(
                    {
                        "timeframe": timeframe,
                        "side": side,
                        "start_inclusive": "2013-01-01T00:00:00Z",
                        "end_exclusive": (
                            "2019-08-28T00:00:00Z"
                            if timeframe == "M15"
                            else "2019-08-01T00:00:00Z"
                        ),
                        "output_files": [
                            f"{symbol}_{timeframe}_{side}.csv" for symbol in FROZEN_SYMBOLS
                        ],
                        "command": [
                            "java", "-jar", str(jar_path),
                            "--output-dir", str(output_dir),
                            "--cache-dir", str(cache_root / f"{timeframe}-{side}"),
                            "--timeframe", timeframe,
                            "--side", side,
                        ],
                    }
                )
        self.assertEqual(plan, expected)

    def test_execution_and_date_override_are_fail_closed(self):
        runner = ROOT / "runner" / "acquire_phase9_data.py"
        with tempfile.TemporaryDirectory(dir=ROOT.parents[2]) as temporary:
            temporary_path = Path(temporary)
            blocked = subprocess.run(
                [
                    sys.executable, str(runner),
                    "--output-dir", str(temporary_path / "raw"),
                    "--cache-root", str(temporary_path / "cache"),
                    "--jar", str(temporary_path / "runner.jar"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("Exact JForex acquisition confirmation", blocked.stderr)
            override = subprocess.run(
                [
                    sys.executable, str(runner),
                    "--output-dir", str(temporary_path / "raw"),
                    "--cache-root", str(temporary_path / "cache"),
                    "--jar", str(temporary_path / "runner.jar"),
                    "--from", "2025-01-01",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(override.returncode, 0)
            self.assertIn("unrecognized arguments", override.stderr)

    def test_java_runner_has_no_date_arguments_and_no_order_submission(self):
        source = (
            ROOT
            / "runner/jforex/src/main/java/org/phase9/Phase9JForexAcquirer.java"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"--from"', source)
        self.assertNotIn('"--to"', source)
        for prohibited in ("submitOrder", "getLastTick", "getReportData", "createReport"):
            self.assertNotIn(prohibited, source)
        self.assertIn('Instant.parse("2019-08-01T00:00:00Z")', source)
        self.assertIn('Instant.parse("2019-08-28T00:00:00Z")', source)

    def test_raw_output_inside_repository_is_rejected(self):
        with self.assertRaises(ValueError):
            acquire.checked_external_dir(str(ROOT / "data"), "Raw output directory")

    def test_complete_48_series_fixture_passes_without_outcomes(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            manifest = validate_mod.validate(raw, output)
            self.assertEqual(manifest["series_count"], 48)
            self.assertFalse(manifest["research_outcomes_calculated"])
            self.assertFalse(manifest["warmup_signal_generation_allowed"])
            self.assertFalse(manifest["full_quality_gate_passed"])
            self.assertFalse(manifest["count_only_authorized"])
            self.assertFalse(manifest["outcome_access_authorized"])
            text = (output / "acquisition_manifest.json").read_text(encoding="utf-8")
            for prohibited in ("forward_return", "MFE", "MAE", "win_rate", "profit_factor"):
                self.assertNotIn(prohibited, text)

    def test_end_exclusive_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            for side in ("bid", "ask"):
                self.write_series(raw / f"AUDJPY_M15_{side}.csv", "M15", "2019-08-28T00:00:00Z")
            with self.assertRaisesRegex(ValueError, "outside frozen interval"):
                validate_mod.validate(raw, output)

    def test_before_start_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            for side in ("bid", "ask"):
                self.write_series(raw / f"AUDJPY_H1_{side}.csv", "H1", "2012-12-31T23:00:00Z")
            with self.assertRaisesRegex(ValueError, "outside frozen interval"):
                validate_mod.validate(raw, output)

    def test_h1_august_tail_is_rejected_for_both_sides(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            for side in ("bid", "ask"):
                self.write_series(raw / f"AUDJPY_H1_{side}.csv", "H1", "2019-08-01T00:00:00Z")
            with self.assertRaisesRegex(ValueError, "outside frozen interval"):
                validate_mod.validate(raw, output)

    def test_extra_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            self.write_series(raw / "EXTRA_M15_bid.csv", "M15")
            with self.assertRaisesRegex(ValueError, "Raw file set mismatch"):
                validate_mod.validate(raw, output)

    def test_missing_csv_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            (raw / "AUDJPY_M15_bid.csv").unlink()
            with self.assertRaisesRegex(ValueError, "Raw file set mismatch"):
                validate_mod.validate(raw, output)

    def test_unexpected_non_csv_and_extra_column_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            (raw / "outcomes.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unexpected raw-directory entries"):
                validate_mod.validate(raw, output)

        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            target = raw / "AUDJPY_M15_bid.csv"
            text = target.read_text(encoding="utf-8")
            target.write_text(text.replace("volume\n", "volume,forward_return\n").replace(",10\n", ",10,0.1\n"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact canonical OHLCV schema"):
                validate_mod.validate(raw, output)

    def test_duplicate_timestamp_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            for side in ("bid", "ask"):
                self.write_series(raw / f"AUDJPY_M15_{side}.csv", "M15", repeated_time=True)
            with self.assertRaisesRegex(ValueError, "not strictly increasing"):
                validate_mod.validate(raw, output)

    def test_bid_ask_timestamp_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            self.write_series(raw / "AUDJPY_M15_ask.csv", "M15", "2013-01-02T00:00:00Z")
            with self.assertRaisesRegex(ValueError, "BID/ASK timestamp mismatch"):
                validate_mod.validate(raw, output)

    def test_crossed_bid_ask_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_tmp, tempfile.TemporaryDirectory() as parent:
            raw = Path(raw_tmp)
            output = Path(parent) / "manifest"
            self.create_complete_fixture(raw)
            self.write_series(raw / "AUDJPY_M15_ask.csv", "M15", ask_below_bid=True)
            with self.assertRaisesRegex(ValueError, "ASK open below BID open"):
                validate_mod.validate(raw, output)

    def test_session_state_still_has_no_outcome_access(self):
        state = json.loads((ROOT / "SESSION_STATE.json").read_text(encoding="utf-8"))
        self.assertFalse(state["phase9"]["outcome_accessed"])

    def test_workflow_is_isolated_build_preflight_only(self):
        workflow = (
            ROOT.parents[1] / ".github/workflows/phase9-acquisition-only.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("BUILD_PHASE9_JFOREX_PREFLIGHT_ONLY", workflow)
        self.assertIn('M2_REPO=$RUNNER_TEMP/phase9-m2', workflow)
        self.assertEqual(
            workflow.count('mvn -B -ntp -o -s "$MAVEN_USER_SETTINGS"'), 2
        )
        self.assertEqual(workflow.count('-gs "$MAVEN_GLOBAL_SETTINGS"'), 3)
        self.assertIn("maven_repository_sha256.third.txt", workflow)
        self.assertIn("phase9_jforex_runner_sha256.reproducible.txt", workflow)
        for prohibited in (
            "secrets.",
            "DUKASCOPY_USERNAME",
            "DUKASCOPY_PASSWORD",
            "PHASE9_JFOREX_CONFIRM",
            "Acquire frozen JForex bars only",
            'python "$root/runner/validate_phase9_acquisition.py"',
            'java -jar',
        ):
            self.assertNotIn(prohibited, workflow)


if __name__ == "__main__":
    unittest.main()
