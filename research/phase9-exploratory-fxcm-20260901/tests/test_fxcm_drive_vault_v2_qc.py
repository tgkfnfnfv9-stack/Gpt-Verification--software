import csv
import gzip
import shutil
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK / "runner"))
import fxcm_drive_vault_acquire_year as acquire_v1  # noqa: E402
import fxcm_drive_vault_acquire_year_v2 as acquire_v2  # noqa: E402
import fxcm_drive_vault_common as common  # noqa: E402


UTC = timezone.utc


def write_canonical(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(common.CANONICAL_HEADER)
        writer.writerows(rows)


def price_row(timestamp: datetime):
    stamp = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    return [stamp, "1", "1.1", "0.9", "1", "1.01", "1.11", "0.91", "1.01", "ABSENT_FROM_SOURCE_SCHEMA", ""]


class VaultV2QcTests(unittest.TestCase):
    def test_exact_direct_h1_reference_produces_all_v2_timeframes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = datetime(2017, 1, 2, tzinfo=UTC)
            write_canonical(root / "m1.csv", [price_row(start + timedelta(minutes=index)) for index in range(60)])
            write_canonical(root / "h1.csv", [price_row(start)])
            result = acquire_v2.derive_qc_v2(root / "m1.csv", root / "h1.csv", 2017)
            for timeframe in ("M5", "M15", "M30", "H1", "H4", "D1", "W1"):
                self.assertGreater(result[timeframe]["complete_bucket_count"], 0)
            self.assertEqual(result["H1"]["reference_exact_match_count"], 1)
            self.assertTrue(result["batch6_compatibility_passed"])
            self.assertEqual(result["forward_fill_count"], 0)
            self.assertEqual(result["interpolation_count"], 0)

    def test_h1_mismatch_blocks_compatibility_and_outer_w1_is_dropped(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = datetime(2017, 1, 1, tzinfo=UTC)
            rows = [price_row(start + timedelta(minutes=index)) for index in range(60)]
            reference = price_row(start)
            reference[4] = "1.2"
            write_canonical(root / "m1.csv", rows)
            write_canonical(root / "h1.csv", [reference])
            result = acquire_v2.derive_qc_v2(root / "m1.csv", root / "h1.csv", 2017)
            self.assertEqual(result["H1"]["reference_ohlc_mismatch_count"], 1)
            self.assertFalse(result["batch6_compatibility_passed"])
            self.assertEqual(result["W1"]["complete_bucket_count"], 0)
            self.assertEqual(result["W1"]["outer_year_boundary_drop_count"], 1)

    def test_archive_contains_only_frozen_present_weeks(self):
        if shutil.which("zstd") is None:
            self.skipTest("zstd unavailable")
        weeks = (1, 3, 52)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shard = root / "shard"
            (shard / "canonical").mkdir(parents=True)
            (shard / "source").mkdir()
            (shard / "SHARD_PAYLOAD_MANIFEST.json").write_text("{}\n", encoding="utf-8")
            (shard / "canonical/prices.csv").write_text("timestamp_utc\n", encoding="utf-8")
            for week in weeks:
                with (shard / "source" / f"{week:02d}.csv.gz").open("wb") as raw:
                    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped:
                        zipped.write(f"week-{week}\n".encode())
            archive_path = root / "masked.tar.zst"
            acquire_v1.make_archive(shard, archive_path, weeks=weeks)
            tar_path = root / "view.tar"
            import subprocess
            with tar_path.open("wb") as output:
                subprocess.run(["zstd", "-d", "--stdout", str(archive_path)], check=True, stdout=output)
            with tarfile.open(tar_path, "r") as archive:
                self.assertEqual(
                    archive.getnames(),
                    ["SHARD_PAYLOAD_MANIFEST.json", "canonical/prices.csv", "source/01.csv.gz", "source/03.csv.gz", "source/52.csv.gz"],
                )


if __name__ == "__main__":
    unittest.main()
