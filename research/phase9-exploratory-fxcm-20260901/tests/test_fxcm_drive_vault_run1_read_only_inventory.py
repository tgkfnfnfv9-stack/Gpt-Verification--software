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

import fxcm_drive_vault_common as common  # noqa: E402
import fxcm_drive_vault_run1_read_only_inventory as inventory  # noqa: E402
import fxcm_google_drive_read_only as read_only_client  # noqa: E402
import verify_fxcm_drive_vault_run1_read_only_inventory as verifier  # noqa: E402


CONTRACT = TRACK / "spec/fxcm_drive_vault_run1_read_only_inventory_v2_1.frozen.json"
AMENDMENT = TRACK / "spec/fxcm_drive_vault_operational_hardening_v2_1.frozen.json"
CLIENT = RUNNER_DIR / "fxcm_google_drive_read_only.py"
RUNNER = RUNNER_DIR / "fxcm_drive_vault_run1_read_only_inventory.py"
VERIFY = RUNNER_DIR / "verify_fxcm_drive_vault_run1_read_only_inventory.py"
WORKFLOW = ROOT / ".github/workflows/phase9-exploratory-fxcm-drive-vault-run1-read-only-inventory.yml"


def owned_folder(object_id, name, parent, properties):
    return {
        "id": object_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent],
        "appProperties": properties,
        "ownedByMe": True,
        "trashed": False,
        "driveId": None,
        "shortcutDetails": None,
    }


class FakeDrive:
    def __init__(self, children):
        self.children = children

    def verify_private_root(self, root_id, expected_name):
        if root_id != "1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v" or expected_name != "Phase9 FXCM Data Vault":
            raise AssertionError
        return {}

    def list_children(self, parent_id):
        return list(self.children.get(parent_id, []))


