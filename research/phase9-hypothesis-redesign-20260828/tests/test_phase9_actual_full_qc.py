from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


actual = load_module("phase9_actual_full_qc", ROOT / "runner/phase9_actual_full_qc.py")


def csv_row(timestamp: str, values: str = "1.0000000000,1.1000000000,0.9000000000,1.0500000000,10.0000000000") -> bytes:
    return f"{timestamp},{values}\n".encode("ascii")


class ActualFullQcContractTests(unittest.TestCase):
    def test_exact_frozen_48_series_and_boundaries(self):
        self.assertEqual(len(actual.SPECS), 48)
        self.assertEqual(len({spec.filename for spec in actual.SPECS}), 48)
        self.assertEqual(actual.parse_timestamp("2019-07-31T23:00:00Z", "H1"), actual.END["H1"] - timedelta(hours=1))
        with self.assertRaises(actual.ActualQcError):
            actual.parse_timestamp("2019-08-01T00:00:00Z", "H1")
        with self.assertRaises(actual.ActualQcError):
            actual.parse_timestamp("2019-08-28T00:00:00Z", "M15")
        with self.assertRaises(actual.ActualQcError):
            actual.parse_timestamp("2013-01-01T00:01:00Z", "M15")

    def test_strict_csv_parser_rejects_geometry_nonfinite_and_crlf(self):
        spec = actual.SeriesSpec("AUDJPY", "M15", "bid")
        actual.parse_row(csv_row("2013-01-01T00:00:00Z"), spec)
        for row in (
            csv_row("2013-01-01T00:00:00Z", "NaN,1,1,1,1"),
            csv_row("2013-01-01T00:00:00Z", "1,0.9,0.8,1,1"),
            csv_row("2013-01-01T00:00:00Z")[:-1] + b"\r\n",
        ):
            with self.subTest(row=row), self.assertRaises(actual.ActualQcError):
                actual.parse_row(row, spec)

    def test_bid_ask_gate_uses_frozen_open_rule_and_records_volume_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = actual.CSV_HEADER
            bid = header + csv_row("2013-01-01T00:00:00Z", "1.0,2.0,0.5,1.5,10")
            ask = header + csv_row("2013-01-01T00:00:00Z", "1.1,1.6,0.6,1.2,10")
            (root / "AUDJPY_M15_bid.csv").write_bytes(bid)
            (root / "AUDJPY_M15_ask.csv").write_bytes(ask)
            result = actual.validate_bid_ask(root, "AUDJPY", "M15")
            self.assertEqual(result["bid_ask_volume_mismatch_count"], 0)
            (root / "AUDJPY_M15_ask.csv").write_bytes(
                header + csv_row("2013-01-01T00:00:00Z", "1.1,1.6,0.6,1.2,11")
            )
            result = actual.validate_bid_ask(root, "AUDJPY", "M15")
            self.assertEqual(result["bid_ask_volume_mismatch_count"], 1)

    def test_allowlist_requires_canonical_separate_git_commit_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "phase9@example.invalid"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Phase9 Test"], cwd=repo, check=True)
            (repo / "source.txt").write_text("source\n", encoding="ascii")
            subprocess.run(["git", "add", "source.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "source run"], cwd=repo, check=True)
            source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            canonical = repo / actual.CANONICAL_ALLOWLIST
            canonical.parent.mkdir(parents=True)
            manifest_sha = hashlib.sha256(b"{}\n").hexdigest()
            value = {
                "schema_version": "phase9-provider-schedule-exact-allowlist-v1.0",
                "status": "SEPARATE_COMMIT_EXACT_ALLOWLIST_FROZEN",
                "source_run_id": 123,
                "source_head_sha": source,
                "source_artifact_id": 456,
                "source_artifact_zip_sha256": "a" * 64,
                "inventory_manifest_sha256": manifest_sha,
                "freeze_parent_sha": source,
                "same_run_self_authorization_used": False,
            }
            canonical.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
            subprocess.run(["git", "add", actual.CANONICAL_ALLOWLIST.as_posix()], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "freeze allowlist"], cwd=repo, check=True)
            (repo / "execution.txt").write_text("execution\n", encoding="ascii")
            subprocess.run(["git", "add", "execution.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "execution"], cwd=repo, check=True)
            actual.validate_schedule_allowlist(canonical, manifest_sha, repo)
            forged = repo / "forged.json"
            forged.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(actual.ActualQcError):
                actual.validate_schedule_allowlist(forged, manifest_sha, repo)

    def manifest(self) -> dict:
        rows = []
        for instrument in actual.INSTRUMENTS:
            for timeframe in actual.TIMEFRAMES:
                rows.append({
                    "path": f"{instrument}_{timeframe}.timestamps",
                    "sha256": "0" * 64,
                    "scheduled_slot_count": 1,
                    "first_timestamp": "2013-01-01T00:00:00Z",
                    "last_timestamp": "2013-01-01T00:00:00Z",
                })
        return {
            "schema_version": "phase9-provider-schedule-inventory-v1.0",
            "status": "FROZEN_PROVIDER_SCHEDULE_INVENTORY",
            "source": "authenticated-provider-metadata",
            "provider_version": "test-version",
            "observed_at_utc": "2026-09-01T00:00:00Z",
            "timezone": "UTC",
            "bar_timestamp": "BAR_OPEN",
            "coverage_start_inclusive": "2013-01-01T00:00:00Z",
            "coverage_end_exclusive_by_timeframe": {
                "M15": "2019-08-28T00:00:00Z",
                "H1": "2019-08-01T00:00:00Z",
            },
            "complete_interval_inventory": True,
            "derived_from_raw_prices": False,
            "inventory_sha256": "0" * 64,
            "series": rows,
        }

    def test_current_unversioned_calendar_is_rejected_before_raw_access(self):
        current = ROOT / "data_manifest/trading_calendar.json"
        with self.assertRaises(actual.ActualQcError):
            actual.validate_schedule_contract(current)

    def test_schedule_contract_rejects_raw_derived_or_incomplete_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            value = self.manifest()
            path.write_text(json.dumps(value), encoding="utf-8")
            actual.validate_schedule_contract(path)
            value["derived_from_raw_prices"] = True
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(actual.ActualQcError):
                actual.validate_schedule_contract(path)

    def test_tiny_24_schedule_fixture_cannot_claim_full_period(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = self.manifest()
            inventory = hashlib.sha256()
            for row in sorted(value["series"], key=lambda item: item["path"]):
                path = root / row["path"]
                path.write_text("2013-01-01T00:00:00Z\n", encoding="ascii")
                row["sha256"] = actual.sha256_file(path)
                inventory.update(f'{row["sha256"]}  {row["path"]}\n'.encode("ascii"))
            value["inventory_sha256"] = inventory.hexdigest()
            with self.assertRaises(actual.ActualQcError):
                actual.validate_schedule_files(value, root)

    def test_raw_mode_change_after_custody_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for spec in actual.SPECS:
                path = root / spec.filename
                path.write_bytes(actual.CSV_HEADER)
                path.chmod(0o600)
            actual.validate_raw_set(root)
            target_spec = actual.SPECS[0]
            target = root / target_spec.filename
            target.chmod(0o644)
            with self.assertRaises(actual.ActualQcError):
                list(actual.iter_rows(target, target_spec))
            actual._PINNED_RAW.clear()
            actual._PINNED_RAW_ROOT = None

    def test_h4_bucket_is_created_only_when_all_scheduled_h1_are_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schedule = root / "AUDJPY_H1.timestamps"
            schedule.write_text(
                "".join(f"2013-01-01T0{hour}:00:00Z\n" for hour in range(4)), encoding="ascii"
            )
            spec = actual.SeriesSpec("AUDJPY", "H1", "bid")
            raw = root / spec.filename
            raw.write_bytes(actual.CSV_HEADER + b"".join(
                csv_row(f"2013-01-01T0{hour}:00:00Z") for hour in range(4)
            ))
            result = actual.derived_bucket_audit(raw, spec, schedule, 4)
            self.assertEqual(result["created_complete_bucket_count"], 1)
            self.assertEqual(result["dropped_source_missing_bucket_count"], 0)
            self.assertRegex(result["derived_ohlcv_sha256"], r"^[0-9a-f]{64}$")
            raw.write_bytes(actual.CSV_HEADER + b"".join(
                csv_row(f"2013-01-01T0{hour}:00:00Z") for hour in range(3)
            ))
            result = actual.derived_bucket_audit(raw, spec, schedule, 4)
            self.assertEqual(result["created_complete_bucket_count"], 0)
            self.assertEqual(result["dropped_source_missing_bucket_count"], 1)

    def test_d1_requires_all_24_h1_and_hashes_aggregated_ohlcv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            schedule = root / "AUDJPY_H1.timestamps"
            lines = [actual.iso(actual.START + timedelta(hours=hour)) for hour in range(24)]
            schedule.write_text("".join(value + "\n" for value in lines), encoding="ascii")
            spec = actual.SeriesSpec("AUDJPY", "H1", "bid")
            raw = root / spec.filename
            raw.write_bytes(actual.CSV_HEADER + b"".join(csv_row(value) for value in lines))
            complete = actual.derived_bucket_audit(raw, spec, schedule, 24)
            self.assertEqual(complete["created_complete_bucket_count"], 1)
            digest = complete["derived_ohlcv_sha256"]
            raw.write_bytes(actual.CSV_HEADER + b"".join(
                csv_row(value, "1,1.2,0.8,1.1,11" if index == 23 else "1,1.1,0.9,1.05,10")
                for index, value in enumerate(lines)
            ))
            changed = actual.derived_bucket_audit(raw, spec, schedule, 24)
            self.assertNotEqual(changed["derived_ohlcv_sha256"], digest)
            raw.write_bytes(actual.CSV_HEADER + b"".join(csv_row(value) for value in lines[:-1]))
            partial = actual.derived_bucket_audit(raw, spec, schedule, 24)
            self.assertEqual(partial["created_complete_bucket_count"], 0)

    def test_cross_market_stream_uses_exact_frozen_group(self):
        start = actual.START
        factories = {
            member: (lambda member=member: iter([start] if member == "XAUUSD" else []))
            for member in actual.FROZEN_GROUPS["METALS2"]
        }
        result = actual.cross_market_stream("METALS2", "H1", factories)
        self.assertEqual(result["union_count"], 1)
        self.assertEqual(result["intersection_count"], 0)
        self.assertEqual(result["missing_member_occurrences"], 1)
        with self.assertRaises(actual.ActualQcError):
            actual.cross_market_stream("METALS2", "H1", {"XAUUSD": lambda: iter([])})

    def test_atomic_report_rejects_existing_part_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            target = root / "target"
            target.write_text("do-not-touch", encoding="utf-8")
            report.with_suffix(".json.part").symlink_to(target)
            with self.assertRaises(actual.ActualQcError):
                actual.atomic_json(report, {"safe": True})
            self.assertEqual(target.read_text(encoding="utf-8"), "do-not-touch")

    def test_contract_and_source_keep_authorization_false_and_no_result_metrics(self):
        contract = json.loads((ROOT / "spec/provider_schedule_contract.frozen.json").read_text(encoding="utf-8"))
        self.assertFalse(contract["authorization_state"]["count_only_authorized"])
        self.assertFalse(contract["authorization_state"]["research_outcomes_calculated"])
        self.assertEqual(contract["authorization_state"]["outcome_fields"], [])
        source = (ROOT / "runner/phase9_actual_full_qc.py").read_text(encoding="utf-8").casefold()
        for prohibited in ("mfe", "mae", "profit_factor", "drawdown", "win_rate", "p_value", "cumulative_r"):
            self.assertNotIn(prohibited, source)


if __name__ == "__main__":
    unittest.main()
