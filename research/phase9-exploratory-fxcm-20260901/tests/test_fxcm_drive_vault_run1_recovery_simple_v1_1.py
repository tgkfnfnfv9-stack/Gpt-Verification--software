import csv
import gzip
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
RUNNER_DIR = TRACK / "runner"
sys.path.insert(0, str(RUNNER_DIR))
MODULE_PATH = RUNNER_DIR / "fxcm_drive_vault_run1_recovery_simple_v1_1.py"
SPEC = TRACK / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1_1.frozen.json"
spec = importlib.util.spec_from_file_location("simple_recovery_v1_1", MODULE_PATH)
simple = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(simple)


def write_fixture(path: Path, include_row: bool, unexpected_header: bool = False) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        header = ("wrong",) if unexpected_header else simple.base.acquire_base.DIRECT_HEADER
        writer.writerow(header)
        if include_row:
            writer.writerow([
                "01/10/2022 00:00:00", "1", "1", "1", "1",
                "1.1", "1.1", "1.1", "1.1",
            ])


class CorrectiveRecoveryV11Test(unittest.TestCase):
    def setUp(self):
        self.original_download = simple.base.BASE_DOWNLOAD_SOURCE
        self.original_sleep = simple.time.sleep

    def tearDown(self):
        simple.base.BASE_DOWNLOAD_SOURCE = self.original_download
        simple.time.sleep = self.original_sleep

    def test_two_header_only_responses_then_nonempty_success(self):
        attempts = []
        sleeps = []

        def fake_download(_opener, _url, destination):
            attempts.append(len(attempts) + 1)
            write_fixture(destination, include_row=len(attempts) >= 3)
            body = destination.read_bytes()
            return len(body), "a" * 64

        simple.base.BASE_DOWNLOAD_SOURCE = fake_download
        simple.time.sleep = sleeps.append
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.csv.gz"
            size, digest = simple.download_source_with_delayed_integrity_retry(
                object(), "https://example.invalid/source.csv.gz", destination
            )
            self.assertTrue(destination.is_file())
            self.assertGreater(size, 0)
            self.assertEqual(digest, "a" * 64)
        self.assertEqual(attempts, [1, 2, 3])
        self.assertEqual(sleeps, [5, 15])

    def test_header_only_exhaustion_fails_closed_and_deletes_payload(self):
        attempts = []
        sleeps = []

        def fake_download(_opener, _url, destination):
            attempts.append(len(attempts) + 1)
            write_fixture(destination, include_row=False)
            return destination.stat().st_size, "b" * 64

        simple.base.BASE_DOWNLOAD_SOURCE = fake_download
        simple.time.sleep = sleeps.append
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.csv.gz"
            with self.assertRaisesRegex(simple.VaultError, "bounded delayed"):
                simple.download_source_with_delayed_integrity_retry(
                    object(), "https://example.invalid/source.csv.gz", destination
                )
            self.assertFalse(destination.exists())
        self.assertEqual(len(attempts), 6)
        self.assertEqual(sleeps, [5, 15, 30, 60, 120])

    def test_truncated_tail_is_retried_until_complete_stream(self):
        attempts = []
        sleeps = []

        def fake_download(_opener, _url, destination):
            attempts.append(len(attempts) + 1)
            write_fixture(destination, include_row=True)
            if len(attempts) < 3:
                body = destination.read_bytes()
                destination.write_bytes(body[:-8])
            return destination.stat().st_size, "d" * 64

        simple.base.BASE_DOWNLOAD_SOURCE = fake_download
        simple.time.sleep = sleeps.append
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.csv.gz"
            size, digest = simple.download_source_with_delayed_integrity_retry(
                object(), "https://example.invalid/source.csv.gz", destination
            )
            self.assertTrue(destination.is_file())
            self.assertGreater(size, 0)
            self.assertEqual(digest, "d" * 64)
        self.assertEqual(attempts, [1, 2, 3])
        self.assertEqual(sleeps, [5, 15])

    def test_unknown_header_is_rejected_without_retry(self):
        attempts = []
        sleeps = []

        def fake_download(_opener, _url, destination):
            attempts.append(1)
            write_fixture(destination, include_row=True, unexpected_header=True)
            return destination.stat().st_size, "c" * 64

        simple.base.BASE_DOWNLOAD_SOURCE = fake_download
        simple.time.sleep = sleeps.append
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.csv.gz"
            with self.assertRaisesRegex(simple.VaultError, "non-retryable"):
                simple.download_source_with_delayed_integrity_retry(
                    object(), "https://example.invalid/source.csv.gz", destination
                )
            self.assertFalse(destination.exists())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(sleeps, [])

    def test_contract_and_executed_v1_anchors(self):
        contract = simple.load_simple_contract_v1_1(SPEC)
        self.assertEqual(contract["workflow"]["required_run_number"], 4)
        self.assertEqual(
            contract["source_policy"]["content_integrity_delays_seconds"],
            [0, 5, 15, 30, 60, 120],
        )
        self.assertTrue(contract["source_policy"]["header_only_never_accepted_as_zero_rows"])
        self.assertEqual(contract["executed_v1_anchors"]["drive_upload_count"], 0)
        incident = json.loads(
            (TRACK.parents[1] / contract["incident_audit"]["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(incident["effects"]["drive_upload_count"], 0)
        self.assertFalse(incident["independent_refetch"]["raw_or_canonical_price_retained"])

    def test_drive_upload_properties_are_rewritten_to_v1_1(self):
        observed = {}
        original = simple.BASE_GOOGLE_DRIVE_PRIVATE.upload_file_new

        def fake_upload(_self, parent_id, path, remote_name, mime_type, app_properties):
            observed.update(app_properties)
            return {"id": "fake"}

        simple.BASE_GOOGLE_DRIVE_PRIVATE.upload_file_new = fake_upload
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "object"
                path.write_bytes(b"a")
                instance = object.__new__(simple.VersionedGoogleDrivePrivate)
                result = instance.upload_file_new(
                    "parent",
                    path,
                    "object",
                    "application/octet-stream",
                    {"operational_version": "v2.1+simple-v1-recovery"},
                )
        finally:
            simple.BASE_GOOGLE_DRIVE_PRIVATE.upload_file_new = original
        self.assertEqual(result, {"id": "fake"})
        self.assertEqual(observed["operational_version"], "v2.1+simple-v1.1-recovery")
        self.assertEqual(observed["recovery_version"], "simple-v1.1")


if __name__ == "__main__":
    unittest.main()