class Run1ReadOnlyInventoryTests(unittest.TestCase):
    def setUp(self):
        self.contract = inventory.load_inventory_contract(CONTRACT, AMENDMENT)

    def _fake_drive(self):
        root_id = self.contract["drive_scope"]["root_folder_id"]
        transaction_id = "private-transaction-id"
        transaction = owned_folder(
            transaction_id,
            "v2-txn-run-33705800232",
            root_id,
            {
                "vault_version": "v2",
                "operational_version": "v2.1",
                "run_id": "33705800232",
                "head_sha": inventory.SOURCE_HEAD_SHA,
                "state": "ACQUIRING",
                "amendment_sha256": inventory.AMENDMENT_SHA256,
            },
        )
        stage_id = "private-stage-id"
        stage = owned_folder(
            stage_id,
            "v2-staging-run-33705800232-year-2012",
            transaction_id,
            {
                "vault_version": "v2",
                "operational_version": "v2.1",
                "run_id": "33705800232",
                "head_sha": inventory.SOURCE_HEAD_SHA,
                "year": "2012",
                "state": "UNSEALED",
            },
        )
        stage_children = []
        for index, name in enumerate(inventory._expected_archive_names(2012)):
            symbol, periodicity = name[len("fxcm-v2-") : -len(".tar.zst")].rsplit("-", 2)[0::2]
            stage_children.append({
                "id": f"private-archive-{index}",
                "name": name,
                "mimeType": "application/zstd",
                "size": str(1000 + index),
                "appProperties": {
                    "vault_version": "v2",
                    "operational_version": "v2.1",
                    "run_id": "33705800232",
                    "head_sha": inventory.SOURCE_HEAD_SHA,
                    "year": "2012",
                    "symbol": symbol,
                    "periodicity": periodicity,
                    "sha256": f"{index + 1:064x}",
                    "partition": "DEVELOPMENT",
                    "state": "UNSEALED",
                },
            })
        stage_children.append({
            "id": "private-manifest-id",
            "name": "YEAR_MANIFEST.json",
            "mimeType": "application/json",
            "size": "12345",
            "appProperties": {
                "vault_version": "v2",
                "operational_version": "v2.1",
                "run_id": "33705800232",
                "head_sha": inventory.SOURCE_HEAD_SHA,
                "year": "2012",
                "sha256": "f" * 64,
                "state": "YEAR_COMPLETE_UNSEALED",
            },
        })
        return FakeDrive({root_id: [transaction], transaction_id: [stage], stage_id: stage_children})

    def test_inventory_strips_private_ids_and_classifies_partial_transaction(self):
        report = inventory.build_inventory(self.contract, "999", 1, "a" * 40, self._fake_drive())
        self.assertEqual(report["complete_years"], [2012])
        self.assertEqual(report["partial_or_unavailable_years"], list(range(2013, 2026)))
        self.assertEqual(report["drive_mutation_count"], 0)
        self.assertEqual(report["drive_file_content_bytes_read"], 0)
        self.assertNotIn(b"private-", common.canonical_json_bytes(report))
        self.assertEqual(report["year_stages"][0]["valid_archive_metadata_count"], 50)

    def test_verifier_accepts_exact_sanitized_report_and_rejects_mutation_claim(self):
        report = inventory.build_inventory(self.contract, "999", 1, "a" * 40, self._fake_drive())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_path = root / inventory.REPORT_FILES[0]
            report_path.write_bytes(common.canonical_json_bytes(report))
            manifest_path = root / inventory.REPORT_FILES[1]
            manifest_path.write_text(f"{common.sha256_file(report_path)}  {report_path.name}\n", encoding="ascii")
            verifier.verify(root, "a" * 40, "999")
            report["drive_mutation_count"] = 1
            report_path.write_bytes(common.canonical_json_bytes(report))
            manifest_path.write_text(f"{common.sha256_file(report_path)}  {report_path.name}\n", encoding="ascii")
            with self.assertRaises(common.VaultError):
                verifier.verify(root, "a" * 40, "999")

    def test_read_only_client_has_no_drive_mutation_or_media_surface(self):
        text = CLIENT.read_text(encoding="utf-8")
        self.assertIn('method="GET"', text)
        self.assertEqual(text.count('method="POST"'), 1)
        self.assertNotIn('method="PATCH"', text)
        self.assertNotIn('method="DELETE"', text)
        self.assertNotIn("upload/drive", text)
        self.assertNotIn("alt=media", text)
        for surface in ("create_folder", "upload_file", "move_file", "publish_folder", "download_verify"):
            self.assertNotIn(surface, text)

    def test_read_only_client_rejects_media_query_before_oauth(self):
        client = object.__new__(read_only_client.GoogleDriveReadOnly)
        client._access_token = None
        client._opener = None
        with self.assertRaises(common.VaultError):
            client._drive_json_get(
                "https://www.googleapis.com/drive/v3/files/"
                "1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v?alt=media"
            )

    def test_workflow_is_manual_single_use_and_pins_exact_closure(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotRegex(text, r"(?m)^\s*(push|schedule|workflow_run|repository_dispatch):")
        self.assertIn("github.run_number == 1", text)
        self.assertIn("github.run_attempt == 1", text)
        self.assertIn("inputs.expected_head_sha == github.sha", text)
        self.assertIn("environment: phase9-fxcm-vault-acquisition-v2", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("id-token: write", text)
        self.assertNotIn("fxcorporate.com", text)
        self.assertNotIn("acquire_year", text)
        self.assertNotIn("finalize", text)
        for path in (CONTRACT, AMENDMENT, CLIENT, RUNNER, VERIFY):
            self.assertRegex(
                text,
                rf"sha256sum .*{re.escape(path.name)}.*= '{common.sha256_file(path)}'",
            )

    def test_contract_explicitly_blocks_execution_expansion(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertFalse(contract["authorization"]["workflow_dispatch_authorized"])
        self.assertFalse(contract["authorization"]["cleanup_authorized"])
        self.assertFalse(contract["authorization"]["recovery_acquisition_authorized"])
        self.assertEqual(contract["allowed_operations"]["drive_api_methods"], ["GET"])


if __name__ == "__main__":
    unittest.main()
