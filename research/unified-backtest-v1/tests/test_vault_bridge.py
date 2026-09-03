#!/usr/bin/env python3
"""Synthetic tests for the FXCM Vault to unified-input adapter."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runner"
if str(RUNNER) not in sys.path:
    sys.path.insert(0, str(RUNNER))

import unified_backtest as engine
import vault_to_bundle as bridge


def source_row(timestamp: str, crossed_close: bool = False) -> list[str]:
    return [
        timestamp,
        "1.00000", "1.10000", "0.90000", "1.00000",
        "1.01000", "1.11000", "0.91000", "0.99000" if crossed_close else "1.01000",
        "ABSENT_FROM_SOURCE_SCHEMA", "",
    ]


def write_source(path: Path, rows: list[list[str]]) -> dict:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(bridge.SOURCE_HEADER)
        writer.writerows(rows)
    return {
        "canonical_csv_sha256": bridge.sha256_file(path),
        "canonical_row_count": len(rows),
        "canonical_first_timestamp_utc": rows[0][0],
        "canonical_last_timestamp_utc": rows[-1][0],
    }


class VaultBridgeTests(unittest.TestCase):
    def test_bridge_accepts_current_cache_bypass_recovery_version(self):
        self.assertEqual(bridge.RECOVERY_VERSION, "simple-v1.2")
        self.assertEqual(bridge.OPERATIONAL_VERSION, "v2.1+simple-v1.2-recovery")

    def test_expected_manifest_sha_list_is_exact(self):
        text = ",".join(f"{year}:{str(year)[-1] * 64}" for year in bridge.YEARS)
        self.assertEqual(set(bridge.parse_expected_manifest_sha256s(text)), set(bridge.YEARS))
        with self.assertRaises(bridge.BridgeError):
            bridge.parse_expected_manifest_sha256s(text.rsplit(",", 1)[0])
        with self.assertRaises(bridge.BridgeError):
            bridge.parse_expected_manifest_sha256s(text + ",2025:" + "f" * 64)

    def test_m1_to_h1_exact_intersection_and_numeric_text_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m1 = root / "M1-source.csv"
            rows = [source_row(f"2022-01-01T00:{minute:02d}:00Z") for minute in range(60)]
            m1_identity = write_source(m1, rows)
            m1_output = root / "M1-output.csv"
            with m1_output.open("x", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(bridge.TARGET_HEADER)
                last, retained, complete, quarantined = bridge.append_m1_and_build_h1(
                    m1, writer, m1_identity, None
                )
            self.assertEqual(last, "2022-01-01T00:59:00Z")
            self.assertEqual(retained, 60)
            self.assertEqual(quarantined, [])
            self.assertEqual(list(complete), ["2022-01-01T00:00:00Z"])
            self.assertIn("1.00000,1.10000,0.90000,1.00000", m1_output.read_text(encoding="utf-8"))

            h1 = root / "H1-source.csv"
            h1_identity = write_source(h1, [source_row("2022-01-01T00:00:00Z")])
            h1_output = root / "H1-output.csv"
            with h1_output.open("x", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(bridge.TARGET_HEADER)
                _, h1_retained, missing, mismatches, crossed = bridge.append_h1_intersection(
                    h1, writer, h1_identity, None, complete
                )
            self.assertEqual((h1_retained, missing, mismatches, crossed), (1, [], [], []))

            mismatched_values = source_row("2022-01-01T00:00:00Z")
            mismatched_values[4] = "1.02000"
            mismatched_values[8] = "1.03000"
            mismatch_source = root / "H1-mismatch.csv"
            mismatch_identity = write_source(mismatch_source, [mismatched_values])
            mismatch_output = root / "H1-mismatch-output.csv"
            with mismatch_output.open("x", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(bridge.TARGET_HEADER)
                _, retained, missing, mismatches, crossed = bridge.append_h1_intersection(
                    mismatch_source, writer, mismatch_identity, None, complete
                )
            self.assertEqual((retained, missing, mismatches, crossed), (
                1, [], ["2022-01-01T00:00:00Z"], [],
            ))

    def test_crossed_close_is_quarantined_without_fill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            m1 = root / "M1.csv"
            rows = [
                source_row(f"2022-01-01T00:{minute:02d}:00Z", crossed_close=(minute == 20))
                for minute in range(60)
            ]
            identity = write_source(m1, rows)
            output = root / "out.csv"
            with output.open("x", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(bridge.TARGET_HEADER)
                _, retained, complete, quarantined = bridge.append_m1_and_build_h1(
                    m1, writer, identity, None
                )
            self.assertEqual(retained, 59)
            self.assertEqual(quarantined, ["2022-01-01T00:20:00Z"])
            self.assertEqual(complete, {})

    def test_archive_member_allowlist_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_tar = root / "source.tar"
            source_identity = {
                "schema_version": "phase9-exploratory-fxcm-drive-vault-shard-payload-v2.0.0",
                "vault_version": "v2", "year": 2022, "symbol": "EURUSD", "periodicity": "m1",
                "calendar_clip": {"start_inclusive": "2022-01-01T00:00:00Z", "end_exclusive": "2023-01-01T00:00:00Z"},
                "base_week_count": 52, "present_week_indices": [], "known_missing_week_indices": list(range(1, 53)),
                "source_object_count": 0, "source_objects": [], "observed_row_count": 1, "usable_row_count": 1,
                "crossed_quote_count": 0, "crossed_quote_event_sha256": hashlib.sha256(b"").hexdigest(),
                "clipped_outside_year_row_count": 0, "duplicate_count": 0, "gap_segment_count": 0,
                "missing_nominal_slot_count": 0, "canonical_row_count": 1,
                "canonical_first_timestamp_utc": "2022-01-01T00:00:00Z",
                "canonical_last_timestamp_utc": "2022-01-01T00:00:00Z",
                "canonical_timestamp_sha256": "a" * 64, "canonical_csv_sha256": "b" * 64,
                "field_schema": list(bridge.SOURCE_HEADER), "volume_status": "ABSENT_FROM_SOURCE_SCHEMA",
                "forward_fill_count": 0, "interpolation_count": 0, "qc_status": "PASS",
            }
            with tarfile.open(raw_tar, "x", format=tarfile.USTAR_FORMAT) as archive:
                for name, body in (
                    ("SHARD_PAYLOAD_MANIFEST.json", bridge.canonical_bytes(source_identity)),
                    ("canonical/prices.csv", b"x\n"),
                ):
                    info = tarfile.TarInfo(name)
                    info.size = len(body)
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(body))
            archive_path = root / "source.tar.zst"
            subprocess.run(["zstd", "-q", "-o", archive_path, raw_tar], check=True)
            output = root / "prices.csv"
            bridge.extract_canonical_csv(archive_path, output, source_identity, root / "inspect.tar")
            self.assertEqual(output.read_bytes(), b"x\n")

            bad_tar = root / "bad.tar"
            with tarfile.open(bad_tar, "x", format=tarfile.USTAR_FORMAT) as archive:
                info = tarfile.TarInfo("../escape")
                info.size = 1
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(b"x"))
            bad_archive = root / "bad.tar.zst"
            subprocess.run(["zstd", "-q", "-o", bad_archive, bad_tar], check=True)
            with self.assertRaises(bridge.BridgeError):
                bridge.extract_canonical_csv(bad_archive, root / "bad.csv", source_identity, root / "bad-inspect.tar")

    def test_empirical_timestamp_profile_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.json"
            source.write_text("{}\n", encoding="utf-8")
            evidence = root / "evidence.json"
            evidence.write_text(json.dumps({
                "schema_version": "timestamp-semantics-evidence-v1.0.0",
                "status": "EMPIRICALLY_ALIGNED_ASSUMPTION",
                "providers": [{
                    "provider": "FXCM CandleData",
                    "dataset_or_endpoint": "fixture",
                    "timestamp_column": "timestamp_utc",
                    "timezone": "UTC",
                    "timeframes": ["M1", "H1"],
                    "semantics_by_timeframe": {"M1": "INTERVAL_OPEN_INSTANT", "H1": "INTERVAL_OPEN_INSTANT"},
                    "primary_source_locator": "https://example.invalid/fxcm",
                    "primary_source_artifact_path": "source.json",
                    "primary_source_artifact_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "primary_source_artifact_bytes": source.stat().st_size,
                    "review_status": "APPROVED_FOR_EXPLORATORY_BACKTEST_ONLY",
                }],
            }) + "\n", encoding="utf-8")
            paths = engine.validate_timestamp_evidence(
                evidence,
                root,
                {"FXCM CandleData"},
                "BAR_OPEN_EMPIRICALLY_ALIGNED_PROVIDER_NOT_EXPLICIT",
            )
            self.assertEqual(paths, ["source.json"])
            with self.assertRaises(engine.BacktestError):
                engine.validate_timestamp_evidence(evidence, root, {"FXCM CandleData"}, "BAR_OPEN_VERIFIED")


if __name__ == "__main__":
    unittest.main()
