import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
TRACK = Path(__file__).resolve().parents[1]
V1 = ROOT / ".github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v1.yml"
V2_OLD = ROOT / ".github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2.yml"
V2 = ROOT / ".github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v2-1.yml"
VERIFY = TRACK / "runner/verify_fxcm_drive_vault_v2.py"
ACQUISITION_V2 = TRACK / "spec/fxcm_drive_vault_acquisition_v2.frozen.json"
AMENDMENT_V2_1 = TRACK / "spec/fxcm_drive_vault_operational_hardening_v2_1.frozen.json"
MASK_SHA256 = "0dcda17adbe53c9572492425405c7feb4b972e0b0312dcbf6d04c0aa4e20f014"
sys.path.insert(0, str(TRACK / "runner"))
import fxcm_drive_vault_common as common  # noqa: E402


class VaultV2WorkflowTests(unittest.TestCase):
    def test_old_workflows_are_blocked_and_v2_1_is_manual_only(self):
        self.assertRegex(V1.read_text(), r"(?m)^\s+false &&$")
        self.assertRegex(V2_OLD.read_text(), r"(?m)^\s+false &&$")
        text = V2.read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotRegex(text, r"(?m)^\s*(push|schedule|workflow_run|repository_dispatch):")
        self.assertIn("github.run_number == 1", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertIn("inputs.expected_head_sha == github.sha", text)
        self.assertIn("environment: phase9-fxcm-vault-acquisition-v2", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("id-token: write", text)
        self.assertIn("prepare-vault:", text)
        self.assertIn("needs: [preflight, prepare-vault]", text)
        self.assertIn("publish canonical folder once", text)
        acquisition_sha256 = common.sha256_file(ACQUISITION_V2)
        self.assertRegex(
            text,
            rf"sha256sum .*fxcm_drive_vault_acquisition_v2\.frozen\.json.*= '{acquisition_sha256}'",
        )
        for path in (
            AMENDMENT_V2_1,
            TRACK / "runner/fxcm_drive_vault_common.py",
            TRACK / "runner/fxcm_drive_vault_acquire_year.py",
            TRACK / "runner/fxcm_drive_vault_v2_common.py",
            TRACK / "runner/fxcm_google_drive_private.py",
            TRACK / "runner/fxcm_drive_vault_prepare_v2_1.py",
            TRACK / "runner/fxcm_drive_vault_acquire_year_v2.py",
            TRACK / "runner/fxcm_drive_vault_finalize.py",
            TRACK / "runner/fxcm_drive_vault_finalize_v2.py",
            TRACK / "runner/verify_fxcm_drive_vault_v2.py",
        ):
            self.assertRegex(
                text,
                rf"sha256sum .*{re.escape(path.name)}.*= '{common.sha256_file(path)}'",
            )

    def test_v2_matrix_scope_secrets_and_price_free_artifact_are_exact(self):
        text = V2.read_text()
        years = re.search(r"year: \[([^]]+)\]", text).group(1)
        self.assertEqual([int(value.strip()) for value in years.split(",")], list(range(2012, 2026)))
        self.assertIn("max-parallel: 4", text)
        for name in common.SECRET_NAMES:
            self.assertIn(f"{name}: ${{{{ secrets.{name} }}}}", text)
        self.assertIn("Upload exact price-free V2.1 audit only", text)
        self.assertNotRegex(text, r"(?m)^\s*path:\s+.*(?:csv|gz|tar|zst)")
        self.assertNotIn("phase9-exploratory-fxcm-blind-mtf-batch6-count-only", text)

    def test_price_free_v2_verifier_accepts_only_exact_audit(self):
        audit = {
            "schema_version": "phase9-exploratory-fxcm-drive-vault-price-free-audit-v2.1.0",
            "status": "PRIVATE_VAULT_TRANSACTIONALLY_COMMITTED_PRICE_FREE_PUBLIC_AUDIT",
            "vault_version": "v2", "operational_version": "v2.1",
            "run_id": "123", "run_attempt": 1,
            "head_sha": "a" * 40, "year_count": 14, "symbol_count": 25,
            "direct_periodicity_count": 2, "shard_count": 700,
            "base_source_object_count": 36400, "source_object_count": 36000,
            "known_missing_source_object_count": 400,
            "availability_mask_sha256": MASK_SHA256,
            "operational_amendment_sha256": common.sha256_file(AMENDMENT_V2_1),
            "vault_manifest_sha256": "b" * 64, "vault_seal_sha256": "c" * 64,
            "all_uploads_redownload_sha256_verified": True,
            "transactional_publication_committed": True,
            "batch6_compatibility_passed": False,
            "full_provider_schedule_qc_claimed": False,
            "formal_phase9_authorization_effect": False,
            "count_only_authorized": False, "batch6_authorized": False,
            "research_outcomes_calculated": False, "outcome_fields": [],
            "public_price_files": 0, "public_drive_identifiers": 0,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit_path = root / "VAULT_RUN_PRICE_FREE_AUDIT.json"
            audit_path.write_bytes(common.canonical_json_bytes(audit))
            (root / "artifact_manifest_sha256.txt").write_text(
                f"{common.sha256_file(audit_path)}  {audit_path.name}\n", encoding="ascii"
            )
            command = [
                sys.executable, str(VERIFY), "--report-dir", str(root),
                "--expected-head-sha", "a" * 40, "--expected-run-id", "123",
                "--expected-mask-sha256", MASK_SHA256,
                "--expected-amendment-sha256", common.sha256_file(AMENDMENT_V2_1),
            ]
            subprocess.run(command, check=True)
            for field, bad_value in (
                ("public_price_files", 1),
                ("vault_seal_sha256", "not-a-sha"),
                ("batch6_compatibility_passed", 0),
                ("transactional_publication_committed", 1),
            ):
                with self.subTest(field=field):
                    changed = dict(audit)
                    changed[field] = bad_value
                    audit_path.write_bytes(common.canonical_json_bytes(changed))
                    (root / "artifact_manifest_sha256.txt").write_text(
                        f"{common.sha256_file(audit_path)}  {audit_path.name}\n", encoding="ascii"
                    )
                    self.assertNotEqual(
                        subprocess.run(command, stderr=subprocess.DEVNULL).returncode, 0
                    )


if __name__ == "__main__":
    unittest.main()
