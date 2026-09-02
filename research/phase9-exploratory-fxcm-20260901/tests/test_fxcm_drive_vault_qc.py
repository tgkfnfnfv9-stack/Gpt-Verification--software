import csv
import gzip
import io
import shutil
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK / "runner"))
import fxcm_drive_vault_acquire_year as acquire  # noqa: E402
import fxcm_drive_vault_common as common  # noqa: E402


UTC = timezone.utc


def write_canonical(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(common.CANONICAL_HEADER)
        writer.writerows(rows)


def price_row(timestamp: datetime, close="1.0"):
    stamp = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
    return [stamp, "1", "1.1", "0.9", close, "1.01", "1.11", "0.91", close, "ABSENT_FROM_SOURCE_SCHEMA", ""]


class VaultQcTests(unittest.TestCase):
    def test_m1_derived_h1_is_canonical_and_reference_mismatch_blocks_batch6_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = datetime(2017, 1, 3, tzinfo=UTC)
            write_canonical(root / "m1.csv", [price_row(start + timedelta(minutes=index)) for index in range(60)])
            write_canonical(root / "h1.csv", [price_row(start, close="1.2")])
            write_canonical(root / "d1.csv", [])
            result = acquire.derive_qc(root / "m1.csv", root / "h1.csv", root / "d1.csv", 2017)
            self.assertEqual(result["H1"]["complete_bucket_count"], 1)
            self.assertEqual(result["H1"]["reference_ohlc_mismatch_count"], 1)
            self.assertFalse(result["batch6_compatibility_passed"])
            self.assertEqual(result["forward_fill_count"], 0)
            self.assertFalse(result["provider_schedule_claimed"])

    def test_bucket_boundaries_include_utc_monday(self):
        value = datetime(2025, 12, 31, 17, 43, tzinfo=UTC)
        self.assertEqual(acquire.bucket_start(value, "M5").minute, 40)
        self.assertEqual(acquire.bucket_start(value, "H4").hour, 16)
        self.assertEqual(acquire.bucket_start(value, "W1"), datetime(2025, 12, 29, tzinfo=UTC))

    def test_invalid_numbers_and_archive_paths_fail(self):
        with self.assertRaises(common.VaultError):
            acquire.decimal_value("nan", "price")
        with self.assertRaises(common.VaultError):
            common.validate_safe_member("../prices.csv")
        with self.assertRaises(common.VaultError):
            common.validate_safe_member("/prices.csv")

    def test_deterministic_archive_exact_member_set(self):
        if shutil.which("zstd") is None:
            self.skipTest("zstd unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shard = root / "shard"
            (shard / "canonical").mkdir(parents=True)
            (shard / "source").mkdir()
            (shard / "SHARD_PAYLOAD_MANIFEST.json").write_text("{}\n")
            (shard / "canonical/prices.csv").write_text("timestamp_utc\n")
            for week in common.WEEKS:
                with (shard / "source" / f"{week:02d}.csv.gz").open("wb") as raw:
                    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as zipped:
                        zipped.write(f"week-{week}\n".encode())
            first = root / "first.tar.zst"
            second = root / "second.tar.zst"
            self.assertEqual(acquire.make_archive(shard, first), acquire.make_archive(shard, second))
            tar_path = root / "view.tar"
            import subprocess
            with tar_path.open("wb") as output:
                subprocess.run(["zstd", "-d", "--stdout", str(first)], check=True, stdout=output)
            with tarfile.open(tar_path, "r") as archive:
                names = archive.getnames()
                self.assertEqual(names[0:2], ["SHARD_PAYLOAD_MANIFEST.json", "canonical/prices.csv"])
                self.assertEqual(names[2:], [f"source/{week:02d}.csv.gz" for week in common.WEEKS])
                self.assertTrue(all(member.mtime == 0 and member.uid == 0 and member.gid == 0 for member in archive.getmembers()))


if __name__ == "__main__":
    unittest.main()
