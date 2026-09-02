import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
RUNNER = TRACK / "runner"
sys.path.insert(0, str(RUNNER))
import fxcm_drive_vault_common as common  # noqa: E402


class VaultContractTests(unittest.TestCase):
    def setUp(self):
        self.paths = (
            TRACK / "spec/fxcm_drive_vault_acquisition_v1.frozen.json",
            TRACK / "spec/fxcm_drive_vault_partitions_v1.frozen.json",
            TRACK / "spec/fxcm_drive_vault_manifest_schema_v1.frozen.json",
            TRACK / "spec/fxcm_drive_vault_formal_boundary_amendment_v1.frozen.json",
        )

    def test_exact_inventory_and_partitions(self):
        contract, partitions, manifest, formal = common.load_frozen_contracts(*self.paths)
        self.assertEqual(len(common.expected_shard_keys()), 1344)
        identities = list(common.iter_source_identities(contract))
        self.assertEqual(len(identities), 69888)
        self.assertEqual(len({row[4] for row in identities}), 69888)
        self.assertEqual(identities[0][:4], (2010, "AUDCAD", "m1", 1))
        self.assertEqual(identities[-1][:4], (2025, "USDJPY", "D1", 52))
        self.assertEqual(common.partition_for_year(partitions, 2019)["id"], "DEVELOPMENT")
        self.assertEqual(common.partition_for_year(partitions, 2020)["id"], "STRICT_OOS")
        self.assertEqual(common.partition_for_year(partitions, 2022)["id"], "ROBUSTNESS")
        self.assertEqual(common.partition_for_year(partitions, 2024)["id"], "FINAL_HOLDOUT")
        self.assertEqual(manifest["year_manifest"]["exact_shard_count"], 84)
        self.assertFalse(formal["formal_split_effect_if_executed"]["globally_unseen_formal_holdout_inside_vault"])
        self.assertEqual(contract["oauth"]["scope"], "https://www.googleapis.com/auth/drive.file")
        self.assertTrue(contract["oauth"]["preexisting_root_access_must_be_granted_to_same_oauth_client"])
        self.assertEqual(
            contract["oauth"]["inaccessible_root_action"],
            "FAIL_WITHOUT_SCOPE_EXPANSION_OR_PRICE_ACCESS",
        )

    def test_batch6_interval_is_preserved_exactly(self):
        partitions = json.loads(self.paths[1].read_text())
        interval = partitions["batch6_compatibility_interval"]
        self.assertEqual(interval["start_inclusive"], "2017-01-01T00:00:00Z")
        self.assertEqual(interval["end_exclusive"], "2018-12-31T00:00:00Z")
        self.assertFalse(interval["access_authorized"])

    def test_all_confirmations_are_required(self):
        contract, *_ = common.load_frozen_contracts(*self.paths)
        with self.assertRaises(common.VaultError):
            common.require_exact_confirmations(contract, "wrong", "wrong", "wrong", "acquisition")
        common.require_exact_confirmations(
            contract,
            contract["workflow"]["acquisition_confirmation"],
            contract["workflow"]["usage_confirmation"],
            "I_ACCEPT_EXPLORATORY_VAULT_2019_PLUS_RETIRES_FORMAL_PHASE9_UNSEEN_CLAIMS",
            "acquisition",
        )

    def test_unknown_target_mutation_is_rejected(self):
        values = [json.loads(path.read_text()) for path in self.paths]
        values[0]["target"]["symbols"] = values[0]["target"]["symbols"][:-1]
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index, value in enumerate(values):
                path = Path(temporary) / f"{index}.json"
                path.write_text(json.dumps(value))
                paths.append(path)
            with self.assertRaises(common.VaultError):
                common.load_frozen_contracts(*paths)


if __name__ == "__main__":
    unittest.main()
