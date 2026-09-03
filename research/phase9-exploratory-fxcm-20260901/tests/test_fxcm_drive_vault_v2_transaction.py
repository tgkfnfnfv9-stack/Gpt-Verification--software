import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


TRACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK / "runner"))
import fxcm_drive_vault_acquire_year as acquire_base  # noqa: E402
import fxcm_drive_vault_common as common  # noqa: E402
import fxcm_drive_vault_finalize_v2 as finalize_v2  # noqa: E402
import fxcm_drive_vault_prepare_v2_1 as prepare_v2_1  # noqa: E402
import fxcm_drive_vault_v2_common as v2  # noqa: E402
import fxcm_google_drive_private as drive_module  # noqa: E402


FROZEN_PATHS = (
    TRACK / "spec/fxcm_drive_vault_acquisition_v2.frozen.json",
    TRACK / "spec/fxcm_drive_vault_partitions_v2.frozen.json",
    TRACK / "spec/fxcm_drive_vault_manifest_schema_v2.frozen.json",
    TRACK / "spec/fxcm_drive_vault_formal_boundary_amendment_v2.frozen.json",
    TRACK / "spec/fxcm_drive_vault_availability_mask_v2.frozen.json",
)
AMENDMENT = TRACK / "spec/fxcm_drive_vault_operational_hardening_v2_1.frozen.json"


def owned_folder(file_id, name, parent, properties):
    return {
        "id": file_id,
        "name": name,
        "mimeType": drive_module.FOLDER_MIME,
        "parents": [parent],
        "appProperties": properties,
        "ownedByMe": True,
        "trashed": False,
    }


