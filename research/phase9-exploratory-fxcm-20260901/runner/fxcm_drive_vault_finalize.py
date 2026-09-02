#!/usr/bin/env python3
"""Promote 16 complete private Drive year stages and write the vault seal last."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from fxcm_drive_vault_common import (
    DIRECT_PERIODICITIES,
    ROOT_FOLDER_ID,
    SYMBOLS,
    YEARS,
    VaultError,
    canonical_sha256,
    contract_sha_bundle,
    load_frozen_contracts,
    load_json,
    partition_for_year,
    reject_prohibited_keys,
    require_exact_confirmations,
    sha256_file,
    validate_public_report_tree,
    write_canonical_json,
)
from fxcm_google_drive_private import FOLDER_MIME, GoogleDrivePrivate


def child_by_name(drive: GoogleDrivePrivate, parent_id: str, name: str, mime_type: str | None = None) -> dict:
    matches = [row for row in drive.list_children(parent_id) if row.get("name") == name]
    if len(matches) != 1:
        raise VaultError(f"Drive child not unique: {name}")
    if mime_type is not None and matches[0].get("mimeType") != mime_type:
        raise VaultError(f"Drive child MIME mismatch: {name}")
    return matches[0]


def create_tree(drive: GoogleDrivePrivate, run_id: str) -> dict[str, Any]:
    v1 = drive.create_folder_new(ROOT_FOLDER_ID, "v1", {"vault_version": "v1", "run_id": run_id, "state": "PROMOTING"})
    manifest = drive.create_folder_new(v1["id"], "manifest", {"vault_version": "v1", "role": "MANIFEST"})
    years_manifest = drive.create_folder_new(manifest["id"], "years", {"vault_version": "v1", "role": "YEAR_MANIFESTS"})
    prices = drive.create_folder_new(v1["id"], "prices", {"vault_version": "v1", "partition": "DEVELOPMENT"})
    sealed = drive.create_folder_new(v1["id"], "sealed", {"vault_version": "v1", "role": "SEALED"})
    oos = drive.create_folder_new(sealed["id"], "oos", {"vault_version": "v1", "partition": "STRICT_OOS"})
    robustness = drive.create_folder_new(sealed["id"], "robustness", {"vault_version": "v1", "partition": "ROBUSTNESS"})
    final_holdout = drive.create_folder_new(sealed["id"], "final_holdout", {"vault_version": "v1", "partition": "FINAL_HOLDOUT"})
    staging = drive.create_folder_new(v1["id"], "staging", {"vault_version": "v1", "role": "COMPLETED_EMPTY_STAGES"})
    return {
        "v1": v1, "manifest": manifest, "years_manifest": years_manifest, "prices": prices,
        "STRICT_OOS": oos, "ROBUSTNESS": robustness, "FINAL_HOLDOUT": final_holdout, "staging": staging,
    }


def read_year_manifest(
    drive: GoogleDrivePrivate, stage: dict, year: int, run_id: str, head_sha: str, temp_dir: Path,
    manifest_schema: dict,
) -> tuple[dict, dict, list[dict]]:
    children = drive.list_children(stage["id"])
    if len(children) != 85:
        raise VaultError(f"year {year} staging file count mismatch")
    manifest_rows = [row for row in children if row.get("name") == "YEAR_MANIFEST.json"]
    if len(manifest_rows) != 1:
        raise VaultError("year manifest not unique")
    metadata = manifest_rows[0]
    props = metadata.get("appProperties") or {}
    expected_sha = props.get("sha256", "")
    expected_size = int(metadata.get("size", -1))
    destination = temp_dir / f"year-{year}-manifest.json"
    drive.download_verify(metadata["id"], destination, expected_size, expected_sha)
    value = load_json(destination)
    reject_prohibited_keys(value)
    expected_year_keys = {
        "schema_version", "status", "vault_version", "run_id", "run_attempt", "head_sha", "year",
        "partition_id", "contract_sha256", "source_object_count", "shard_count", "zstd_version",
        "shards_sha256", "derived_qc_sha256", "batch6_compatibility_passed",
        "provider_schedule_claimed", "forward_fill_count", "interpolation_count",
        "formal_phase9_authorization_effect", "count_only_authorized", "research_outcomes_calculated",
        "outcome_fields", "stage_folder_id", "shards", "derived_qc",
    }
    if set(value) != expected_year_keys:
        raise VaultError("year manifest key set mismatch")
    checks = (
        value.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-year-manifest-v1.0.0",
        value.get("status") == "YEAR_STAGED_PRIVATE_DRIVE_REDOWNLOAD_VERIFIED_UNSEALED",
        value.get("vault_version") == "v1",
        value.get("run_id") == run_id,
        value.get("run_attempt") == 1,
        value.get("head_sha") == head_sha,
        value.get("year") == year,
        value.get("source_object_count") == 4368,
        value.get("shard_count") == 84,
        value.get("forward_fill_count") == 0,
        value.get("interpolation_count") == 0,
        value.get("formal_phase9_authorization_effect") is False,
        value.get("count_only_authorized") is False,
        value.get("research_outcomes_calculated") is False,
        value.get("outcome_fields") == [],
        value.get("stage_folder_id") == stage["id"],
    )
    if not all(checks):
        raise VaultError(f"year {year} manifest state mismatch")
    shards = value.get("shards")
    if not isinstance(shards, list) or len(shards) != 84:
        raise VaultError("year shard manifest count mismatch")
    expected_shard_keys = set(manifest_schema["shard_identity_fields"]) | {"drive_file_id", "drive_parent_id"}
    expected_source_keys = set(manifest_schema["source_object_fields"])
    for shard in shards:
        if set(shard) != expected_shard_keys:
            raise VaultError("year shard key set mismatch")
        if any(set(source) != expected_source_keys for source in shard["source_objects"]):
            raise VaultError("source object key set mismatch")
    keys = [(row.get("symbol"), row.get("periodicity")) for row in shards]
    expected = [(symbol, periodicity) for symbol in SYMBOLS for periodicity in DIRECT_PERIODICITIES]
    if keys != expected or len(keys) != len(set(keys)):
        raise VaultError("year shard order or uniqueness mismatch")
    drive_files = {row.get("id"): row for row in children if row.get("name") != "YEAR_MANIFEST.json"}
    if len(drive_files) != 84:
        raise VaultError("Drive staged shard identity count mismatch")
    for shard in shards:
        drive_row = drive_files.get(shard.get("drive_file_id"))
        if drive_row is None:
            raise VaultError("Drive shard ID missing from staging")
        props = drive_row.get("appProperties") or {}
        if drive_row.get("name") != shard.get("archive_name"):
            raise VaultError("Drive shard name mismatch")
        if drive_row.get("parents") != [stage["id"]]:
            raise VaultError("Drive shard parent escape")
        if int(drive_row.get("size", -1)) != shard.get("archive_bytes"):
            raise VaultError("Drive shard size mismatch")
        if props.get("sha256") != shard.get("archive_sha256") or props.get("state") != "UNSEALED":
            raise VaultError("Drive shard appProperties mismatch")
        if shard.get("drive_upload_redownload_sha256_verified") is not True:
            raise VaultError("Drive shard lacks upload redownload verification")
    return value, metadata, children


def upload_and_verify_json(
    drive: GoogleDrivePrivate, parent_id: str, work_dir: Path, name: str, value: dict, app_properties: dict[str, str]
) -> tuple[dict, str]:
    path = work_dir / name
    write_canonical_json(path, value)
    digest = sha256_file(path)
    uploaded = drive.upload_file_new(
        parent_id, path, name, "application/json", {**app_properties, "sha256": digest}
    )
    verified = work_dir / f"verified-{name}"
    drive.download_verify(uploaded["id"], verified, path.stat().st_size, digest)
    verified.unlink()
    return uploaded, digest


def finalize(args: argparse.Namespace) -> dict:
    contract, partitions, manifest_schema, formal = load_frozen_contracts(
        args.acquisition_contract, args.partitions_contract, args.manifest_schema, args.formal_boundary
    )
    require_exact_confirmations(
        contract, args.confirmation, args.usage_confirmation, args.formal_acknowledgement, "acquisition"
    )
    if args.run_attempt != 1:
        raise VaultError("only first run attempt is authorized")
    if args.work_dir.exists() or args.work_dir.is_symlink() or args.public_report_dir.exists() or args.public_report_dir.is_symlink():
        raise VaultError("finalizer output directories must not exist")
    args.work_dir.mkdir(parents=True)
    args.public_report_dir.mkdir(parents=True)
    drive = GoogleDrivePrivate()
    drive.verify_root(contract["drive_custody"]["root_folder_name"])
    root_children = drive.list_children(ROOT_FOLDER_ID)
    expected_stage_names = {f"v1-staging-run-{args.run_id}-year-{year}" for year in YEARS}
    actual_names = {row.get("name") for row in root_children}
    if actual_names != expected_stage_names or len(root_children) != 16:
        raise VaultError("Drive root must contain exactly the 16 current-run staging folders")
    stages = {int(row["name"].rsplit("-", 1)[1]): row for row in root_children}
    if set(stages) != set(YEARS) or any(row.get("mimeType") != FOLDER_MIME for row in stages.values()):
        raise VaultError("Drive year staging folder set mismatch")
    year_data = {}
    for year in YEARS:
        year_data[year] = read_year_manifest(
            drive, stages[year], year, args.run_id, args.head_sha, args.work_dir, manifest_schema
        )
    tree = create_tree(drive, args.run_id)
    destination_symbol_folders: dict[tuple[int, str], str] = {}
    year_manifest_folders: dict[int, str] = {}
    for year in YEARS:
        partition = partition_for_year(partitions, year)
        parent = tree["prices"] if partition["id"] == "DEVELOPMENT" else tree[partition["id"]]
        year_folder = drive.create_folder_new(parent["id"], str(year), {
            "vault_version": "v1", "year": str(year), "partition": partition["id"]
        })
        for symbol in SYMBOLS:
            symbol_folder = drive.create_folder_new(year_folder["id"], symbol, {
                "vault_version": "v1", "year": str(year), "symbol": symbol, "partition": partition["id"]
            })
            destination_symbol_folders[(year, symbol)] = symbol_folder["id"]
        year_manifest_folder = drive.create_folder_new(tree["years_manifest"]["id"], str(year), {
            "vault_version": "v1", "year": str(year), "role": "YEAR_MANIFEST"
        })
        year_manifest_folders[year] = year_manifest_folder["id"]
    all_shards: list[dict] = []
    year_summaries: list[dict] = []
    for year in YEARS:
        manifest, manifest_metadata, _ = year_data[year]
        partition = partition_for_year(partitions, year)
        for shard in manifest["shards"]:
            new_props = {
                "vault_version": "v1", "run_id": args.run_id, "year": str(year),
                "symbol": shard["symbol"], "periodicity": shard["periodicity"],
                "sha256": shard["archive_sha256"], "partition": partition["id"], "state": "SEALED",
            }
            destination_id = destination_symbol_folders[(year, shard["symbol"])]
            drive.move_file(shard["drive_file_id"], stages[year]["id"], destination_id, new_props)
            shard_copy = dict(shard)
            shard_copy["drive_parent_id"] = destination_id
            shard_copy["drive_parent_role"] = partition["storage_namespace"]
            all_shards.append(shard_copy)
        drive.move_file(
            manifest_metadata["id"], stages[year]["id"], year_manifest_folders[year],
            {"vault_version": "v1", "run_id": args.run_id, "year": str(year), "state": "SEALED_YEAR_MANIFEST"},
        )
        drive.move_file(
            stages[year]["id"], ROOT_FOLDER_ID, tree["staging"]["id"],
            {"vault_version": "v1", "run_id": args.run_id, "year": str(year), "state": "EMPTY_COMPLETED_STAGE"},
        )
        year_summaries.append({
            "year": year, "partition_id": partition["id"], "shard_count": 84,
            "source_object_count": 4368, "shards_sha256": manifest["shards_sha256"],
            "derived_qc_sha256": manifest["derived_qc_sha256"],
            "batch6_compatibility_passed": manifest["batch6_compatibility_passed"],
        })
    if len(all_shards) != 1344:
        raise VaultError("final vault shard count mismatch")
    vault_manifest = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-manifest-v1.0.0",
        "status": "SEALED_PRIVATE_DRIVE_CUSTODY",
        "vault_version": "v1", "run_id": args.run_id, "run_attempt": args.run_attempt, "head_sha": args.head_sha,
        "contract_sha256": contract_sha_bundle((
            args.acquisition_contract, args.partitions_contract, args.manifest_schema, args.formal_boundary
        )),
        "year_count": 16, "symbol_count": 28, "direct_periodicity_count": 3,
        "shard_count": 1344, "source_object_count": 69888,
        "partition_years": {item["id"]: item["years"] for item in partitions["partitions"]},
        "shards_sha256": canonical_sha256(all_shards), "year_summaries": year_summaries,
        "shards": all_shards,
        "formal_phase9_authorization_effect": False, "count_only_authorized": False,
        "batch6_authorized": False, "research_outcomes_calculated": False, "outcome_fields": [],
    }
    source_objects = [
        {"year": shard["year"], "symbol": shard["symbol"], "periodicity": shard["periodicity"], **{
            key: source[key] for key in ("week_index", "url", "http_status", "bytes", "sha256", "row_count")
        }}
        for shard in all_shards for source in shard["source_objects"]
    ]
    source_inventory = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-source-inventory-v1.0.0",
        "vault_version": "v1", "run_id": args.run_id, "source_object_count": 69888,
        "source_identity_sha256": canonical_sha256(source_objects),
        "source_objects": source_objects,
        "provider_release_identity": contract["provider"]["release_identity"],
        "provider_schedule_claimed": False,
    }
    qc_summary = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-qc-summary-v1.0.0",
        "vault_version": "v1", "run_id": args.run_id,
        "year_count": 16, "shard_count": 1344,
        "observed_row_count": sum(row["observed_row_count"] for row in all_shards),
        "usable_row_count": sum(row["usable_row_count"] for row in all_shards),
        "crossed_quote_count": sum(row["crossed_quote_count"] for row in all_shards),
        "duplicate_count": sum(row["duplicate_count"] for row in all_shards),
        "forward_fill_count": 0, "interpolation_count": 0,
        "all_uploads_redownload_sha256_verified": all(row["drive_upload_redownload_sha256_verified"] for row in all_shards),
        "batch6_compatibility_passed": all(row["batch6_compatibility_passed"] for row in year_summaries if row["year"] in (2017, 2018)),
        "full_provider_schedule_qc_claimed": False,
        "vault_custody_qc_passed": True,
    }
    custody = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-custody-v1.0.0",
        "vault_version": "v1", "run_id": args.run_id, "root_folder_id": ROOT_FOLDER_ID,
        "exact_file_id_parent_id_required": True, "duplicate_names_allowed": False,
        "vault_manifest_sha256": canonical_sha256(vault_manifest),
        "source_inventory_sha256": canonical_sha256(source_inventory),
        "qc_summary_sha256": canonical_sha256(qc_summary),
        "seal_written_last": True,
    }
    _, source_sha = upload_and_verify_json(drive, tree["manifest"]["id"], args.work_dir, "source_inventory.json", source_inventory, {"role": "SOURCE_INVENTORY"})
    _, qc_sha = upload_and_verify_json(drive, tree["manifest"]["id"], args.work_dir, "qc_summary.json", qc_summary, {"role": "QC_SUMMARY"})
    _, vault_sha = upload_and_verify_json(drive, tree["manifest"]["id"], args.work_dir, "vault_manifest.json", vault_manifest, {"role": "VAULT_MANIFEST"})
    _, custody_sha = upload_and_verify_json(drive, tree["manifest"]["id"], args.work_dir, "drive_custody_manifest.json", custody, {"role": "CUSTODY_MANIFEST"})
    digest_path = args.work_dir / "vault_manifest_sha256.txt"
    digest_path.write_text(f"{vault_sha}  vault_manifest.json\n", encoding="ascii")
    digest_upload = drive.upload_file_new(
        tree["manifest"]["id"], digest_path, digest_path.name, "text/plain",
        {"vault_version": "v1", "run_id": args.run_id, "role": "VAULT_MANIFEST_DIGEST", "sha256": sha256_file(digest_path)},
    )
    verified_digest = args.work_dir / "verified-vault_manifest_sha256.txt"
    drive.download_verify(digest_upload["id"], verified_digest, digest_path.stat().st_size, sha256_file(digest_path))
    verified_digest.unlink()
    seal = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-seal-v1.0.0",
        "status": "SEALED_LAST_PRIVATE_DRIVE_OBJECT",
        "vault_version": "v1", "run_id": args.run_id, "run_attempt": args.run_attempt, "head_sha": args.head_sha,
        "year_count": 16, "shard_count": 1344, "source_object_count": 69888,
        "source_inventory_sha256": source_sha, "qc_summary_sha256": qc_sha,
        "vault_manifest_sha256": vault_sha, "drive_custody_manifest_sha256": custody_sha,
        "formal_boundary_effect_if_executed": formal["formal_split_effect_if_executed"],
        "count_only_authorized": False, "batch6_authorized": False,
        "research_outcomes_calculated": False, "outcome_fields": [],
    }
    _, seal_sha = upload_and_verify_json(drive, tree["manifest"]["id"], args.work_dir, "VAULT_SEAL.json", seal, {"role": "VAULT_SEAL_LAST"})
    public_audit = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-price-free-audit-v1.0.0",
        "status": "PRIVATE_VAULT_SEALED_PRICE_FREE_PUBLIC_AUDIT",
        "vault_version": "v1", "run_id": args.run_id, "run_attempt": args.run_attempt, "head_sha": args.head_sha,
        "year_count": 16, "symbol_count": 28, "direct_periodicity_count": 3,
        "shard_count": 1344, "source_object_count": 69888,
        "vault_manifest_sha256": vault_sha, "vault_seal_sha256": seal_sha,
        "all_uploads_redownload_sha256_verified": True,
        "batch6_compatibility_passed": qc_summary["batch6_compatibility_passed"],
        "full_provider_schedule_qc_claimed": False,
        "formal_phase9_authorization_effect": False,
        "count_only_authorized": False, "batch6_authorized": False,
        "research_outcomes_calculated": False, "outcome_fields": [],
        "public_price_files": 0, "public_drive_identifiers": 0,
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
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--public-report-dir", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--formal-acknowledgement", required=True)
    args = parser.parse_args()
    runner_temp = os.environ.get("RUNNER_TEMP")
    expected_work = f"fxcm-vault-finalize-{args.run_id}-{args.run_attempt}"
    expected_report = f"fxcm-vault-public-report-{args.run_id}-{args.run_attempt}"
    if not runner_temp or args.work_dir.parent.resolve() != Path(runner_temp).resolve() or args.work_dir.name != expected_work:
        raise VaultError("finalizer work directory is outside the exact ephemeral runner boundary")
    if args.public_report_dir.parent.resolve() != Path(runner_temp).resolve() or args.public_report_dir.name != expected_report:
        raise VaultError("public report directory is outside the exact ephemeral runner boundary")
    try:
        result = finalize(args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        if args.work_dir.exists() and not args.work_dir.is_symlink():
            shutil.rmtree(args.work_dir)


if __name__ == "__main__":
    raise SystemExit(main())
