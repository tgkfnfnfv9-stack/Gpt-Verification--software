import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
RUNNER_DIR = TRACK / "runner"
SPEC = TRACK / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1.frozen.json"
WORKFLOW = TRACK / "audit" / "fxcm_drive_vault_run1_recovery_simple_v1.executed.yml"
sys.path.insert(0, str(RUNNER_DIR))

module_spec = importlib.util.spec_from_file_location(
    "simple_recovery_security", RUNNER_DIR / "fxcm_drive_vault_run1_recovery_simple_v1.py"
)
simple_recovery = importlib.util.module_from_spec(module_spec)
assert module_spec.loader is not None
module_spec.loader.exec_module(simple_recovery)


class FakeDrive:
    YEAR_BYTES = {
        2012: 248526856, 2013: 250697861, 2014: 242164532, 2015: 271388223,
        2016: 274416912, 2017: 259799164, 2018: 257462808, 2019: 244249900,
        2020: 256708652, 2021: 243448496,
    }
    def __init__(self):
        self.transaction = {
            "id": "transaction-object",
            "name": "v2-txn-run-33705800232",
            "mimeType": "application/vnd.google-apps.folder",
            "appProperties": {
                "vault_version": "v2",
                "operational_version": "v2.1",
                "run_id": "33705800232",
                "head_sha": "be864557a8e16d253e6aecf1519f85ad6162c1a3",
                "state": "ACQUIRING",
                "amendment_sha256": "03b8ecaa6a75a1df797f8c4de5fbdf5b59ce0a5655957a5f04c1ab595301434b",
            },
        }
        self.stages = [
            {
                "id": f"stage-{year}",
                "name": f"v2-staging-run-33705800232-year-{year}",
                "mimeType": "application/vnd.google-apps.folder",
                "appProperties": {
                    "vault_version": "v2", "operational_version": "v2.1",
                    "run_id": "33705800232",
                    "head_sha": "be864557a8e16d253e6aecf1519f85ad6162c1a3",
                    "year": str(year), "state": "UNSEALED",
                },
            }
            for year in range(2012, 2026)
        ]

    def verify_private_root(self, name, object_id):
        if name != "Phase9 FXCM Data Vault" or object_id != "1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v":
            raise AssertionError("wrong root")

    def list_children(self, object_id):
        if object_id == "1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v":
            return [self.transaction]
        if object_id == "transaction-object":
            return self.stages
        if object_id.startswith("stage-"):
            year = int(object_id.split("-")[1])
            if year > 2021:
                return []
            partition = "DEVELOPMENT" if year <= 2019 else "STRICT_OOS"
            total = self.YEAR_BYTES[year]
            base, remainder = divmod(total, 50)
            rows = []
            index = 0
            for symbol in simple_recovery.SYMBOLS_V2:
                for periodicity in simple_recovery.DIRECT_PERIODICITIES_V2:
                    size = base + (1 if index < remainder else 0)
                    name = f"fxcm-v2-{symbol}-{year}-{periodicity}.tar.zst"
                    rows.append({
                        "id": f"{year}-{symbol}-{periodicity}", "name": name,
                        "mimeType": "application/zstd", "size": str(size),
                        "appProperties": {
                            "vault_version": "v2", "operational_version": "v2.1",
                            "run_id": "33705800232",
                            "head_sha": "be864557a8e16d253e6aecf1519f85ad6162c1a3",
                            "year": str(year), "symbol": symbol, "periodicity": periodicity,
                            "sha256": "a" * 64, "partition": partition, "state": "UNSEALED",
                        },
                    })
                    index += 1
            rows.append({
                "id": f"manifest-{year}", "name": "YEAR_MANIFEST.json",
                "mimeType": "application/json", "size": "1",
                "appProperties": {
                    "vault_version": "v2", "operational_version": "v2.1",
                    "run_id": "33705800232",
                    "head_sha": "be864557a8e16d253e6aecf1519f85ad6162c1a3",
                    "year": str(year), "sha256": "b" * 64,
                    "state": "YEAR_COMPLETE_UNSEALED",
                },
            })
            return rows
        raise AssertionError("unknown fake object")


