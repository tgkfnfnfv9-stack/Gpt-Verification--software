import json
import sys
import tempfile
import unittest
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK / "runner"))
import fxcm_drive_vault_common as common  # noqa: E402
import fxcm_drive_vault_v2_common as v2  # noqa: E402


class VaultV2ContractTests(unittest.TestCase):
    def setUp(self):
        self.paths = (
            TRACK / "spec/fxcm_drive_vault_acquisition_v2.frozen.json",
            TRACK / "spec/fxcm_drive_vault_partitions_v2.frozen.json",
            TRACK / "spec/fxcm_drive_vault_manifest_schema_v2.frozen.json",
            TRACK / "spec/fxcm_drive_vault_formal_boundary_amendment_v2.frozen.json",
            TRACK / "spec/fxcm_drive_vault_availability_mask_v2.frozen.json",
        )

    def test_exact_availability_backed_inventory(self):
        contract, _, _, _, mask = v2.load_v2_contracts(*self.paths)
        self.assertEqual(len(v2.expected_shard_keys_v2()), 700)
        identities = list(v2.iter_present_source_identities(contract, mask))
        self.assertEqual(len(identities), 36000)
        self.assertEqual(len({row[4] for row in identities}), 36000)
        self.assertEqual(len(v2.missing_identity_set(mask)), 400)
        self.assertEqual(v2.expected_year_source_count(mask, 2012), 2600)
        self.assertEqual(v2.expected_year_source_count(mask, 2019), 2558)
        self.assertEqual(v2.expected_year_source_count(mask, 2024), 2479)
        self.assertEqual(v2.expected_year_source_count(mask, 2025), 2405)
        self.assertEqual(set(contract["target"]["excluded_unavailable_symbols"]), {"CHFJPY", "EURCAD", "GBPAUD"})
        self.assertEqual(contract["target"]["direct_periodicities"], ["m1", "H1"])
        self.assertIn("direct D1", contract["target"]["excluded"])

    def test_exact_partition_boundaries_and_batch6_lock(self):
        _, partitions, _, _, _ = v2.load_v2_contracts(*self.paths)
        self.assertEqual(v2.partition_for_year_v2(partitions, 2019)["id"], "DEVELOPMENT")
        self.assertEqual(v2.partition_for_year_v2(partitions, 2020)["id"], "STRICT_OOS")
        self.assertEqual(v2.partition_for_year_v2(partitions, 2022)["id"], "ROBUSTNESS")
        self.assertEqual(v2.partition_for_year_v2(partitions, 2024)["id"], "FINAL_HOLDOUT")
        interval = partitions["batch6_compatibility_interval"]
        self.assertEqual(interval["start_inclusive"], "2017-01-01T00:00:00Z")
        self.assertEqual(interval["end_exclusive"], "2018-12-31T00:00:00Z")
        self.assertFalse(interval["access_authorized"])

    def test_all_four_confirmations_are_required(self):
        contract, *_ = v2.load_v2_contracts(*self.paths)
        workflow = contract["workflow"]
        values = (
            workflow["acquisition_confirmation"],
            workflow["scope_confirmation"],
            workflow["usage_confirmation"],
            workflow["formal_acknowledgement"],
        )
        v2.require_v2_confirmations(contract, *values)
        for index in range(4):
            changed = list(values)
            changed[index] = "wrong"
            with self.subTest(index=index), self.assertRaises(common.VaultError):
                v2.require_v2_confirmations(contract, *changed)

    def test_mask_mutation_is_rejected(self):
        values = [json.loads(path.read_text()) for path in self.paths]
        values[-1]["known_missing_identity_keys"][0] = "2012/AUDCAD/m1/01"
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index, value in enumerate(values):
                path = Path(temporary) / self.paths[index].name
                path.write_text(json.dumps(value), encoding="utf-8")
                paths.append(path)
            with self.assertRaises(common.VaultError):
                v2.load_v2_contracts(*paths)


if __name__ == "__main__":
    unittest.main()
