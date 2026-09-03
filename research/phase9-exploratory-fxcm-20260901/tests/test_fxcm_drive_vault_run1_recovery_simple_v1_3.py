import importlib.util
import os
import sys
import unittest
import urllib.parse
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
RUNNER_DIR = TRACK / "runner"
sys.path.insert(0, str(RUNNER_DIR))
MODULE_PATH = RUNNER_DIR / "fxcm_drive_vault_run1_recovery_simple_v1_3.py"
SPEC = TRACK / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1_3.frozen.json"
spec = importlib.util.spec_from_file_location("simple_recovery_v1_3", MODULE_PATH)
simple = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(simple)


class MacOSRecoveryV13Test(unittest.TestCase):
    def test_contract_freezes_scope_network_and_zero_write_v1_2_anchor(self):
        relative_spec = Path(os.path.relpath(SPEC, Path.cwd()))
        contract = simple.load_simple_contract_v1_3(relative_spec)
        self.assertEqual(contract["interval"], {
            "start_inclusive": "2022-01-01T00:00:00Z",
            "end_exclusive": "2026-01-01T00:00:00Z",
            "years": [2022, 2023, 2024, 2025],
        })
        self.assertEqual(len(contract["symbols"]), 25)
        self.assertEqual(contract["counts"], simple.EXPECTED_COUNTS)
        self.assertEqual(contract["per_year"], simple.EXPECTED_PER_YEAR)
        self.assertEqual(contract["offer_sides"], ["BID", "ASK"])
        self.assertEqual(
            contract["derived_periodicities"],
            ["M5", "M15", "M30", "H4", "D1", "W1"],
        )
        self.assertFalse(contract["source_policy"]["request_known_missing"])
        self.assertEqual(contract["workflow"]["recover_runner_label"], "macos-15")
        self.assertEqual(contract["executed_v1_2_anchors"]["run_id"], "33805536160")
        self.assertEqual(contract["executed_v1_2_anchors"]["drive_write_count"], 0)
        self.assertEqual(contract["executed_v1_2_anchors"]["cleanup"], "PASS")

    def test_v1_3_inherits_exact_v1_2_acquisition_and_qc_path(self):
        self.assertIs(
            simple.base.acquire_base.download_source,
            simple.v12.download_source_with_cache_isolation,
        )
        self.assertIs(simple.base.load_simple_contract, simple.load_simple_contract_v1_3)
        self.assertEqual(simple.base.RECOVERY_VERSION, "simple-v1.3")
        self.assertEqual(simple.v12.v11.RECOVERY_VERSION, "simple-v1.3")
        self.assertEqual(
            simple.v12.v11.OPERATIONAL_VERSION,
            "v2.1+simple-v1.3-recovery",
        )
        self.assertIs(simple.v12.download_transport, simple.download_transport)

    def test_transport_query_uses_new_v1_3_cache_identity(self):
        canonical = "https://candledata.fxcorporate.com/m1/AUDCAD/2022/1.csv.gz"
        value = simple.transport_url(canonical, 1, 1)
        parsed = urllib.parse.urlsplit(value)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.hostname, "candledata.fxcorporate.com")
        self.assertEqual(parsed.path, "/m1/AUDCAD/2022/1.csv.gz")
        self.assertEqual(urllib.parse.parse_qs(parsed.query), {
            "phase9_v": ["simple-v1.3"],
            "integrity_attempt": ["1"],
            "transport_attempt": ["1"],
        })
        self.assertEqual(urllib.parse.urlsplit(canonical).query, "")

    def test_published_contract_remains_price_nonreference(self):
        contract = simple.load_simple_contract_v1_3(SPEC)
        for name in (
            "workflow_dispatch",
            "price_access",
            "oauth_token_exchange",
            "drive_access",
            "drive_write",
            "transaction_finalization",
            "research_use",
        ):
            self.assertIs(contract["current_authorization"][name], False)


if __name__ == "__main__":
    unittest.main()
