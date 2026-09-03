import csv
import gzip
import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
RUNNER_DIR = TRACK / "runner"
sys.path.insert(0, str(RUNNER_DIR))
MODULE_PATH = RUNNER_DIR / "fxcm_drive_vault_run1_recovery_simple_v1_2.py"
SPEC = TRACK / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1_2.frozen.json"
spec = importlib.util.spec_from_file_location("simple_recovery_v1_2", MODULE_PATH)
simple = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(simple)


def gzip_fixture(include_row: bool) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed:
        text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(simple.base.acquire_base.DIRECT_HEADER)
        if include_row:
            writer.writerow([
                "01/10/2022 00:00:00", "1", "1", "1", "1",
                "1.1", "1.1", "1.1", "1.1",
            ])
        text.flush()
        text.detach()
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, body: bytes, url: str):
        self.body = io.BytesIO(body)
        self.status = 200
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.body.read(size)

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.urls = []

    def open(self, request, timeout):
        self.urls.append(request.full_url)
        return FakeResponse(self.bodies.pop(0), request.full_url)


class CacheIsolatedRecoveryV12Test(unittest.TestCase):
    def setUp(self):
        self.original_sleep = simple.time.sleep

    def tearDown(self):
        simple.time.sleep = self.original_sleep

    def test_transport_url_preserves_host_and_path_with_bounded_query(self):
        canonical = "https://candledata.fxcorporate.com/m1/AUDCAD/2022/1.csv.gz"
        value = simple.transport_url(canonical, 2, 3)
        parsed = urllib.parse.urlsplit(value)
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.hostname, "candledata.fxcorporate.com")
        self.assertEqual(parsed.path, "/m1/AUDCAD/2022/1.csv.gz")
        self.assertEqual(query, {
            "phase9_v": ["simple-v1.2"],
            "integrity_attempt": ["2"],
            "transport_attempt": ["3"],
        })
        self.assertEqual(urllib.parse.urlsplit(canonical).query, "")

    def test_successful_query_transport_returns_exact_payload_sha(self):
        canonical = "https://candledata.fxcorporate.com/m1/AUDCAD/2022/1.csv.gz"
        body = gzip_fixture(include_row=True)
        opener = FakeOpener([body])
        simple.time.sleep = lambda _seconds: None
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.csv.gz"
            size, digest = simple.download_source_with_cache_isolation(
                opener, canonical, destination
            )
            self.assertEqual(destination.read_bytes(), body)
        self.assertEqual(size, len(body))
        self.assertEqual(digest, hashlib.sha256(body).hexdigest())
        self.assertEqual(len(opener.urls), 1)
        self.assertNotEqual(opener.urls[0], canonical)

    def test_header_only_query_retries_with_new_transport_identity(self):
        canonical = "https://candledata.fxcorporate.com/m1/AUDCAD/2022/1.csv.gz"
        opener = FakeOpener([
            gzip_fixture(include_row=False),
            gzip_fixture(include_row=True),
        ])
        sleeps = []
        simple.time.sleep = sleeps.append
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source.csv.gz"
            simple.download_source_with_cache_isolation(opener, canonical, destination)
            self.assertTrue(destination.is_file())
        self.assertEqual(sleeps, [5])
        self.assertEqual(len(opener.urls), 2)
        self.assertNotEqual(opener.urls[0], opener.urls[1])
        self.assertIn("integrity_attempt=1", opener.urls[0])
        self.assertIn("integrity_attempt=2", opener.urls[1])

    def test_contract_anchors_failed_v1_1_and_run5(self):
        contract = simple.load_simple_contract_v1_2(SPEC)
        self.assertEqual(contract["workflow"]["required_run_number"], 5)
        self.assertEqual(contract["executed_v1_1_anchors"]["run_id"], "33799360214")
        self.assertEqual(contract["executed_v1_1_anchors"]["drive_upload_count"], 0)
        self.assertTrue(
            contract["source_policy"]["transport_cache_bust"][
                "canonical_identity_stored_without_query"
            ]
        )

    def test_v1_2_drive_metadata_globals_are_active(self):
        self.assertEqual(simple.v11.RECOVERY_VERSION, "simple-v1.2")
        self.assertEqual(
            simple.v11.OPERATIONAL_VERSION,
            "v2.1+simple-v1.2-recovery",
        )
        self.assertIs(
            simple.base.acquire_base.download_source,
            simple.download_source_with_cache_isolation,
        )


if __name__ == "__main__":
    unittest.main()
