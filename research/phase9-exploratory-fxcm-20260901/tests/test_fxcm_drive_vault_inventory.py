import sys
import unittest
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK / "runner"))
import fxcm_drive_vault_inventory as inventory  # noqa: E402


class FakeHeaders(dict):
    pass


class FakeResponse:
    status = 200
    headers = FakeHeaders({"Content-Length": "123"})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *_args, **_kwargs):
        raise AssertionError("HEAD-only inventory must never read a response body")


class FakeOpener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse()


class VaultInventoryTests(unittest.TestCase):
    def test_head_status_reads_no_response_body(self):
        opener = FakeOpener()
        status, length, error = inventory.head_status(opener, "https://candledata.fxcorporate.com/m1/EURUSD/2017/1.csv.gz")
        self.assertEqual((status, length, error), (200, 123, None))
        self.assertEqual(opener.requests[0][0].method, "HEAD")


if __name__ == "__main__":
    unittest.main()
