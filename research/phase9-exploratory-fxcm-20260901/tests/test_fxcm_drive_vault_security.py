import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TRACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK / "runner"))
import fxcm_drive_vault_common as common  # noqa: E402
import fxcm_google_drive_private as drive_module  # noqa: E402


class VaultSecurityTests(unittest.TestCase):
    def test_oauth_missing_fails_before_client_network(self):
        with mock.patch.dict(os.environ, {name: "" for name in common.SECRET_NAMES}, clear=False):
            with self.assertRaises(common.VaultError):
                drive_module.GoogleDrivePrivate()

    def test_drive_client_rejects_non_google_api_host_before_token(self):
        client = object.__new__(drive_module.GoogleDrivePrivate)
        client._access_token = None
        client._opener = None
        with self.assertRaises(common.VaultError):
            client._json_request("GET", "https://evil.example/drive/v3/files")

    def test_public_report_rejects_price_drive_id_and_outcome(self):
        forbidden = (
            {"bid_open": "1.0"},
            {"drive_file_id": "private"},
            {"return": 0.1},
        )
        for body in forbidden:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                audit = root / "VAULT_RUN_PRICE_FREE_AUDIT.json"
                audit.write_text(json.dumps(body) + "\n")
                (root / "artifact_manifest_sha256.txt").write_text(f"{common.sha256_file(audit)}  {audit.name}\n")
                with self.assertRaises(common.VaultError):
                    common.validate_public_report_tree(root)

    def test_public_report_rejects_extra_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit = root / "VAULT_RUN_PRICE_FREE_AUDIT.json"
            audit.write_text("{}\n")
            (root / "artifact_manifest_sha256.txt").write_text(f"{common.sha256_file(audit)}  {audit.name}\n")
            (root / "extra.csv").write_text("price\n")
            with self.assertRaises(common.VaultError):
                common.validate_public_report_tree(root)


if __name__ == "__main__":
    unittest.main()
