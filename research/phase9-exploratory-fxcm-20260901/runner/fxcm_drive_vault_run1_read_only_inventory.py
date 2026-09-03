#!/usr/bin/env python3
"""Inventory the failed V2.1 Drive transaction using metadata GETs only."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from fxcm_drive_vault_common import (
    HEX64,
    VaultError,
    canonical_sha256,
    load_json,
    sha256_file,
    write_canonical_json,
)
from fxcm_google_drive_read_only import FOLDER_MIME, GoogleDriveReadOnly


SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-read-only-inventory-v2.1.0"
REPORT_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-read-only-report-v2.1.0"
REPORT_FILES = ("VAULT_RUN1_READ_ONLY_INVENTORY.json", "artifact_manifest_sha256.txt")
SOURCE_RUN_ID = 33705800232
SOURCE_HEAD_SHA = "be864557a8e16d253e6aecf1519f85ad6162c1a3"
AMENDMENT_SHA256 = "03b8ecaa6a75a1df797f8c4de5fbdf5b59ce0a5655957a5f04c1ab595301434b"
YEARS = tuple(range(2012, 2026))
SYMBOLS = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY",
    "EURAUD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD", "GBPCAD",
    "GBPCHF", "GBPJPY", "GBPNZD", "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY",
    "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
)
PERIODICITIES = ("m1", "H1")


def load_inventory_contract(path: Path, amendment_path: Path) -> dict[str, Any]:
    contract = load_json(path)
    source = contract.get("source_acquisition", {})
    drive = contract.get("drive_scope", {})
    allowed = contract.get("allowed_operations", {})
    report = contract.get("public_report", {})
    workflow = contract.get("workflow", {})
    authorization = contract.get("authorization", {})
    dependencies = contract.get("frozen_dependencies", {})
    checks = (
        contract.get("schema_version") == SCHEMA,
        contract.get("status") == "FROZEN_USER_APPROVED_DESIGN_NOT_EXECUTED",
        contract.get("track") == "EXPLORATORY_FXCM_DRIVE_VAULT_NOT_FORMAL_PHASE9",
        source.get("run_id") == SOURCE_RUN_ID,
        source.get("run_number") == 1,
        source.get("run_attempt") == 1,
        source.get("head_sha") == SOURCE_HEAD_SHA,
        source.get("conclusion") == "failure",
        source.get("transaction_name") == f"v2-txn-run-{SOURCE_RUN_ID}",
        source.get("expected_transaction_state") == "ACQUIRING",
        source.get("successful_years") == list(range(2012, 2022)),
        source.get("failed_years") == [2022, 2023, 2024, 2025],
        source.get("finalizer_conclusion") == "skipped",
        source.get("public_artifact_count") == 0,
        drive.get("root_folder_id") == "1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v",
        drive.get("root_folder_name") == "Phase9 FXCM Data Vault",
        drive.get("vault_version") == "v2",
        drive.get("operational_version") == "v2.1",
        drive.get("years") == list(YEARS),
        drive.get("symbols") == list(SYMBOLS),
        drive.get("direct_periodicities") == list(PERIODICITIES),
        drive.get("expected_archive_names_per_year") == 50,
        drive.get("expected_complete_stage_children_per_year") == 51,
        drive.get("year_manifest_name") == "YEAR_MANIFEST.json",
        allowed.get("drive_api_methods") == ["GET"],
        allowed.get("drive_metadata_list") is True,
        allowed.get("drive_metadata_get") is True,
        allowed.get("drive_file_content_download") is False,
        allowed.get("fxcm_source_request") is False,
        all(allowed.get(key) is False for key in (
            "drive_create", "drive_upload", "drive_patch", "drive_move", "drive_rename",
            "drive_delete", "drive_permission_change", "transaction_finalize",
            "canonical_publish", "automatic_remote_cleanup",
        )),
        report.get("exact_files") == list(REPORT_FILES),
        report.get("drive_object_ids_allowed") is False,
        report.get("arbitrary_remote_names_allowed") is False,
        report.get("price_bytes_allowed") is False,
        report.get("credentials_allowed") is False,
        report.get("research_statistics_allowed") is False,
        workflow.get("manual_only") is True,
        workflow.get("required_run_number") == 1,
        workflow.get("required_run_attempt") == 1,
        workflow.get("environment") == "phase9-fxcm-vault-acquisition-v2",
        workflow.get("reviewed_head_sha_required") is True,
        workflow.get("confirmation") == "INVENTORY_PHASE9_FXCM_VAULT_RUN_33705800232_METADATA_ONLY_NO_MUTATION",
        authorization.get("inventory_design_approved") is True,
        authorization.get("workflow_dispatch_authorized") is False,
        authorization.get("cleanup_authorized") is False,
        authorization.get("recovery_acquisition_authorized") is False,
        authorization.get("v2_1_rerun_authorized") is False,
        authorization.get("count_only_authorized") is False,
        authorization.get("batch6_authorized") is False,
        authorization.get("returns_or_outcomes_authorized") is False,
        authorization.get("formal_phase9_authorization_effect") is False,
        dependencies.get(amendment_path.name) == AMENDMENT_SHA256,
        sha256_file(amendment_path) == AMENDMENT_SHA256,
    )
    if not all(checks):
        raise VaultError("read-only Run #1 inventory contract mismatch")
    return contract


def _expected_archive_names(year: int) -> list[str]:
    return [
        f"fxcm-v2-{symbol}-{year}-{periodicity}.tar.zst"
        for symbol in SYMBOLS
        for periodicity in PERIODICITIES
    ]


def _partition(year: int) -> str:
    if year <= 2019:
        return "DEVELOPMENT"
    if year <= 2021:
        return "STRICT_OOS"
    if year <= 2023:
        return "ROBUSTNESS"
    return "FINAL_HOLDOUT"


def _stage_inventory(
    drive: GoogleDriveReadOnly,
    stage: dict[str, Any],
    year: int,
    stage_properties_valid: bool,
) -> dict[str, Any]:
    children = drive.list_children(stage["id"])
    expected_names = _expected_archive_names(year)
    expected_set = set(expected_names)
    valid_metadata: list[dict[str, Any]] = []
    missing = 0
    invalid = 0
    duplicate_extra = 0
    for name in expected_names:
        matches = [row for row in children if row.get("name") == name]
        if not matches:
            missing += 1
            continue
        duplicate_extra += max(0, len(matches) - 1)
        if len(matches) != 1:
            invalid += 1
            continue
        row = matches[0]
        symbol, periodicity = name[len("fxcm-v2-") : -len(".tar.zst")].rsplit("-", 2)[0::2]
        properties = row.get("appProperties")
        size_text = row.get("size")
        try:
            size = int(size_text)
        except (TypeError, ValueError):
            size = -1
        expected_properties = {
            "vault_version": "v2",
            "operational_version": "v2.1",
            "run_id": str(SOURCE_RUN_ID),
            "head_sha": SOURCE_HEAD_SHA,
            "year": str(year),
            "symbol": symbol,
            "periodicity": periodicity,
            "partition": _partition(year),
            "state": "UNSEALED",
        }
        sha = properties.get("sha256") if isinstance(properties, dict) else None
        comparable = dict(properties) if isinstance(properties, dict) else {}
        comparable.pop("sha256", None)
        if (
            row.get("mimeType") != "application/zstd"
            or size <= 0
            or not isinstance(sha, str)
            or HEX64.fullmatch(sha) is None
            or comparable != expected_properties
        ):
            invalid += 1
            continue
        valid_metadata.append({"name": name, "size": size, "sha256": sha})

    manifests = [row for row in children if row.get("name") == "YEAR_MANIFEST.json"]
    manifest_valid = False
    if len(manifests) == 1:
        manifest = manifests[0]
        properties = manifest.get("appProperties")
        sha = properties.get("sha256") if isinstance(properties, dict) else None
        comparable = dict(properties) if isinstance(properties, dict) else {}
        comparable.pop("sha256", None)
        try:
            manifest_size = int(manifest.get("size"))
        except (TypeError, ValueError):
            manifest_size = -1
        manifest_valid = (
            manifest.get("mimeType") == "application/json"
            and manifest_size > 0
            and isinstance(sha, str)
            and HEX64.fullmatch(sha) is not None
            and comparable == {
                "vault_version": "v2",
                "operational_version": "v2.1",
                "run_id": str(SOURCE_RUN_ID),
                "head_sha": SOURCE_HEAD_SHA,
                "year": str(year),
                "state": "YEAR_COMPLETE_UNSEALED",
            }
        )
    unexpected = sum(
        row.get("name") not in expected_set and row.get("name") != "YEAR_MANIFEST.json"
        for row in children
    )
    valid_metadata.sort(key=lambda row: row["name"])
    complete = (
        stage_properties_valid
        and len(children) == 51
        and len(valid_metadata) == 50
        and missing == 0
        and invalid == 0
        and duplicate_extra == 0
        and len(manifests) == 1
        and manifest_valid
        and unexpected == 0
    )
    return {
        "year": year,
        "stage_match_count": 1,
        "stage_metadata_valid": stage_properties_valid,
        "child_object_count": len(children),
        "expected_archive_count": 50,
        "valid_archive_metadata_count": len(valid_metadata),
        "missing_archive_count": missing,
        "invalid_archive_metadata_count": invalid,
        "duplicate_expected_name_extra_count": duplicate_extra,
        "unexpected_child_object_count": unexpected,
        "year_manifest_match_count": len(manifests),
        "year_manifest_metadata_valid": manifest_valid,
        "valid_archive_names_sha256": canonical_sha256([row["name"] for row in valid_metadata]),
        "valid_archive_metadata_sha256": canonical_sha256(valid_metadata),
        "valid_archive_total_bytes": sum(row["size"] for row in valid_metadata),
        "stage_classification": "COMPLETE_YEAR_STAGE_METADATA_ONLY" if complete else "PARTIAL_OR_INVALID_YEAR_STAGE_METADATA_ONLY",
    }


def build_inventory(
    contract: dict[str, Any],
    inventory_run_id: str,
    inventory_run_attempt: int,
    inventory_head_sha: str,
    drive: GoogleDriveReadOnly | None = None,
) -> dict[str, Any]:
    if inventory_run_attempt != 1 or not inventory_run_id or not inventory_head_sha:
        raise VaultError("read-only inventory workflow identity mismatch")
    drive = drive or GoogleDriveReadOnly()
    scope = contract["drive_scope"]
    source = contract["source_acquisition"]
    drive.verify_private_root(scope["root_folder_id"], scope["root_folder_name"])
    root_children = drive.list_children(scope["root_folder_id"])
    transaction_named = [row for row in root_children if row.get("name") == source["transaction_name"]]
    canonical_named = [row for row in root_children if row.get("name") == "v2"]
    transaction_properties = {
        "vault_version": "v2",
        "operational_version": "v2.1",
        "run_id": str(SOURCE_RUN_ID),
        "head_sha": SOURCE_HEAD_SHA,
        "state": "ACQUIRING",
        "amendment_sha256": AMENDMENT_SHA256,
    }
    transaction_valid = (
        len(transaction_named) == 1
        and transaction_named[0].get("mimeType") == FOLDER_MIME
        and transaction_named[0].get("appProperties") == transaction_properties
    )
    year_rows: list[dict[str, Any]] = []
    unexpected_transaction_children = 0
    if len(transaction_named) == 1 and transaction_named[0].get("mimeType") == FOLDER_MIME:
        transaction_children = drive.list_children(transaction_named[0]["id"])
        expected_stage_names = {f"v2-staging-run-{SOURCE_RUN_ID}-year-{year}" for year in YEARS}
        unexpected_transaction_children = sum(row.get("name") not in expected_stage_names for row in transaction_children)
        for year in YEARS:
            stage_name = f"v2-staging-run-{SOURCE_RUN_ID}-year-{year}"
            matches = [row for row in transaction_children if row.get("name") == stage_name]
            expected_properties = {
                "vault_version": "v2",
                "operational_version": "v2.1",
                "run_id": str(SOURCE_RUN_ID),
                "head_sha": SOURCE_HEAD_SHA,
                "year": str(year),
                "state": "UNSEALED",
            }
            if len(matches) == 1 and matches[0].get("mimeType") == FOLDER_MIME:
                year_rows.append(_stage_inventory(
                    drive, matches[0], year, matches[0].get("appProperties") == expected_properties
                ))
            else:
                year_rows.append({
                    "year": year,
                    "stage_match_count": len(matches),
                    "stage_metadata_valid": False,
                    "child_object_count": 0,
                    "expected_archive_count": 50,
                    "valid_archive_metadata_count": 0,
                    "missing_archive_count": 50,
                    "invalid_archive_metadata_count": 0,
                    "duplicate_expected_name_extra_count": max(0, len(matches) - 1),
                    "unexpected_child_object_count": 0,
                    "year_manifest_match_count": 0,
                    "year_manifest_metadata_valid": False,
                    "valid_archive_names_sha256": canonical_sha256([]),
                    "valid_archive_metadata_sha256": canonical_sha256([]),
                    "valid_archive_total_bytes": 0,
                    "stage_classification": "MISSING_OR_AMBIGUOUS_YEAR_STAGE_METADATA_ONLY",
                })
    else:
        for year in YEARS:
            year_rows.append({
                "year": year,
                "stage_match_count": 0,
                "stage_metadata_valid": False,
                "child_object_count": 0,
                "expected_archive_count": 50,
                "valid_archive_metadata_count": 0,
                "missing_archive_count": 50,
                "invalid_archive_metadata_count": 0,
                "duplicate_expected_name_extra_count": 0,
                "unexpected_child_object_count": 0,
                "year_manifest_match_count": 0,
                "year_manifest_metadata_valid": False,
                "valid_archive_names_sha256": canonical_sha256([]),
                "valid_archive_metadata_sha256": canonical_sha256([]),
                "valid_archive_total_bytes": 0,
                "stage_classification": "TRANSACTION_UNAVAILABLE_FOR_YEAR_INVENTORY",
            })

    complete_years = [row["year"] for row in year_rows if row["stage_classification"] == "COMPLETE_YEAR_STAGE_METADATA_ONLY"]
    return {
        "schema_version": REPORT_SCHEMA,
        "status": "INVENTORY_COMPLETED_READ_ONLY_METADATA_GETS_ONLY",
        "inventory_run_id": inventory_run_id,
        "inventory_run_attempt": inventory_run_attempt,
        "inventory_head_sha": inventory_head_sha,
        "source_acquisition_run_id": SOURCE_RUN_ID,
        "source_acquisition_run_attempt": 1,
        "source_acquisition_head_sha": SOURCE_HEAD_SHA,
        "source_acquisition_conclusion": "failure",
        "root_owner_only_verified": True,
        "root_child_object_count": len(root_children),
        "transaction_name_match_count": len(transaction_named),
        "transaction_metadata_valid": transaction_valid,
        "canonical_v2_name_match_count": len(canonical_named),
        "unexpected_root_child_object_count": len(root_children) - len(transaction_named) - len(canonical_named),
        "unexpected_transaction_child_object_count": unexpected_transaction_children,
        "year_count": len(year_rows),
        "complete_year_stage_count": len(complete_years),
        "complete_years": complete_years,
        "partial_or_unavailable_years": [row["year"] for row in year_rows if row["year"] not in complete_years],
        "year_stage_inventory_sha256": canonical_sha256(year_rows),
        "year_stages": year_rows,
        "drive_api_methods": ["GET"],
        "drive_mutation_count": 0,
        "drive_file_content_bytes_read": 0,
        "fxcm_source_request_count": 0,
        "price_bytes_read": 0,
        "credentials_in_public_report": False,
        "drive_object_ids_in_public_report": 0,
        "arbitrary_remote_names_in_public_report": 0,
        "cleanup_authorized": False,
        "recovery_acquisition_authorized": False,
        "v2_1_rerun_authorized": False,
        "count_only_authorized": False,
        "batch6_authorized": False,
        "research_statistics_calculated": False,
        "formal_phase9_authorization_effect": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-contract", type=Path, required=True)
    parser.add_argument("--operational-amendment", type=Path, required=True)
    parser.add_argument("--inventory-run-id", required=True)
    parser.add_argument("--inventory-run-attempt", type=int, required=True)
    parser.add_argument("--inventory-head-sha", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    contract = load_inventory_contract(args.inventory_contract, args.operational_amendment)
    if args.confirmation != contract["workflow"]["confirmation"]:
        raise VaultError("read-only inventory confirmation mismatch")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise VaultError("read-only inventory output directory must be new")
    args.output_dir.mkdir(parents=True)
    report = build_inventory(
        contract,
        args.inventory_run_id,
        args.inventory_run_attempt,
        args.inventory_head_sha,
    )
    report_path = args.output_dir / REPORT_FILES[0]
    write_canonical_json(report_path, report)
    (args.output_dir / REPORT_FILES[1]).write_text(
        f"{sha256_file(report_path)}  {report_path.name}\n", encoding="ascii"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
