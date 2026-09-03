#!/usr/bin/env python3
"""Create the sole uncommitted V2.1 Drive transaction before price access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fxcm_drive_vault_common import VaultError, sha256_file
from fxcm_drive_vault_v2_common import (
    OPERATIONAL_VERSION_V2_1,
    load_v2_1_operational_amendment,
    load_v2_contracts,
    require_v2_1_confirmations,
)
from fxcm_google_drive_private import FOLDER_MIME, GoogleDrivePrivate


def prepare(args: argparse.Namespace) -> dict[str, object]:
    paths = (
        args.acquisition_contract,
        args.partitions_contract,
        args.manifest_schema,
        args.formal_boundary,
        args.availability_mask,
    )
    contract, *_ = load_v2_contracts(*paths)
    amendment = load_v2_1_operational_amendment(args.operational_amendment, paths)
    require_v2_1_confirmations(
        amendment,
        args.confirmation,
        args.scope_confirmation,
        args.usage_confirmation,
        args.formal_acknowledgement,
    )
    if args.run_attempt != 1:
        raise VaultError("only first V2.1 run attempt is authorized")
    drive = GoogleDrivePrivate()
    root_id = contract["drive_custody"]["root_folder_id"]
    drive.verify_private_root(
        contract["drive_custody"]["root_folder_name"], root_id, require_empty=True
    )
    name = amendment["transactional_publication"]["transaction_name_template"].format(
        run_id=args.run_id
    )
    properties = {
        "vault_version": "v2",
        "operational_version": OPERATIONAL_VERSION_V2_1,
        "run_id": str(args.run_id),
        "head_sha": args.head_sha,
        "state": amendment["transactional_publication"]["transaction_initial_state"],
        "amendment_sha256": sha256_file(args.operational_amendment),
    }
    transaction = drive.create_folder_new(root_id, name, properties)
    children = drive.list_children(root_id)
    if (
        len(children) != 1
        or children[0].get("id") != transaction.get("id")
        or children[0].get("name") != name
        or children[0].get("mimeType") != FOLDER_MIME
        or children[0].get("appProperties") != properties
    ):
        raise VaultError("V2.1 transaction creation reconciliation failed")
    return {
        "status": "V2_1_TRANSACTION_PREPARED_NO_PRICE_ACCESS",
        "vault_version": "v2",
        "operational_version": OPERATIONAL_VERSION_V2_1,
        "run_id": str(args.run_id),
        "head_sha": args.head_sha,
        "root_was_empty": True,
        "price_response_body_bytes_read": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-contract", type=Path, required=True)
    parser.add_argument("--partitions-contract", type=Path, required=True)
    parser.add_argument("--manifest-schema", type=Path, required=True)
    parser.add_argument("--formal-boundary", type=Path, required=True)
    parser.add_argument("--availability-mask", type=Path, required=True)
    parser.add_argument("--operational-amendment", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--scope-confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--formal-acknowledgement", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
