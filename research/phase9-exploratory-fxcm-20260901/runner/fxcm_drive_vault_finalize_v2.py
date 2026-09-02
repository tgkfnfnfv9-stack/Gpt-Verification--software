#!/usr/bin/env python3
"""Promote 14 complete V2 year stages and write the private vault seal last."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from fxcm_drive_vault_common import (
    ROOT_FOLDER_ID,
    VaultError,
    assert_hex64,
    canonical_sha256,
    contract_sha_bundle,
    load_json,
    reject_prohibited_keys,
    sha256_file,
    source_url,
    validate_public_report_tree,
    write_canonical_json,
)
from fxcm_drive_vault_finalize import upload_and_verify_json
from fxcm_drive_vault_v2_common import (
    DIRECT_PERIODICITIES_V2,
    KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2,
    PRESENT_SOURCE_OBJECT_COUNT_V2,
    SYMBOLS_V2,
    YEARS_V2,
    expected_year_source_count,
    known_missing_weeks,
    load_v2_contracts,
    partition_for_year_v2,
    present_weeks,
    require_v2_confirmations,
)
from fxcm_google_drive_private import FOLDER_MIME, GoogleDrivePrivate


def create_tree_v2(drive: GoogleDrivePrivate, run_id: str) -> dict[str, Any]:
    version = {"vault_version": "v2", "run_id": run_id}
    root = drive.create_folder_new(
        ROOT_FOLDER_ID, "v2", {**version, "state": "PROMOTING"}
    )
    manifest = drive.create_folder_new(
        root["id"], "manifest", {"vault_version": "v2", "role": "MANIFEST"}
    )
    years_manifest = drive.create_folder_new(
        manifest["id"], "years", {"vault_version": "v2", "role": "YEAR_MANIFESTS"}
    )
    prices = drive.create_folder_new(
        root["id"], "prices", {"vault_version": "v2", "partition": "DEVELOPMENT"}
    )
    sealed = drive.create_folder_new(
        root["id"], "sealed", {"vault_version": "v2", "role": "SEALED"}
    )
    oos = drive.create_folder_new(
        sealed["id"], "oos", {"vault_version": "v2", "partition": "STRICT_OOS"}
    )
    robustness = drive.create_folder_new(
        sealed["id"], "robustness", {"vault_version": "v2", "partition": "ROBUSTNESS"}
    )
    final_holdout = drive.create_folder_new(
        sealed["id"], "final_holdout", {"vault_version": "v2", "partition": "FINAL_HOLDOUT"}
    )
    staging = drive.create_folder_new(
        root["id"], "staging", {"vault_version": "v2", "role": "COMPLETED_EMPTY_STAGES"}
    )
    return {
        "v2": root,
        "manifest": manifest,
        "years_manifest": years_manifest,
        "prices": prices,
        "STRICT_OOS": oos,
        "ROBUSTNESS": robustness,
        "FINAL_HOLDOUT": final_holdout,
        "staging": staging,
    }


def read_year_manifest_v2(
    drive: GoogleDrivePrivate,
    stage: dict[str, Any],
    year: int,
    run_id: str,
    head_sha: str,
    temp_dir: Path,
    manifest_schema: dict[str, Any],
    contract: dict[str, Any],
    partitions: dict[str, Any],
    mask: dict[str, Any],
    expected_contract_hashes: dict[str, str],
    expected_mask_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    children = drive.list_children(stage["id"])
    if len(children) != 51:
        raise VaultError(f"V2 year {year} staging file count mismatch")
    manifests = [row for row in children if row.get("name") == "YEAR_MANIFEST.json"]
    if len(manifests) != 1:
        raise VaultError("V2 year manifest not unique")
    metadata = manifests[0]
    props = metadata.get("appProperties") or {}
    expected_sha = props.get("sha256", "")
    expected_size = int(metadata.get("size", -1))
    destination = temp_dir / f"v2-year-{year}-manifest.json"
    drive.download_verify(metadata["id"], destination, expected_size, expected_sha)
    value = load_json(destination)
    reject_prohibited_keys(value)
    expected_keys = {
        "schema_version", "status", "vault_version", "run_id", "run_attempt", "head_sha",
        "year", "partition_id", "contract_sha256", "availability_mask_sha256",
        "base_source_object_count", "source_object_count", "known_missing_source_object_count",
        "shard_count", "zstd_version", "shards_sha256", "derived_qc_sha256",
        "batch6_compatibility_passed", "provider_schedule_claimed", "forward_fill_count",
        "interpolation_count", "formal_phase9_authorization_effect", "count_only_authorized",
        "research_outcomes_calculated", "outcome_fields", "stage_folder_id", "shards",
        "derived_qc",
    }
    if set(value) != expected_keys:
        raise VaultError("V2 year manifest key set mismatch")
    expected_sources = expected_year_source_count(mask, year)
    expected_partition = partition_for_year_v2(partitions, year)
    checks = (
        value.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-year-manifest-v2.0.0",
        value.get("status") == "YEAR_STAGED_PRIVATE_DRIVE_REDOWNLOAD_VERIFIED_UNSEALED",
        value.get("vault_version") == "v2",
        value.get("run_id") == run_id,
        value.get("run_attempt") == 1,
        value.get("head_sha") == head_sha,
        value.get("year") == year,
        value.get("partition_id") == expected_partition["id"],
        value.get("contract_sha256") == expected_contract_hashes,
        value.get("availability_mask_sha256") == expected_mask_sha256,
        value.get("base_source_object_count") == 2600,
        value.get("source_object_count") == expected_sources,
        value.get("known_missing_source_object_count") == 2600 - expected_sources,
        value.get("shard_count") == 50,
        isinstance(value.get("zstd_version"), str) and bool(value.get("zstd_version")),
        value.get("provider_schedule_claimed") is False,
        value.get("forward_fill_count") == 0,
        value.get("interpolation_count") == 0,
        value.get("formal_phase9_authorization_effect") is False,
        value.get("count_only_authorized") is False,
        value.get("research_outcomes_calculated") is False,
        value.get("outcome_fields") == [],
        value.get("stage_folder_id") == stage["id"],
    )
    if not all(checks):
        raise VaultError(f"V2 year {year} manifest state mismatch")
    shards = value.get("shards")
    if not isinstance(shards, list) or len(shards) != 50:
        raise VaultError("V2 year shard manifest count mismatch")
    if value.get("shards_sha256") != canonical_sha256(shards):
        raise VaultError("V2 year shard manifest SHA mismatch")
    derived_qc = value.get("derived_qc")
    if not isinstance(derived_qc, list) or len(derived_qc) != len(SYMBOLS_V2):
        raise VaultError("V2 derived QC record count mismatch")
    if [row.get("symbol") for row in derived_qc] != list(SYMBOLS_V2):
        raise VaultError("V2 derived QC symbol order mismatch")
    if value.get("derived_qc_sha256") != canonical_sha256(derived_qc):
        raise VaultError("V2 derived QC SHA mismatch")
    if value.get("batch6_compatibility_passed") != all(
        row.get("batch6_compatibility_passed") is True for row in derived_qc
    ):
        raise VaultError("V2 derived QC compatibility summary mismatch")
    for row in derived_qc:
        if (
            row.get("availability_mask_applied") is not True
            or row.get("provider_schedule_claimed") is not False
            or row.get("forward_fill_count") != 0
            or row.get("interpolation_count") != 0
        ):
            raise VaultError("V2 derived QC boundary mismatch")
        for timeframe in ("M5", "M15", "M30", "H1", "H4", "D1", "W1"):
            summary = row.get(timeframe)
            if not isinstance(summary, dict):
                raise VaultError("V2 derived QC timeframe missing")
            assert_hex64(summary.get("bucket_sha256", ""), f"V2 {year} derived {timeframe}")
    expected_shard_fields = set(manifest_schema["shard_identity_fields"]) | {
        "drive_file_id", "drive_parent_id"
    }
    expected_source_fields = set(manifest_schema["source_object_fields"])
    expected_order = [
        (symbol, periodicity)
        for symbol in SYMBOLS_V2
        for periodicity in DIRECT_PERIODICITIES_V2
    ]
    if [(row.get("symbol"), row.get("periodicity")) for row in shards] != expected_order:
        raise VaultError("V2 year shard order mismatch")
    drive_files = {
        row.get("id"): row for row in children if row.get("name") != "YEAR_MANIFEST.json"
    }
    if len(drive_files) != 50:
        raise VaultError("V2 staged shard count mismatch")
    for shard in shards:
        if set(shard) != expected_shard_fields:
            raise VaultError("V2 shard key set mismatch")
        if any(set(source) != expected_source_fields for source in shard["source_objects"]):
            raise VaultError("V2 source object key set mismatch")
        symbol = shard["symbol"]
        periodicity = shard["periodicity"]
        expected_present = list(present_weeks(mask, year, symbol, periodicity))
        expected_missing = list(known_missing_weeks(mask, year, symbol, periodicity))
        if (
            shard["vault_version"] != "v2"
            or shard["contract_sha256"] != expected_contract_hashes["fxcm_drive_vault_acquisition_v2.frozen.json"]
            or shard["partitions_sha256"] != expected_contract_hashes["fxcm_drive_vault_partitions_v2.frozen.json"]
            or shard["availability_mask_sha256"] != expected_mask_sha256
            or shard["run_id"] != run_id
            or shard["run_attempt"] != 1
            or shard["head_sha"] != head_sha
            or shard["year"] != year
            or shard["partition_id"] != expected_partition["id"]
            or shard["archive_name"] != f"fxcm-v2-{symbol}-{year}-{periodicity}.tar.zst"
            or shard["archive_bytes"] <= 0
            or shard["canonical_row_count"] <= 0
            or shard["observed_row_count"] <= 0
            or shard["usable_row_count"] <= 0
            or shard["canonical_row_count"] != shard["usable_row_count"]
            or shard["duplicate_count"] != 0
            or shard["field_schema"] != manifest_schema["canonical_csv"]["header"]
            or shard["volume_status"] not in ("PRESENT", "ABSENT_FROM_SOURCE_SCHEMA")
            or shard["qc_status"] not in ("PASS", "PASS_WITH_CROSSED_ROWS_QUARANTINED")
            or shard["drive_parent_role"] != "RUN_YEAR_STAGING"
            or shard["drive_parent_id"] != stage["id"]
        ):
            raise VaultError("V2 shard identity or QC boundary mismatch")
        assert_hex64(shard["archive_sha256"], "V2 archive")
        assert_hex64(shard["canonical_timestamp_sha256"], "V2 canonical timestamps")
        assert_hex64(shard["canonical_csv_sha256"], "V2 canonical CSV")
        assert_hex64(shard["crossed_quote_event_sha256"], "V2 crossed quote events")
        if (
            shard["base_week_count"] != 52
            or shard["present_week_indices"] != expected_present
            or shard["known_missing_week_indices"] != expected_missing
            or shard["source_object_count"] != len(expected_present)
            or [row["week_index"] for row in shard["source_objects"]] != expected_present
        ):
            raise VaultError("V2 shard availability mask mismatch")
        for source in shard["source_objects"]:
            if (
                source["url"] != source_url(contract, year, symbol, periodicity, source["week_index"])
                or source["http_status"] != 200
                or source["bytes"] <= 0
                or source["row_count"] <= 0
            ):
                raise VaultError("V2 source object evidence mismatch")
            assert_hex64(source["sha256"], "V2 source object")
        drive_row = drive_files.get(shard.get("drive_file_id"))
        if drive_row is None:
            raise VaultError("V2 Drive shard ID missing")
        drive_props = drive_row.get("appProperties") or {}
        if (
            drive_row.get("name") != shard.get("archive_name")
            or drive_row.get("parents") != [stage["id"]]
            or int(drive_row.get("size", -1)) != shard.get("archive_bytes")
            or drive_props.get("sha256") != shard.get("archive_sha256")
            or drive_props.get("state") != "UNSEALED"
            or shard.get("drive_upload_redownload_sha256_verified") is not True
        ):
            raise VaultError("V2 Drive staged shard metadata mismatch")
    if sum(row["source_object_count"] for row in shards) != expected_sources:
        raise VaultError("V2 manifest source count mismatch")
    return value, metadata


def finalize_v2(args: argparse.Namespace) -> dict[str, Any]:
    contract, partitions, manifest_schema, formal, mask = load_v2_contracts(
        args.acquisition_contract,
        args.partitions_contract,
        args.manifest_schema,
        args.formal_boundary,
        args.availability_mask,
    )
    require_v2_confirmations(
        contract,
        args.confirmation,
        args.scope_confirmation,
        args.usage_confirmation,
        args.formal_acknowledgement,
    )
    if args.run_attempt != 1:
        raise VaultError("only first V2 run attempt is authorized")
    if (
        args.work_dir.exists()
        or args.work_dir.is_symlink()
        or args.public_report_dir.exists()
        or args.public_report_dir.is_symlink()
    ):
        raise VaultError("V2 finalizer directories must be new")
    args.work_dir.mkdir(parents=True)
    args.public_report_dir.mkdir(parents=True)
    drive = GoogleDrivePrivate()
    drive.verify_root(contract["drive_custody"]["root_folder_name"])
    root_children = drive.list_children(ROOT_FOLDER_ID)
    expected_names = {
        f"v2-staging-run-{args.run_id}-year-{year}" for year in YEARS_V2
    }
    if (
        {row.get("name") for row in root_children} != expected_names
        or len(root_children) != len(YEARS_V2)
    ):
        raise VaultError("Drive root must contain exactly 14 current V2 staging folders")
    stages = {int(row["name"].rsplit("-", 1)[1]): row for row in root_children}
    if set(stages) != set(YEARS_V2) or any(
        row.get("mimeType") != FOLDER_MIME for row in stages.values()
    ):
        raise VaultError("V2 year staging folder set mismatch")
    expected_contract_hashes = contract_sha_bundle((
        args.acquisition_contract,
        args.partitions_contract,
        args.manifest_schema,
        args.formal_boundary,
        args.availability_mask,
    ))
    mask_sha = expected_contract_hashes[args.availability_mask.name]
    year_data = {
        year: read_year_manifest_v2(
            drive,
            stages[year],
            year,
            args.run_id,
            args.head_sha,
            args.work_dir,
            manifest_schema,
            contract,
            partitions,
            mask,
            expected_contract_hashes,
            mask_sha,
        )
        for year in YEARS_V2
    }
    tree = create_tree_v2(drive, args.run_id)
    destination_symbol_folders: dict[tuple[int, str], str] = {}
    year_manifest_folders: dict[int, str] = {}
    for year in YEARS_V2:
        partition = partition_for_year_v2(partitions, year)
        parent = tree["prices"] if partition["id"] == "DEVELOPMENT" else tree[partition["id"]]
        year_folder = drive.create_folder_new(
            parent["id"],
            str(year),
            {"vault_version": "v2", "year": str(year), "partition": partition["id"]},
        )
        for symbol in SYMBOLS_V2:
            symbol_folder = drive.create_folder_new(
                year_folder["id"],
                symbol,
                {
                    "vault_version": "v2",
                    "year": str(year),
                    "symbol": symbol,
                    "partition": partition["id"],
                },
            )
            destination_symbol_folders[(year, symbol)] = symbol_folder["id"]
        year_manifest_folder = drive.create_folder_new(
            tree["years_manifest"]["id"],
            str(year),
            {"vault_version": "v2", "year": str(year), "role": "YEAR_MANIFEST"},
        )
        year_manifest_folders[year] = year_manifest_folder["id"]
    all_shards: list[dict[str, Any]] = []
    year_summaries: list[dict[str, Any]] = []
    for year in YEARS_V2:
        manifest, manifest_metadata = year_data[year]
        partition = partition_for_year_v2(partitions, year)
        for shard in manifest["shards"]:
            destination_id = destination_symbol_folders[(year, shard["symbol"])]
            drive.move_file(
                shard["drive_file_id"],
                stages[year]["id"],
                destination_id,
                {
                    "vault_version": "v2",
                    "run_id": args.run_id,
                    "year": str(year),
                    "symbol": shard["symbol"],
                    "periodicity": shard["periodicity"],
                    "sha256": shard["archive_sha256"],
                    "partition": partition["id"],
                    "state": "SEALED",
                },
            )
            copy = dict(shard)
            copy["drive_parent_id"] = destination_id
            copy["drive_parent_role"] = partition["storage_namespace"]
            all_shards.append(copy)
        drive.move_file(
            manifest_metadata["id"],
            stages[year]["id"],
            year_manifest_folders[year],
            {
                "vault_version": "v2",
                "run_id": args.run_id,
                "year": str(year),
                "state": "SEALED_YEAR_MANIFEST",
            },
        )
        drive.move_file(
            stages[year]["id"],
            ROOT_FOLDER_ID,
            tree["staging"]["id"],
            {
                "vault_version": "v2",
                "run_id": args.run_id,
                "year": str(year),
                "state": "EMPTY_COMPLETED_STAGE",
            },
        )
        year_summaries.append({
            "year": year,
            "partition_id": partition["id"],
            "shard_count": 50,
            "source_object_count": manifest["source_object_count"],
            "known_missing_source_object_count": manifest["known_missing_source_object_count"],
            "shards_sha256": manifest["shards_sha256"],
            "derived_qc_sha256": manifest["derived_qc_sha256"],
            "batch6_compatibility_passed": manifest["batch6_compatibility_passed"],
        })
    if len(all_shards) != 700:
        raise VaultError("V2 final vault shard count mismatch")
    if sum(row["source_object_count"] for row in all_shards) != PRESENT_SOURCE_OBJECT_COUNT_V2:
        raise VaultError("V2 final source count mismatch")
    vault_manifest = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-manifest-v2.0.0",
        "status": "SEALED_PRIVATE_DRIVE_CUSTODY",
        "vault_version": "v2",
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "head_sha": args.head_sha,
        "contract_sha256": expected_contract_hashes,
        "availability_mask_sha256": mask_sha,
        "year_count": 14,
        "symbol_count": 25,
        "direct_periodicity_count": 2,
        "shard_count": 700,
        "base_source_object_count": 36400,
        "source_object_count": PRESENT_SOURCE_OBJECT_COUNT_V2,
        "known_missing_source_object_count": KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2,
        "partition_years": {
            row["id"]: row["years"] for row in partitions["partitions"]
        },
        "shards_sha256": canonical_sha256(all_shards),
        "year_summaries": year_summaries,
        "shards": all_shards,
        "formal_phase9_authorization_effect": False,
        "count_only_authorized": False,
        "batch6_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }
    source_objects = [
        {
            "year": shard["year"],
            "symbol": shard["symbol"],
            "periodicity": shard["periodicity"],
            **{
                key: source[key]
                for key in ("week_index", "url", "http_status", "bytes", "sha256", "row_count")
            },
        }
        for shard in all_shards
        for source in shard["source_objects"]
    ]
    source_inventory = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-source-inventory-v2.0.0",
        "vault_version": "v2",
        "run_id": args.run_id,
        "source_object_count": PRESENT_SOURCE_OBJECT_COUNT_V2,
        "known_missing_source_object_count": KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2,
        "availability_mask_sha256": mask_sha,
        "source_identity_sha256": canonical_sha256(source_objects),
        "source_objects": source_objects,
        "provider_release_identity": contract["provider"]["release_identity"],
        "provider_schedule_claimed": False,
    }
    qc_summary = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-qc-summary-v2.0.0",
        "vault_version": "v2",
        "run_id": args.run_id,
        "year_count": 14,
        "shard_count": 700,
        "source_object_count": PRESENT_SOURCE_OBJECT_COUNT_V2,
        "known_missing_source_object_count": KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2,
        "observed_row_count": sum(row["observed_row_count"] for row in all_shards),
        "usable_row_count": sum(row["usable_row_count"] for row in all_shards),
        "crossed_quote_count": sum(row["crossed_quote_count"] for row in all_shards),
        "duplicate_count": sum(row["duplicate_count"] for row in all_shards),
        "forward_fill_count": 0,
        "interpolation_count": 0,
        "all_uploads_redownload_sha256_verified": all(
            row["drive_upload_redownload_sha256_verified"] for row in all_shards
        ),
        "batch6_compatibility_passed": all(
            row["batch6_compatibility_passed"]
            for row in year_summaries
            if row["year"] in (2017, 2018)
        ),
        "full_provider_schedule_qc_claimed": False,
        "vault_custody_qc_passed": True,
    }
    custody = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-custody-v2.0.0",
        "vault_version": "v2",
        "run_id": args.run_id,
        "root_folder_id": ROOT_FOLDER_ID,
        "exact_file_id_parent_id_required": True,
        "duplicate_names_allowed": False,
        "availability_mask_sha256": mask_sha,
        "vault_manifest_sha256": canonical_sha256(vault_manifest),
        "source_inventory_sha256": canonical_sha256(source_inventory),
        "qc_summary_sha256": canonical_sha256(qc_summary),
        "seal_written_last": True,
    }
    _, source_sha = upload_and_verify_json(
        drive, tree["manifest"]["id"], args.work_dir, "source_inventory.json",
        source_inventory, {"role": "SOURCE_INVENTORY", "vault_version": "v2"},
    )
    _, qc_sha = upload_and_verify_json(
        drive, tree["manifest"]["id"], args.work_dir, "qc_summary.json",
        qc_summary, {"role": "QC_SUMMARY", "vault_version": "v2"},
    )
    _, vault_sha = upload_and_verify_json(
        drive, tree["manifest"]["id"], args.work_dir, "vault_manifest.json",
        vault_manifest, {"role": "VAULT_MANIFEST", "vault_version": "v2"},
    )
    _, custody_sha = upload_and_verify_json(
        drive, tree["manifest"]["id"], args.work_dir, "drive_custody_manifest.json",
        custody, {"role": "CUSTODY_MANIFEST", "vault_version": "v2"},
    )
    digest_path = args.work_dir / "vault_manifest_sha256.txt"
    digest_path.write_text(f"{vault_sha}  vault_manifest.json\n", encoding="ascii")
    digest_upload = drive.upload_file_new(
        tree["manifest"]["id"],
        digest_path,
        digest_path.name,
        "text/plain",
        {
            "vault_version": "v2",
            "run_id": args.run_id,
            "role": "VAULT_MANIFEST_DIGEST",
            "sha256": sha256_file(digest_path),
        },
    )
    verified_digest = args.work_dir / "verified-vault_manifest_sha256.txt"
    drive.download_verify(
        digest_upload["id"],
        verified_digest,
        digest_path.stat().st_size,
        sha256_file(digest_path),
    )
    verified_digest.unlink()
    seal = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-seal-v2.0.0",
        "status": "SEALED_LAST_PRIVATE_DRIVE_OBJECT",
        "vault_version": "v2",
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "head_sha": args.head_sha,
        "year_count": 14,
        "shard_count": 700,
        "base_source_object_count": 36400,
        "source_object_count": PRESENT_SOURCE_OBJECT_COUNT_V2,
        "known_missing_source_object_count": KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2,
        "availability_mask_sha256": mask_sha,
        "source_inventory_sha256": source_sha,
        "qc_summary_sha256": qc_sha,
        "vault_manifest_sha256": vault_sha,
        "drive_custody_manifest_sha256": custody_sha,
        "formal_boundary_effect_if_executed": formal["v2_execution_effect"],
        "count_only_authorized": False,
        "batch6_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }
    _, seal_sha = upload_and_verify_json(
        drive,
        tree["manifest"]["id"],
        args.work_dir,
        "VAULT_SEAL.json",
        seal,
        {"role": "VAULT_SEAL_LAST", "vault_version": "v2"},
    )
    public_audit = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-price-free-audit-v2.0.0",
        "status": "PRIVATE_VAULT_SEALED_PRICE_FREE_PUBLIC_AUDIT",
        "vault_version": "v2",
        "run_id": args.run_id,
        "run_attempt": args.run_attempt,
        "head_sha": args.head_sha,
        "year_count": 14,
        "symbol_count": 25,
        "direct_periodicity_count": 2,
        "shard_count": 700,
        "base_source_object_count": 36400,
        "source_object_count": PRESENT_SOURCE_OBJECT_COUNT_V2,
        "known_missing_source_object_count": KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2,
        "availability_mask_sha256": mask_sha,
        "vault_manifest_sha256": vault_sha,
        "vault_seal_sha256": seal_sha,
        "all_uploads_redownload_sha256_verified": True,
        "batch6_compatibility_passed": qc_summary["batch6_compatibility_passed"],
        "full_provider_schedule_qc_claimed": False,
        "formal_phase9_authorization_effect": False,
        "count_only_authorized": False,
        "batch6_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "public_price_files": 0,
        "public_drive_identifiers": 0,
    }
    reject_prohibited_keys(public_audit)
    audit_path = args.public_report_dir / "VAULT_RUN_PRICE_FREE_AUDIT.json"
    write_canonical_json(audit_path, public_audit)
    (args.public_report_dir / "artifact_manifest_sha256.txt").write_text(
        f"{sha256_file(audit_path)}  {audit_path.name}\n", encoding="ascii"
    )
    validate_public_report_tree(args.public_report_dir)
    return public_audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-contract", type=Path, required=True)
    parser.add_argument("--partitions-contract", type=Path, required=True)
    parser.add_argument("--manifest-schema", type=Path, required=True)
    parser.add_argument("--formal-boundary", type=Path, required=True)
    parser.add_argument("--availability-mask", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--public-report-dir", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--scope-confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--formal-acknowledgement", required=True)
    args = parser.parse_args()
    runner_temp = os.environ.get("RUNNER_TEMP")
    expected_work = f"fxcm-vault-v2-finalize-{args.run_id}-{args.run_attempt}"
    expected_report = f"fxcm-vault-v2-public-report-{args.run_id}-{args.run_attempt}"
    if (
        not runner_temp
        or args.work_dir.parent.resolve() != Path(runner_temp).resolve()
        or args.work_dir.name != expected_work
    ):
        raise VaultError("V2 finalizer work directory outside ephemeral runner boundary")
    if (
        args.public_report_dir.parent.resolve() != Path(runner_temp).resolve()
        or args.public_report_dir.name != expected_report
    ):
        raise VaultError("V2 public report directory outside ephemeral runner boundary")
    try:
        result = finalize_v2(args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        if args.work_dir.exists() and not args.work_dir.is_symlink():
            shutil.rmtree(args.work_dir)


if __name__ == "__main__":
    raise SystemExit(main())
