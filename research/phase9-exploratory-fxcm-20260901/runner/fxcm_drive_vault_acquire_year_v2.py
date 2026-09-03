#!/usr/bin/env python3
"""Acquire one frozen V2 FXCM year and stage it in private Google Drive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fxcm_drive_vault_acquire_year import (
    Aggregate,
    RejectRedirects,
    aggregate_tuple,
    bucket_start,
    iter_canonical,
    make_archive,
    process_direct_shard,
    row_tuple,
)
from fxcm_drive_vault_common import (
    canonical_sha256,
    contract_sha_bundle,
    iso_utc,
    sha256_file,
    write_canonical_json,
    VaultError,
)
from fxcm_drive_vault_v2_common import (
    DIRECT_PERIODICITIES_V2,
    OPERATIONAL_VERSION_V2_1,
    SYMBOLS_V2,
    WEEKS_V2,
    YEARS_V2,
    expected_year_source_count,
    known_missing_weeks,
    load_v2_1_operational_amendment,
    load_v2_contracts,
    partition_for_year_v2,
    present_weeks,
    require_v2_1_confirmations,
)
from fxcm_google_drive_private import FOLDER_MIME, GoogleDrivePrivate


UTC = timezone.utc
FINE_TIMEFRAMES = ("M5", "M15", "M30", "H1")
FINE_EXPECTED_M1 = {"M5": 5, "M15": 15, "M30": 30, "H1": 60}
HIGH_TIMEFRAMES = ("H4", "D1", "W1")


def combine_h1_components(start: datetime, components: list[Aggregate]) -> Aggregate:
    if not components:
        raise VaultError("cannot combine empty H1 component list")
    first = components[0]
    combined = Aggregate(
        start=start,
        first_timestamp=first.first_timestamp,
        last_timestamp=components[-1].last_timestamp,
        count=sum(row.count for row in components),
        bid=list(first.bid),
        ask=list(first.ask),
        volume=first.volume,
        all_volume_present=all(row.all_volume_present for row in components),
    )
    for row in components[1:]:
        combined.bid[1] = max(combined.bid[1], row.bid[1])
        combined.bid[2] = min(combined.bid[2], row.bid[2])
        combined.bid[3] = row.bid[3]
        combined.ask[1] = max(combined.ask[1], row.ask[1])
        combined.ask[2] = min(combined.ask[2], row.ask[2])
        combined.ask[3] = row.ask[3]
        if combined.volume is None or row.volume is None:
            combined.volume = None
            combined.all_volume_present = False
        else:
            combined.volume += row.volume
    return combined


def derive_qc_v2(m1_path: Path, h1_path: Path, year: int) -> dict[str, Any]:
    """Derive exact UTC buckets; direct H1 is the only completeness reference."""
    references = {row.timestamp: row_tuple(row) for row in iter_canonical(h1_path)}
    fine: dict[str, dict[str, Any]] = {
        timeframe: {
            "candidate_bucket_count": 0,
            "complete_bucket_count": 0,
            "dropped_bucket_count": 0,
            "bucket_sha256": hashlib.sha256(),
        }
        for timeframe in FINE_TIMEFRAMES
    }
    active: dict[str, Aggregate] = {}
    complete_h1: dict[datetime, Aggregate] = {}

    def finish_fine(timeframe: str, aggregate: Aggregate) -> None:
        summary = fine[timeframe]
        summary["candidate_bucket_count"] += 1
        expected = FINE_EXPECTED_M1[timeframe]
        complete = (
            aggregate.count == expected
            and aggregate.last_timestamp - aggregate.first_timestamp == timedelta(minutes=expected - 1)
        )
        if not complete:
            summary["dropped_bucket_count"] += 1
            return
        summary["complete_bucket_count"] += 1
        values = aggregate_tuple(aggregate)
        line = iso_utc(aggregate.start) + "," + ",".join(format(value, "f") for value in values) + "\n"
        summary["bucket_sha256"].update(line.encode("ascii"))
        if timeframe == "H1":
            complete_h1[aggregate.start] = aggregate

    for row in iter_canonical(m1_path):
        for timeframe in FINE_TIMEFRAMES:
            start = bucket_start(row.timestamp, timeframe)
            current = active.get(timeframe)
            if current is None:
                active[timeframe] = Aggregate.from_row(start, row)
            elif current.start == start:
                current.add(row)
            else:
                finish_fine(timeframe, current)
                active[timeframe] = Aggregate.from_row(start, row)
    for timeframe, aggregate in active.items():
        finish_fine(timeframe, aggregate)

    derived_keys = set(complete_h1)
    reference_keys = set(references)
    exact_h1: dict[datetime, Aggregate] = {}
    mismatch = 0
    for timestamp in sorted(derived_keys & reference_keys):
        aggregate = complete_h1[timestamp]
        if aggregate_tuple(aggregate) == references[timestamp]:
            exact_h1[timestamp] = aggregate
        else:
            mismatch += 1
    fine["H1"].update({
        "derived_timestamp_missing_for_reference_count": len(reference_keys - derived_keys),
        "direct_reference_missing_for_derived_count": len(derived_keys - reference_keys),
        "reference_exact_match_count": len(exact_h1),
        "reference_ohlc_mismatch_count": mismatch,
        "direct_reference_timestamp_count": len(reference_keys),
    })

    high: dict[str, dict[str, Any]] = {}
    year_start = datetime(year, 1, 1, tzinfo=UTC)
    year_end = datetime(year + 1, 1, 1, tzinfo=UTC)
    for timeframe in HIGH_TIMEFRAMES:
        groups: dict[datetime, list[datetime]] = {}
        for timestamp in reference_keys:
            groups.setdefault(bucket_start(timestamp, timeframe), []).append(timestamp)
        digest = hashlib.sha256()
        complete_count = dropped_count = boundary_drop_count = component_count = 0
        for start, timestamps in sorted(groups.items()):
            if timeframe == "W1" and not (year_start <= start and start + timedelta(days=7) <= year_end):
                boundary_drop_count += 1
                dropped_count += 1
                continue
            ordered = sorted(timestamps)
            components = [exact_h1.get(timestamp) for timestamp in ordered]
            if not components or any(component is None for component in components):
                dropped_count += 1
                continue
            typed = [component for component in components if component is not None]
            combined = combine_h1_components(start, typed)
            values = aggregate_tuple(combined)
            digest.update(
                (iso_utc(start) + "," + ",".join(format(value, "f") for value in values) + "\n").encode("ascii")
            )
            complete_count += 1
            component_count += len(typed)
        high[timeframe] = {
            "candidate_bucket_count": len(groups),
            "complete_bucket_count": complete_count,
            "dropped_bucket_count": dropped_count,
            "outer_year_boundary_drop_count": boundary_drop_count if timeframe == "W1" else 0,
            "exact_h1_component_count": component_count,
            "bucket_sha256": digest.hexdigest(),
            "completeness_reference": "DIRECT_H1_TIMESTAMP_SET",
        }
    result = {
        timeframe: {
            key: value.hexdigest() if hasattr(value, "hexdigest") else value
            for key, value in summary.items()
        }
        for timeframe, summary in fine.items()
    }
    result.update(high)
    result["availability_mask_applied"] = True
    result["provider_schedule_claimed"] = False
    result["forward_fill_count"] = 0
    result["interpolation_count"] = 0
    # This only compares current M1-derived H1 with current direct H1.  It is
    # not the separately preregistered 64-series Batch 6 compatibility gate.
    result["batch6_compatibility_passed"] = False
    return result


def acquire_year_v2(args: argparse.Namespace) -> dict[str, Any]:
    frozen_paths = (
        args.acquisition_contract,
        args.partitions_contract,
        args.manifest_schema,
        args.formal_boundary,
        args.availability_mask,
    )
    contract, partitions, _, _, mask = load_v2_contracts(*frozen_paths)
    amendment = load_v2_1_operational_amendment(
        args.operational_amendment, frozen_paths
    )
    require_v2_1_confirmations(
        amendment,
        args.confirmation,
        args.scope_confirmation,
        args.usage_confirmation,
        args.formal_acknowledgement,
    )
    if args.year not in YEARS_V2:
        raise VaultError("year outside frozen V2 scope")
    if args.run_attempt != 1:
        raise VaultError("only first V2 run attempt is authorized")
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise VaultError("V2 work directory must not exist")
    args.work_dir.mkdir(parents=True)
    drive = GoogleDrivePrivate()
    drive.verify_private_root(
        contract["drive_custody"]["root_folder_name"],
        contract["drive_custody"]["root_folder_id"],
    )
    amendment_sha = sha256_file(args.operational_amendment)
    transaction_name = amendment["transactional_publication"]["transaction_name_template"].format(
        run_id=args.run_id
    )
    transaction_properties = {
        "vault_version": "v2",
        "operational_version": OPERATIONAL_VERSION_V2_1,
        "run_id": str(args.run_id),
        "head_sha": args.head_sha,
        "state": amendment["transactional_publication"]["transaction_initial_state"],
        "amendment_sha256": amendment_sha,
    }
    root_children = drive.list_children(contract["drive_custody"]["root_folder_id"])
    if (
        len(root_children) != 1
        or root_children[0].get("name") != transaction_name
        or root_children[0].get("mimeType") != FOLDER_MIME
        or root_children[0].get("appProperties") != transaction_properties
    ):
        raise VaultError("V2.1 transaction identity mismatch before price access")
    transaction = root_children[0]
    partition = partition_for_year_v2(partitions, args.year)
    stage_name = f"v2-staging-run-{args.run_id}-year-{args.year}"
    stage = drive.create_folder_new(
        transaction["id"],
        stage_name,
        {
            "vault_version": "v2",
            "operational_version": OPERATIONAL_VERSION_V2_1,
            "run_id": str(args.run_id),
            "head_sha": args.head_sha,
            "year": str(args.year),
            "state": "UNSEALED",
        },
    )
    opener = urllib.request.build_opener(RejectRedirects())
    contract_hashes = contract_sha_bundle((
        args.acquisition_contract,
        args.partitions_contract,
        args.manifest_schema,
        args.formal_boundary,
        args.availability_mask,
        args.operational_amendment,
    ))
    mask_sha = contract_hashes[args.availability_mask.name]
    shard_records: list[dict[str, Any]] = []
    derived_records: list[dict[str, Any]] = []
    zstd_version = subprocess.run(
        ["zstd", "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    for symbol in SYMBOLS_V2:
        symbol_dir = args.work_dir / symbol
        symbol_dir.mkdir()
        payloads: dict[str, dict[str, Any]] = {}
        shard_dirs: dict[str, Path] = {}
        weeks_by_periodicity: dict[str, tuple[int, ...]] = {}
        for periodicity in DIRECT_PERIODICITIES_V2:
            weeks = present_weeks(mask, args.year, symbol, periodicity)
            weeks_by_periodicity[periodicity] = weeks
            shard_dir, payload = process_direct_shard(
                contract,
                args.year,
                symbol,
                periodicity,
                symbol_dir,
                opener,
                weeks=weeks,
                vault_version="v2",
            )
            shard_dirs[periodicity] = shard_dir
            payloads[periodicity] = payload
        derived = derive_qc_v2(
            shard_dirs["m1"] / "canonical/prices.csv",
            shard_dirs["H1"] / "canonical/prices.csv",
            args.year,
        )
        derived_records.append({"symbol": symbol, **derived})
        for periodicity in DIRECT_PERIODICITIES_V2:
            weeks = weeks_by_periodicity[periodicity]
            missing_weeks = known_missing_weeks(mask, args.year, symbol, periodicity)
            archive_name = f"fxcm-v2-{symbol}-{args.year}-{periodicity}.tar.zst"
            archive_path = symbol_dir / archive_name
            archive_sha = make_archive(shard_dirs[periodicity], archive_path, weeks=weeks)
            archive_bytes = archive_path.stat().st_size
            app_properties = {
                "vault_version": "v2",
                "operational_version": OPERATIONAL_VERSION_V2_1,
                "run_id": str(args.run_id),
                "head_sha": args.head_sha,
                "year": str(args.year),
                "symbol": symbol,
                "periodicity": periodicity,
                "sha256": archive_sha,
                "partition": partition["id"],
                "state": "UNSEALED",
            }
            uploaded = drive.upload_file_new(
                stage["id"], archive_path, archive_name, "application/zstd", app_properties
            )
            verify_path = symbol_dir / f"verify-{archive_name}"
            drive.download_verify(uploaded["id"], verify_path, archive_bytes, archive_sha)
            verify_path.unlink()
            payload = payloads[periodicity]
            shard_records.append({
                "vault_version": "v2",
                "contract_sha256": contract_hashes[args.acquisition_contract.name],
                "partitions_sha256": contract_hashes[args.partitions_contract.name],
                "availability_mask_sha256": mask_sha,
                "run_id": str(args.run_id),
                "run_attempt": args.run_attempt,
                "head_sha": args.head_sha,
                "year": args.year,
                "symbol": symbol,
                "periodicity": periodicity,
                "partition_id": partition["id"],
                "archive_name": archive_name,
                "archive_sha256": archive_sha,
                "archive_bytes": archive_bytes,
                "canonical_row_count": payload["canonical_row_count"],
                "canonical_first_timestamp_utc": payload["canonical_first_timestamp_utc"],
                "canonical_last_timestamp_utc": payload["canonical_last_timestamp_utc"],
                "canonical_timestamp_sha256": payload["canonical_timestamp_sha256"],
                "canonical_csv_sha256": payload["canonical_csv_sha256"],
                "base_week_count": len(WEEKS_V2),
                "present_week_indices": list(weeks),
                "known_missing_week_indices": list(missing_weeks),
                "source_object_count": payload["source_object_count"],
                "source_objects": payload["source_objects"],
                "observed_row_count": payload["observed_row_count"],
                "usable_row_count": payload["usable_row_count"],
                "crossed_quote_count": payload["crossed_quote_count"],
                "crossed_quote_event_sha256": payload["crossed_quote_event_sha256"],
                "duplicate_count": payload["duplicate_count"],
                "gap_segment_count": payload["gap_segment_count"],
                "missing_nominal_slot_count": payload["missing_nominal_slot_count"],
                "volume_status": payload["volume_status"],
                "field_schema": payload["field_schema"],
                "qc_status": payload["qc_status"],
                "drive_parent_role": "RUN_YEAR_STAGING",
                "drive_upload_redownload_sha256_verified": True,
                "drive_file_id": uploaded["id"],
                "drive_parent_id": stage["id"],
            })
            archive_path.unlink()
        shutil.rmtree(symbol_dir)
    expected_year_sources = expected_year_source_count(mask, args.year)
    if len(shard_records) != 50 or len({(row["symbol"], row["periodicity"]) for row in shard_records}) != 50:
        raise VaultError("V2 year shard inventory mismatch")
    if sum(row["source_object_count"] for row in shard_records) != expected_year_sources:
        raise VaultError("V2 year source object count mismatch")
    year_manifest = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-year-manifest-v2.0.0",
        "status": "YEAR_STAGED_PRIVATE_DRIVE_REDOWNLOAD_VERIFIED_UNSEALED",
        "vault_version": "v2",
        "run_id": str(args.run_id),
        "run_attempt": args.run_attempt,
        "head_sha": args.head_sha,
        "year": args.year,
        "partition_id": partition["id"],
        "contract_sha256": contract_hashes,
        "availability_mask_sha256": mask_sha,
        "base_source_object_count": 2600,
        "source_object_count": expected_year_sources,
        "known_missing_source_object_count": 2600 - expected_year_sources,
        "shard_count": len(shard_records),
        "zstd_version": zstd_version,
        "shards_sha256": canonical_sha256(shard_records),
        "derived_qc_sha256": canonical_sha256(derived_records),
        "batch6_compatibility_passed": all(row["batch6_compatibility_passed"] for row in derived_records),
        "provider_schedule_claimed": False,
        "forward_fill_count": 0,
        "interpolation_count": 0,
        "formal_phase9_authorization_effect": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "stage_folder_id": stage["id"],
        "shards": shard_records,
        "derived_qc": derived_records,
    }
    year_manifest_path = args.work_dir / "YEAR_MANIFEST.json"
    write_canonical_json(year_manifest_path, year_manifest)
    year_sha = sha256_file(year_manifest_path)
    uploaded_manifest = drive.upload_file_new(
        stage["id"],
        year_manifest_path,
        "YEAR_MANIFEST.json",
        "application/json",
        {
            "vault_version": "v2",
            "operational_version": OPERATIONAL_VERSION_V2_1,
            "run_id": str(args.run_id),
            "head_sha": args.head_sha,
            "year": str(args.year),
            "sha256": year_sha,
            "state": "YEAR_COMPLETE_UNSEALED",
        },
    )
    verify_manifest = args.work_dir / "verify-YEAR_MANIFEST.json"
    drive.download_verify(
        uploaded_manifest["id"],
        verify_manifest,
        year_manifest_path.stat().st_size,
        year_sha,
    )
    verify_manifest.unlink()
    return {
        "year": args.year,
        "shard_count": 50,
        "source_object_count": expected_year_sources,
        "known_missing_source_object_count": 2600 - expected_year_sources,
        "batch6_compatibility_passed": year_manifest["batch6_compatibility_passed"],
        "year_manifest_sha256": year_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-contract", type=Path, required=True)
    parser.add_argument("--partitions-contract", type=Path, required=True)
    parser.add_argument("--manifest-schema", type=Path, required=True)
    parser.add_argument("--formal-boundary", type=Path, required=True)
    parser.add_argument("--availability-mask", type=Path, required=True)
    parser.add_argument("--operational-amendment", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--scope-confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--formal-acknowledgement", required=True)
    args = parser.parse_args()
    runner_temp = os.environ.get("RUNNER_TEMP")
    expected_name = f"fxcm-vault-v2-year-{args.year}-{args.run_id}-{args.run_attempt}"
    if (
        not runner_temp
        or args.work_dir.parent.resolve() != Path(runner_temp).resolve()
        or args.work_dir.name != expected_name
    ):
        raise VaultError("V2 work directory is outside the exact ephemeral runner boundary")
    try:
        result = acquire_year_v2(args)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        if args.work_dir.exists() and not args.work_dir.is_symlink():
            shutil.rmtree(args.work_dir)


if __name__ == "__main__":
    raise SystemExit(main())