class VaultV21TransactionTests(unittest.TestCase):
    def test_amendment_anchors_unchanged_v2_contracts_and_no_authorization(self):
        amendment = v2.load_v2_1_operational_amendment(AMENDMENT, FROZEN_PATHS)
        self.assertEqual(
            amendment["frozen_v2_contract_sha256"],
            {path.name: common.sha256_file(path) for path in FROZEN_PATHS},
        )
        self.assertFalse(amendment["authorization"]["price_acquisition_authorized"])
        self.assertFalse(amendment["authorization"]["workflow_dispatch_authorized"])
        self.assertEqual(amendment["scientific_scope_changes"], [])

    def test_source_url_is_exactly_pinned(self):
        contract = json.loads(FROZEN_PATHS[0].read_text())
        expected = "https://candledata.fxcorporate.com/m1/EURUSD/2017/1.csv.gz"
        self.assertEqual(common.source_url(contract, 2017, "EURUSD", "m1", 1), expected)
        for replacement in (
            "http://candledata.fxcorporate.com/{periodicity}/{instrument}/{year}/{week}.csv.gz",
            "https://evil.example/{periodicity}/{instrument}/{year}/{week}.csv.gz",
            "https://candledata.fxcorporate.com:444/{periodicity}/{instrument}/{year}/{week}.csv.gz",
            "https://candledata.fxcorporate.com/{periodicity}/{instrument}/{year}/{week}.csv.gz?q=1",
        ):
            changed = json.loads(json.dumps(contract))
            changed["provider"]["base_url_template"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(common.VaultError):
                common.source_url(changed, 2017, "EURUSD", "m1", 1)

    def test_private_root_rejects_any_shared_permission(self):
        client = object.__new__(drive_module.GoogleDrivePrivate)
        base = {
            "id": v2.ROOT_FOLDER_ID_V2,
            "name": "Phase9 FXCM Data Vault",
            "mimeType": drive_module.FOLDER_MIME,
            "ownedByMe": True,
            "trashed": False,
            "permissionIds": ["owner", "anyone"],
            "permissions": [
                {"id": "owner", "type": "user", "role": "owner"},
                {"id": "anyone", "type": "anyone", "role": "reader"},
            ],
        }
        client._json_request = mock.Mock(return_value=base)
        with self.assertRaises(common.VaultError):
            client.verify_private_root("Phase9 FXCM Data Vault", v2.ROOT_FOLDER_ID_V2)

    def test_child_listing_rejects_direct_share(self):
        client = object.__new__(drive_module.GoogleDrivePrivate)
        client._private_owner_permission_id = "owner"
        child = owned_folder("child", "stage", "parent", {"state": "UNSEALED"})
        child["permissionIds"] = ["owner"]
        child["permissions"] = [
            {"id": "owner", "type": "user", "role": "owner"},
            {"id": "anyone", "type": "anyone", "role": "reader"},
        ]
        client._json_request = mock.Mock(return_value={"files": [child]})
        with self.assertRaisesRegex(common.VaultError, "directly shared"):
            client.list_children("parent")

    def test_publish_response_loss_is_reconciled_only_for_exact_commit(self):
        client = object.__new__(drive_module.GoogleDrivePrivate)
        original = {"state": "ACQUIRING"}
        committed = {"state": "COMMITTED"}
        response = owned_folder("txn", "v2", v2.ROOT_FOLDER_ID_V2, committed)
        client._json_request = mock.Mock(side_effect=[common.VaultError("lost"), response])
        result = client.publish_folder_reconciled(
            "txn", "v2-txn-run-1", "v2", v2.ROOT_FOLDER_ID_V2, original, committed
        )
        self.assertEqual(result["appProperties"], committed)
        ambiguous = dict(response)
        ambiguous["appProperties"] = {"state": "OTHER"}
        client._json_request = mock.Mock(side_effect=[common.VaultError("lost"), ambiguous])
        with self.assertRaisesRegex(common.VaultError, "UNKNOWN_COMMIT_OUTCOME"):
            client.publish_folder_reconciled(
                "txn", "v2-txn-run-1", "v2", v2.ROOT_FOLDER_ID_V2, original, committed
            )

    def test_publish_response_loss_exact_original_and_get_failure_fail_closed(self):
        client = object.__new__(drive_module.GoogleDrivePrivate)
        original = {"state": "ACQUIRING"}
        committed = {"state": "COMMITTED"}
        unchanged = owned_folder(
            "txn", "v2-txn-run-1", v2.ROOT_FOLDER_ID_V2, original
        )
        client._json_request = mock.Mock(side_effect=[common.VaultError("lost"), unchanged])
        with self.assertRaisesRegex(common.VaultError, "was not committed"):
            client.publish_folder_reconciled(
                "txn", "v2-txn-run-1", "v2", v2.ROOT_FOLDER_ID_V2, original, committed
            )
        client._json_request = mock.Mock(
            side_effect=[common.VaultError("lost"), common.VaultError("get lost")]
        )
        with self.assertRaisesRegex(common.VaultError, "UNKNOWN_COMMIT_OUTCOME"):
            client.publish_folder_reconciled(
                "txn", "v2-txn-run-1", "v2", v2.ROOT_FOLDER_ID_V2, original, committed
            )

    def test_publish_rejects_wrong_parent(self):
        client = object.__new__(drive_module.GoogleDrivePrivate)
        original = {"state": "ACQUIRING"}
        committed = {"state": "COMMITTED"}
        response = owned_folder("txn", "v2", "wrong-parent", committed)
        client._json_request = mock.Mock(return_value=response)
        with self.assertRaisesRegex(common.VaultError, "UNKNOWN_COMMIT_OUTCOME"):
            client.publish_folder_reconciled(
                "txn", "v2-txn-run-1", "v2", v2.ROOT_FOLDER_ID_V2, original, committed
            )

    def test_exact_private_tree_rejects_extra_and_mutated_objects(self):
        expected = {
            "parent": {
                "child": {
                    "name": "manifest",
                    "mimeType": drive_module.FOLDER_MIME,
                    "appProperties": {"role": "MANIFEST"},
                    "size": 123,
                }
            },
            "child": {},
        }
        exact = owned_folder("child", "manifest", "parent", {"role": "MANIFEST"})
        exact["size"] = "123"
        fake = mock.Mock()
        fake.list_children.side_effect = [[exact], []]
        finalize_v2.verify_exact_private_tree(fake, expected)
        extra = owned_folder("extra", "unexpected", "parent", {})
        fake.list_children.side_effect = [[exact, extra]]
        with self.assertRaisesRegex(common.VaultError, "inventory mismatch"):
            finalize_v2.verify_exact_private_tree(fake, expected)
        mutated = dict(exact)
        mutated["appProperties"] = {"role": "OTHER"}
        fake.list_children.side_effect = [[mutated]]
        with self.assertRaisesRegex(common.VaultError, "identity mismatch"):
            finalize_v2.verify_exact_private_tree(fake, expected)

    def test_download_rejects_changed_final_url_before_reading_body(self):
        url = "https://candledata.fxcorporate.com/m1/EURUSD/2017/1.csv.gz"

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return url + "?redirected=1"

            def read(self, _size):
                raise AssertionError("body must not be read after final URL mismatch")

        opener = mock.Mock()
        opener.open.return_value = Response()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "source.csv.gz"
            with self.assertRaisesRegex(common.VaultError, "final URL mismatch"):
                acquire_base.download_source(opener, url, destination)
            self.assertFalse(destination.exists())

    def test_prepare_requires_empty_private_root_and_creates_one_transaction(self):
        contract = json.loads(FROZEN_PATHS[0].read_text())
        amendment = json.loads(AMENDMENT.read_text())
        workflow = amendment["workflow"]
        properties = {
            "vault_version": "v2",
            "operational_version": "v2.1",
            "run_id": "77",
            "head_sha": "a" * 40,
            "state": "ACQUIRING",
            "amendment_sha256": common.sha256_file(AMENDMENT),
        }
        transaction = owned_folder(
            "txn", "v2-txn-run-77", contract["drive_custody"]["root_folder_id"], properties
        )
        fake = mock.Mock()
        fake.create_folder_new.return_value = transaction
        fake.list_children.return_value = [transaction]
        args = SimpleNamespace(
            acquisition_contract=FROZEN_PATHS[0],
            partitions_contract=FROZEN_PATHS[1],
            manifest_schema=FROZEN_PATHS[2],
            formal_boundary=FROZEN_PATHS[3],
            availability_mask=FROZEN_PATHS[4],
            operational_amendment=AMENDMENT,
            run_id="77",
            run_attempt=1,
            head_sha="a" * 40,
            confirmation=workflow["acquisition_confirmation"],
            scope_confirmation=workflow["scope_confirmation"],
            usage_confirmation=workflow["usage_confirmation"],
            formal_acknowledgement=workflow["formal_acknowledgement"],
        )
        with mock.patch.object(prepare_v2_1, "GoogleDrivePrivate", return_value=fake):
            result = prepare_v2_1.prepare(args)
        fake.verify_private_root.assert_called_once_with(
            "Phase9 FXCM Data Vault", v2.ROOT_FOLDER_ID_V2, require_empty=True
        )
        fake.create_folder_new.assert_called_once_with(
            v2.ROOT_FOLDER_ID_V2, "v2-txn-run-77", properties
        )
        self.assertEqual(result["price_response_body_bytes_read"], 0)

    def test_tree_is_created_inside_transaction_not_canonical_root(self):
        fake = mock.Mock()
        counter = iter(range(1, 9))

        def create(parent, name, properties):
            return owned_folder(str(next(counter)), name, parent, properties)

        fake.create_folder_new.side_effect = create
        transaction = owned_folder(
            "txn", "v2-txn-run-1", v2.ROOT_FOLDER_ID_V2, {"state": "ACQUIRING"}
        )
        tree = finalize_v2.create_tree_v2(fake, transaction, "1")
        self.assertEqual(tree["v2"]["id"], "txn")
        self.assertEqual(fake.create_folder_new.call_args_list[0].args[0], "txn")
        self.assertNotIn(
            v2.ROOT_FOLDER_ID_V2,
            [call.args[0] for call in fake.create_folder_new.call_args_list],
        )

    def test_crossed_row_is_counted_as_canonical_gap(self):
        header = "DateTime,BidOpen,BidHigh,BidLow,BidClose,AskOpen,AskHigh,AskLow,AskClose\n"
        rows = [
            "01/01/2017 00:00:00.000,1,1.1,0.9,1,1.01,1.11,0.91,1.01\n",
            "01/01/2017 00:01:00.000,1,1.1,0.9,1,0.99,1.11,0.91,1.01\n",
            "01/01/2017 00:02:00.000,1,1.1,0.9,1,1.01,1.11,0.91,1.01\n",
        ]

        def fake_download(_opener, _url, destination):
            with gzip.open(destination, "wt", encoding="utf-8", newline="") as handle:
                handle.write(header)
                handle.writelines(rows)
            body = destination.read_bytes()
            return len(body), hashlib.sha256(body).hexdigest()

        contract = json.loads(FROZEN_PATHS[0].read_text())
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            acquire_base, "download_source", side_effect=fake_download
        ):
            _, payload = acquire_base.process_direct_shard(
                contract,
                2017,
                "EURUSD",
                "m1",
                Path(temporary),
                object(),
                weeks=(1,),
                vault_version="v2",
            )
        self.assertEqual(payload["observed_row_count"], 3)
        self.assertEqual(payload["usable_row_count"], 2)
        self.assertEqual(payload["crossed_quote_count"], 1)
        self.assertEqual(payload["gap_segment_count"], 1)
        self.assertEqual(payload["missing_nominal_slot_count"], 1)


if __name__ == "__main__":
    unittest.main()