class SimpleRecoverySecurityTest(unittest.TestCase):
    @staticmethod
    def _accept_fake_inventory(contract, drive):
        rows = []
        for year in range(2012, 2022):
            stage = next(row for row in drive.stages if row["name"].endswith(str(year)))
            rows.append(simple_recovery._validate_preserved_stage(drive, stage, year))
        rows.extend(simple_recovery._empty_inventory_row(year) for year in range(2022, 2026))
        contract["existing_transaction"]["read_only_inventory_year_digest_sha256"] = simple_recovery.canonical_sha256(rows)

    def test_metadata_inventory_accepts_exact_empty_target(self):
        contract = json.loads(SPEC.read_text(encoding="utf-8"))
        drive = FakeDrive()
        self._accept_fake_inventory(contract, drive)
        _, stage = simple_recovery.verify_existing_transaction(drive, contract, 2022, "40000000000", "c" * 40)
        self.assertEqual(stage["id"], "stage-2022")

    def test_metadata_inventory_rejects_changed_individual_sha_and_sizes(self):
        contract = json.loads(SPEC.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(Exception, "inventory digest mismatch"):
            simple_recovery.verify_existing_transaction(FakeDrive(), contract, 2022, "40000000000", "c" * 40)

    def test_metadata_inventory_rejects_nonempty_target(self):
        contract = json.loads(SPEC.read_text(encoding="utf-8"))
        drive = FakeDrive()
        self._accept_fake_inventory(contract, drive)
        original = drive.list_children

        def nonempty(object_id):
            return [{"name": "unexpected"}] if object_id == "stage-2022" else original(object_id)

        drive.list_children = nonempty
        with self.assertRaisesRegex(Exception, "not exactly empty"):
            simple_recovery.verify_existing_transaction(drive, contract, 2022, "40000000000", "c" * 40)

    def test_workflow_has_no_price_artifact(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("actions/upload-artifact", workflow)
        self.assertNotIn("actions/download-artifact", workflow)
        self.assertIn("if: ${{ always() }}", workflow)
        self.assertIn("find \"$work\" -depth -type f -delete", workflow)
        self.assertIn("github.run_number == 1", workflow)
        self.assertIn("trap cleanup_current EXIT INT TERM HUP", workflow)
        self.assertNotIn("env:\n          PHASE9_GDRIVE_OAUTH_CLIENT_ID", workflow)
        self.assertEqual(workflow.count("PHASE9_GDRIVE_OAUTH_CLIENT_ID='${{ secrets.PHASE9_GDRIVE_OAUTH_CLIENT_ID }}'"), 1)

    def test_subprocess_environment_excludes_oauth_secrets(self):
        environment = simple_recovery.SANITIZED_SUBPROCESS_ENV
        self.assertFalse(set(simple_recovery.SECRET_NAMES) & set(environment))
        source = (RUNNER_DIR / "fxcm_drive_vault_run1_recovery_simple_v1.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("subprocess.run("), 2)
        self.assertEqual(source.count("env=SANITIZED_SUBPROCESS_ENV"), 2)

    def test_archive_member_allowlist_is_exact(self):
        self.assertEqual(
            simple_recovery.archive_expected_members((1, 3)),
            ["SHARD_PAYLOAD_MANIFEST.json", "canonical/prices.csv", "source/01.csv.gz", "source/03.csv.gz"],
        )

    def test_no_forbidden_research_authority(self):
        contract = json.loads(SPEC.read_text(encoding="utf-8"))
        self.assertFalse(contract["formal_phase9_authorization_effect"])
        self.assertFalse(contract["current_authorization"]["research_use"])


if __name__ == "__main__":
    unittest.main()
