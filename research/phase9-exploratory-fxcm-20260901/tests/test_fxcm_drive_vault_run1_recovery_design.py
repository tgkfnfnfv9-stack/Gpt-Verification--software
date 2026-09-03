import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TRACK = Path(__file__).resolve().parents[1]
RUNNER_DIR = TRACK / "runner"
sys.path.insert(0, str(RUNNER_DIR))

import verify_fxcm_drive_vault_run1_recovery_design as verifier  # noqa: E402


CONTRACT = TRACK / "spec/fxcm_drive_vault_run1_recovery_v2_2.frozen.json"
VERIFY = RUNNER_DIR / "verify_fxcm_drive_vault_run1_recovery_design.py"


class Run1RecoveryDesignTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def _verify_changed_contract(self, change):
        changed = copy.deepcopy(self.contract)
        change(changed)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "changed.json"
            path.write_text(json.dumps(changed), encoding="utf-8")
            verifier.verify(path, ROOT)

    def test_exact_frozen_design_passes_offline_verification(self):
        result = verifier.verify(CONTRACT, ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["recovery_years"], [2022, 2023, 2024, 2025])
        self.assertEqual(result["planned_recovery_archives"], 200)
        self.assertEqual(result["planned_recovery_manifests"], 4)
        for field in (
            "network_access_performed",
            "oauth_token_exchanges_performed",
            "fxcm_requests_performed",
            "drive_accesses_performed",
            "drive_mutations_performed",
            "cleanup_operations_performed",
        ):
            self.assertEqual(result[field], 0)

    def test_rejects_scope_or_count_expansion(self):
        for change in (
            lambda value: value["scope"]["recovery_years"].insert(0, 2021),
            lambda value: value["scope"].__setitem__("recovery_archive_shards", 250),
            lambda value: value["scope"].__setitem__("frozen_present_source_identities", 10400),
            lambda value: value["preaudit_observed_state"]["preserved_complete_years"].__setitem__("archive_bytes", 1),
        ):
            with self.subTest(change=change):
                with self.assertRaises(verifier.VerificationError):
                    self._verify_changed_contract(change)

    def test_rejects_any_current_authorization(self):
        for field in self.contract["current_authorization"]:
            with self.subTest(field=field):
                with self.assertRaises(verifier.VerificationError):
                    self._verify_changed_contract(
                        lambda value, field=field: value["current_authorization"].__setitem__(field, True)
                    )

    def test_cleanup_is_forbidden_in_every_gate(self):
        gates = self.contract["versioned_recovery_design"]
        for field in (
            "gate_r1_recovery_acquisition",
            "gate_r2_full_transaction_read_only_audit",
            "gate_r3_canonical_publication",
        ):
            self.assertEqual(gates[field]["cleanup"], "FORBIDDEN")
        self.assertFalse(self.contract["current_authorization"]["cleanup"])
        self.assertIn("CLEANUP", self.contract["current_gate_outputs"]["forbidden"])

    def test_design_gate_has_no_executable_recovery_surface(self):
        for relative_path in verifier.FORBIDDEN_EXECUTABLE_PATHS:
            self.assertFalse((ROOT / relative_path).exists(), relative_path)

        source = VERIFY.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?m)^\s*(?:from|import)\s+(?:urllib|requests|httpx|googleapiclient)\b", source))
        self.assertNotIn("GOOGLE_DRIVE_CLIENT_ID", source)
        self.assertNotIn("GOOGLE_DRIVE_CLIENT_SECRET", source)
        self.assertNotIn("GOOGLE_DRIVE_REFRESH_TOKEN", source)
        self.assertNotIn("https://", source)


if __name__ == "__main__":
    unittest.main()
