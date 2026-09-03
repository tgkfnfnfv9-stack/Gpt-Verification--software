import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
RUNNER_DIR = TRACK / "runner"
SPEC = TRACK / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1.frozen.json"
WORKFLOW = TRACK / "audit" / "fxcm_drive_vault_run1_recovery_simple_v1.executed.yml"
sys.path.insert(0, str(RUNNER_DIR))

module_spec = importlib.util.spec_from_file_location(
    "simple_recovery", RUNNER_DIR / "fxcm_drive_vault_run1_recovery_simple_v1.py"
)
simple_recovery = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(simple_recovery)

verify_spec = importlib.util.spec_from_file_location(
    "simple_verifier", RUNNER_DIR / "verify_fxcm_drive_vault_run1_recovery_simple_v1.py"
)
simple_verifier = importlib.util.module_from_spec(verify_spec)
assert verify_spec.loader is not None
verify_spec.loader.exec_module(simple_verifier)


HEADER = [
    "timestamp_utc", "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close", "volume_status", "volume",
]


def write_rows(path: Path, starts: list[datetime], volume: str = "1") -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        for timestamp in starts:
            writer.writerow([
                timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "1.0000", "1.0000", "1.0000", "1.0000",
                "1.0002", "1.0002", "1.0002", "1.0002",
                "PRESENT", volume,
            ])


class SimpleRecoveryContractTest(unittest.TestCase):
    def test_offline_verifier_passes(self):
        result = simple_verifier.verify(
            SPEC,
            RUNNER_DIR / "fxcm_drive_vault_run1_recovery_simple_v1.py",
            WORKFLOW,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["price_access"], 0)

    def test_exact_scope_and_counts(self):
        contract = json.loads(SPEC.read_text(encoding="utf-8"))
        self.assertEqual(contract["interval"]["years"], [2022, 2023, 2024, 2025])
        self.assertEqual(len(contract["symbols"]), 25)
        self.assertEqual(contract["counts"]["archive_shards"], 200)
        self.assertEqual(contract["counts"]["objects_uploaded_and_redownloaded"], 204)

    def test_execution_authority_remains_false(self):
        authorization = json.loads(SPEC.read_text(encoding="utf-8"))["current_authorization"]
        self.assertTrue(authorization["implementation"])
        for name in (
            "workflow_dispatch", "price_access", "oauth_token_exchange",
            "drive_access", "drive_write", "transaction_finalization", "research_use",
        ):
            self.assertFalse(authorization[name])

    def test_complete_synthetic_four_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = datetime(2022, 1, 3, tzinfo=timezone.utc)
            m1 = [start + timedelta(minutes=index) for index in range(240)]
            h1 = [start + timedelta(hours=index) for index in range(4)]
            write_rows(root / "m1.csv", m1)
            write_rows(root / "h1.csv", h1, volume="60")
            result = simple_recovery.derive_qc_simple_v1(root / "m1.csv", root / "h1.csv", 2022)
            self.assertEqual(result["M5"]["complete_bucket_count"], 48)
            self.assertEqual(result["M15"]["complete_bucket_count"], 16)
            self.assertEqual(result["M30"]["complete_bucket_count"], 8)
            self.assertEqual(result["H4"]["complete_bucket_count"], 1)
            self.assertGreater(result["H4"]["dropped_bucket_count"], 0)
            self.assertEqual(result["forward_fill_count"], 0)
            self.assertEqual(result["interpolation_count"], 0)

    def test_missing_minute_drops_and_hashes_bucket(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = datetime(2022, 1, 3, tzinfo=timezone.utc)
            m1 = [start + timedelta(minutes=index) for index in range(60) if index != 7]
            write_rows(root / "m1.csv", m1)
            write_rows(root / "h1.csv", [start], volume="60")
            result = simple_recovery.derive_qc_simple_v1(root / "m1.csv", root / "h1.csv", 2022)
            self.assertGreater(result["M15"]["dropped_bucket_count"], 0)
            self.assertEqual(len(result["M15"]["dropped_bucket_timestamp_sha256"]), 64)
            self.assertGreater(result["H1_cross_check"]["derived_timestamp_missing_for_reference_count"], 0)

    def test_whole_missing_hour_drops_h4(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = datetime(2022, 1, 3, tzinfo=timezone.utc)
            hours = (0, 2, 3)
            m1 = [start + timedelta(hours=hour, minutes=minute) for hour in hours for minute in range(60)]
            h1 = [start + timedelta(hours=hour) for hour in hours]
            write_rows(root / "m1.csv", m1)
            write_rows(root / "h1.csv", h1, volume="60")
            result = simple_recovery.derive_qc_simple_v1(root / "m1.csv", root / "h1.csv", 2022)
            self.assertEqual(result["H4"]["complete_bucket_count"], 0)
            self.assertGreater(result["H4"]["dropped_bucket_count"], 0)
            self.assertGreater(result["H4"]["missing_component_timestamp_count"], 0)


if __name__ == "__main__":
    unittest.main()
