#!/usr/bin/env python3
"""Recover one empty FXCM Run #1 year and verify its private Drive upload."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import tarfile
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import fxcm_drive_vault_acquire_year as acquire_base
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
    SECRET_NAMES,
    VaultError,
    canonical_sha256,
    iso_utc,
    load_json,
    sha256_file,
    write_canonical_json,
)
from fxcm_drive_vault_v2_common import (
    DIRECT_PERIODICITIES_V2,
    SYMBOLS_V2,
    WEEKS_V2,
    expected_year_source_count,
    known_missing_weeks,
    load_v2_1_operational_amendment,
    load_v2_contracts,
    partition_for_year_v2,
    present_weeks,
)
from fxcm_google_drive_private import FOLDER_MIME, GoogleDrivePrivate


UTC = timezone.utc
RECOVERY_YEARS = (2022, 2023, 2024, 2025)
SOURCE_RUN_ID = "33705800232"
SOURCE_HEAD_SHA = "be864557a8e16d253e6aecf1519f85ad6162c1a3"
TRANSACTION_NAME = "v2-txn-run-33705800232"
AMENDMENT_SHA256 = "03b8ecaa6a75a1df797f8c4de5fbdf5b59ce0a5655957a5f04c1ab595301434b"
RECOVERY_VERSION = "simple-v1"
FINE_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60}
HIGH_TIMEFRAMES = ("H4", "D1", "W1")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PRESERVED_ARCHIVE_BYTES = 2548863404
PRESERVED_INVENTORY_SHA256 = "4a0f0cfb78ead6d6730ca7b41b716de8e2fef984e7f36ded17828d9e7b40dc4d"
SANITIZED_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}
BASE_DOWNLOAD_SOURCE = acquire_base.download_source


def download_source_with_integrity_retry(opener, url: str, destination: Path) -> tuple[int, str]:
    """Retry bounded successful-but-invalid payloads without changing identity."""
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            size, digest = BASE_DOWNLOAD_SOURCE(opener, url, destination)
            with gzip.open(destination, "rt", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
                first_row = next(reader, None)
            if not header or not first_row:
                raise VaultError("empty frozen source object")
            return size, digest
        except (VaultError, gzip.BadGzipFile, EOFError, UnicodeError) as error:
            last_error = error
            destination.unlink(missing_ok=True)
            retryable = any(
                marker in str(error).lower()
                for marker in ("too small", "not gzip", "empty frozen", "compressed file ended")
            )
            if not retryable or attempt == 3:
                raise VaultError("frozen-present source failed bounded content-integrity retries") from error
    raise VaultError("source integrity retry exhausted") from last_error


acquire_base.download_source = download_source_with_integrity_retry


def _hash_identities(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _aggregate_rows(start: datetime, rows: list[Any]) -> Aggregate:
    if not rows:
        raise VaultError("cannot aggregate an empty bucket")
    result = Aggregate.from_row(start, rows[0])
    for row in rows[1:]:
        result.add(row)
    return result


def _combine_h1(start: datetime, components: list[Aggregate]) -> Aggregate:
    if not components:
        raise VaultError("cannot combine an empty H1 bucket")
    first = components[0]
    result = Aggregate(
        start=start,
        first_timestamp=first.first_timestamp,
        last_timestamp=components[-1].last_timestamp,
        count=sum(item.count for item in components),
        bid=list(first.bid),
        ask=list(first.ask),
        volume=first.volume,
        all_volume_present=all(item.all_volume_present for item in components),
    )
    for item in components[1:]:
        result.bid[1] = max(result.bid[1], item.bid[1])
        result.bid[2] = min(result.bid[2], item.bid[2])
        result.bid[3] = item.bid[3]
        result.ask[1] = max(result.ask[1], item.ask[1])
        result.ask[2] = min(result.ask[2], item.ask[2])
        result.ask[3] = item.ask[3]
        if result.volume is None or item.volume is None:
            result.volume = None
            result.all_volume_present = False
        else:
            result.volume += item.volume
    return result


def _serialize_aggregate(aggregate: Aggregate) -> bytes:
    values = [format(value, "f") for value in aggregate_tuple(aggregate)]
    if aggregate.all_volume_present and aggregate.volume is not None:
        volume_status = "PRESENT"
        volume = format(aggregate.volume, "f")
    else:
        volume_status = "ABSENT_FROM_SOURCE_SCHEMA"
        volume = ""
    return (iso_utc(aggregate.start) + "," + ",".join(values + [volume_status, volume]) + "\n").encode("ascii")


@lru_cache(maxsize=8)
def expected_fx_timestamp_inventory(year: int, minutes: int) -> tuple[datetime, ...]:
    """Independent 24x5 inventory: Sunday 17:00 through Friday 17:00 New York."""
    if year not in RECOVERY_YEARS or minutes not in (1, 60):
        raise VaultError("expected timestamp inventory scope mismatch")
    eastern = ZoneInfo("America/New_York")
    current = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)
    step = timedelta(minutes=minutes)
    result: list[datetime] = []
    while current < end:
        local = current.astimezone(eastern)
        weekday = local.weekday()
        open_now = (
            weekday in (0, 1, 2, 3)
            or (weekday == 4 and local.hour < 17)
            or (weekday == 6 and local.hour >= 17)
        )
        if open_now:
            result.append(current)
        current += step
    return tuple(result)


def _summary(
    candidate: int,
    completed: list[str],
    dropped: list[str],
    missing: list[str],
    extra: list[str],
    output_digest: hashlib._Hash,
    reference: str,
) -> dict[str, Any]:
    return {
        "candidate_bucket_count": candidate,
        "complete_bucket_count": len(completed),
        "dropped_bucket_count": len(dropped),
        "completed_bucket_timestamp_sha256": _hash_identities(completed),
        "dropped_bucket_timestamp_sha256": _hash_identities(dropped),
        "missing_component_timestamp_count": len(missing),
        "missing_component_timestamp_sha256": _hash_identities(missing),
        "extra_component_timestamp_count": len(extra),
        "extra_component_timestamp_sha256": _hash_identities(extra),
        "canonical_bucket_sha256": output_digest.hexdigest(),
        "completeness_reference": reference,
    }


def derive_qc_simple_v1(m1_path: Path, h1_path: Path, year: int) -> dict[str, Any]:
    """Derive deterministic fingerprints; incomplete buckets are dropped and hashed."""
    m1_rows = list(iter_canonical(m1_path))
    h1_rows = list(iter_canonical(h1_path))
    direct_h1 = {row.timestamp: row for row in h1_rows}
    if len(direct_h1) != len(h1_rows):
        raise VaultError("duplicate direct H1 timestamp")

    expected_m1 = expected_fx_timestamp_inventory(year, 1)
    expected_h1 = expected_fx_timestamp_inventory(year, 60)
    fine: dict[str, dict[str, Any]] = {}
    exact_h1: dict[datetime, Aggregate] = {}
    for timeframe, minutes in FINE_MINUTES.items():
        groups: dict[datetime, list[Any]] = defaultdict(list)
        expected_groups: dict[datetime, list[datetime]] = defaultdict(list)
        for row in m1_rows:
            groups[bucket_start(row.timestamp, timeframe)].append(row)
        for timestamp in expected_m1:
            expected_groups[bucket_start(timestamp, timeframe)].append(timestamp)
        completed: list[str] = []
        dropped: list[str] = []
        missing_all: list[str] = []
        extra_all: list[str] = []
        digest = hashlib.sha256()
        reference_mismatch = 0
        candidate_starts = sorted(set(groups) | set(expected_groups))
        for start in candidate_starts:
            rows = groups.get(start, [])
            actual = {row.timestamp for row in rows}
            expected = set(expected_groups.get(start, []))
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            missing_all.extend(iso_utc(value) for value in missing)
            extra_all.extend(iso_utc(value) for value in extra)
            identity = iso_utc(start)
            if missing or extra or len(rows) != len(expected) or not expected:
                dropped.append(identity)
                continue
            aggregate = _aggregate_rows(start, rows)
            if timeframe == "H1":
                reference = direct_h1.get(start)
                if reference is None or aggregate_tuple(aggregate) != row_tuple(reference):
                    reference_mismatch += 1
                    dropped.append(identity)
                    continue
                exact_h1[start] = aggregate
            digest.update(_serialize_aggregate(aggregate))
            completed.append(identity)
        fine[timeframe] = _summary(
            len(candidate_starts), completed, dropped, missing_all, extra_all, digest,
            "INDEPENDENT_24X5_NEW_YORK_SESSION_EXPECTED_M1_SET",
        )
        if timeframe == "H1":
            derived_keys = set(exact_h1)
            reference_keys = set(direct_h1)
            fine[timeframe].update({
                "direct_reference_timestamp_count": len(reference_keys),
                "direct_reference_missing_for_derived_count": len(derived_keys - reference_keys),
                "derived_timestamp_missing_for_reference_count": len(reference_keys - derived_keys),
                "reference_ohlc_mismatch_count": reference_mismatch,
                "exact_reference_match_count": len(derived_keys & reference_keys),
            })

    high: dict[str, dict[str, Any]] = {}
    year_start = datetime(year, 1, 1, tzinfo=UTC)
    year_end = datetime(year + 1, 1, 1, tzinfo=UTC)
    for timeframe in HIGH_TIMEFRAMES:
        expected_groups: dict[datetime, list[datetime]] = defaultdict(list)
        actual_groups: dict[datetime, list[datetime]] = defaultdict(list)
        for timestamp in expected_h1:
            expected_groups[bucket_start(timestamp, timeframe)].append(timestamp)
        for timestamp in exact_h1:
            actual_groups[bucket_start(timestamp, timeframe)].append(timestamp)
        completed: list[str] = []
        dropped: list[str] = []
        missing_all: list[str] = []
        extra_all: list[str] = []
        digest = hashlib.sha256()
        boundary_drops = 0
        for start in sorted(set(expected_groups) | set(actual_groups)):
            identity = iso_utc(start)
            if timeframe == "W1" and not (year_start <= start and start + timedelta(days=7) <= year_end):
                boundary_drops += 1
                dropped.append(identity)
                continue
            expected = set(expected_groups.get(start, []))
            actual = set(actual_groups.get(start, []))
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            missing_all.extend(iso_utc(value) for value in missing)
            extra_all.extend(iso_utc(value) for value in extra)
            if missing or extra or not expected:
                dropped.append(identity)
                continue
            components = [exact_h1[timestamp] for timestamp in sorted(expected)]
            aggregate = _combine_h1(start, components)
            digest.update(_serialize_aggregate(aggregate))
            completed.append(identity)
        high[timeframe] = _summary(
            len(set(expected_groups) | set(actual_groups)), completed, dropped,
            missing_all, extra_all, digest,
            "INDEPENDENT_24X5_NEW_YORK_SESSION_EXPECTED_H1_SET",
        )
        high[timeframe]["outer_year_boundary_drop_count"] = boundary_drops

    result = {**{name: fine[name] for name in ("M5", "M15", "M30")}, **high}
    result["H1_cross_check"] = fine["H1"]
    result.update({
        "availability_mask_applied": True,
        "forward_fill_count": 0,
        "interpolation_count": 0,
        "derived_price_files_stored": 0,
        "expected_timestamp_inventory": "SUNDAY_17_NEW_YORK_TO_FRIDAY_17_NEW_YORK_DST_AWARE",
        "holiday_or_special_closure_policy": "MISSING_EXPECTED_BUCKETS_DROP_COUNT_HASH_NO_FILL",
    })
    return result


def archive_expected_members(weeks: tuple[int, ...]) -> list[str]:
    return [
        "SHARD_PAYLOAD_MANIFEST.json",
        "canonical/prices.csv",
        *[f"source/{week:02d}.csv.gz" for week in weeks],
    ]


def verify_archive_exact(path: Path, weeks: tuple[int, ...], scratch_tar: Path) -> None:
    if scratch_tar.exists() or scratch_tar.is_symlink():
        raise VaultError("archive verification scratch path must be new")
    subprocess.run(
        ["zstd", "-d", "--quiet", "--force", "-o", str(scratch_tar), str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=SANITIZED_SUBPROCESS_ENV,
    )
    try:
        if scratch_tar.stat().st_size > 8 * 1024 * 1024 * 1024:
            raise VaultError("archive expands beyond bounded size")
        with tarfile.open(scratch_tar, "r:") as archive:
            members = archive.getmembers()
        names = [member.name for member in members]
        expected = archive_expected_members(weeks)
        if len(names) != len(set(names)):
            raise VaultError("duplicate archive member")
        if names != expected:
            raise VaultError("unknown, missing, or reordered archive member")
        if any(
            not member.isfile() or member.issym() or member.islnk()
            or member.uid != 0 or member.gid != 0 or member.mtime != 0 or member.mode != 0o644
            for member in members
        ):
            raise VaultError("archive contains non-canonical member metadata")
    finally:
        scratch_tar.unlink(missing_ok=True)


def load_simple_contract(path: Path) -> dict[str, Any]:
    contract = load_json(path)
    if (
        contract.get("schema_version") != "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.0.0"
        or contract.get("status") != "FROZEN_IMPLEMENTED_NOT_AUTHORIZED_FOR_EXECUTION"
        or contract.get("interval", {}).get("years") != list(RECOVERY_YEARS)
        or contract.get("symbols") != list(SYMBOLS_V2)
        or contract.get("direct_periodicities") != list(DIRECT_PERIODICITIES_V2)
        or contract.get("counts", {}).get("archive_shards") != 200
        or contract.get("counts", {}).get("frozen_present_source_identities") != 10084
        or contract.get("counts", {}).get("frozen_known_missing_source_identities") != 316
        or contract.get("existing_transaction", {}).get("read_only_inventory_year_digest_sha256") != PRESERVED_INVENTORY_SHA256
        or contract.get("current_authorization", {}).get("workflow_dispatch") is not False
        or contract.get("current_authorization", {}).get("price_access") is not False
        or contract.get("current_authorization", {}).get("drive_write") is not False
    ):
        raise VaultError("simple recovery contract mismatch")
    return contract


def verify_frozen_anchors(contract: dict[str, Any], paths: Iterable[Path]) -> None:
    expected = contract["frozen_anchors_sha256"]
    observed = {path.name: sha256_file(path) for path in paths}
    if observed != expected:
        raise VaultError("frozen anchor SHA-256 mismatch")


def _partition_name(year: int) -> str:
    if year <= 2019:
        return "DEVELOPMENT"
    if year <= 2021:
        return "STRICT_OOS"
    if year <= 2023:
        return "ROBUSTNESS"
    return "FINAL_HOLDOUT"


def _archive_names(year: int) -> list[str]:
    return [f"fxcm-v2-{symbol}-{year}-{periodicity}.tar.zst" for symbol in SYMBOLS_V2 for periodicity in DIRECT_PERIODICITIES_V2]


def _stage_properties(year: int) -> dict[str, str]:
    return {
        "vault_version": "v2", "operational_version": "v2.1",
        "run_id": SOURCE_RUN_ID, "head_sha": SOURCE_HEAD_SHA,
        "year": str(year), "state": "UNSEALED",
    }


def _validate_stage_folder(stage: dict[str, Any], year: int) -> None:
    if stage.get("mimeType") != FOLDER_MIME or stage.get("appProperties") != _stage_properties(year):
        raise VaultError("year stage metadata mismatch")


def _validate_preserved_stage(drive: GoogleDrivePrivate, stage: dict[str, Any], year: int) -> dict[str, Any]:
    _validate_stage_folder(stage, year)
    children = drive.list_children(stage["id"])
    names = [row.get("name") for row in children]
    expected_archives = _archive_names(year)
    if len(names) != 51 or len(names) != len(set(names)) or set(names) != set(expected_archives + ["YEAR_MANIFEST.json"]):
        raise VaultError("preserved year exact name inventory mismatch")
    valid_metadata: list[dict[str, Any]] = []
    for name in expected_archives:
        row = next(item for item in children if item.get("name") == name)
        symbol, periodicity = name[len("fxcm-v2-") : -len(".tar.zst")].rsplit("-", 2)[0::2]
        properties = dict(row.get("appProperties") or {})
        digest = properties.pop("sha256", None)
        expected = {
            "vault_version": "v2", "operational_version": "v2.1",
            "run_id": SOURCE_RUN_ID, "head_sha": SOURCE_HEAD_SHA,
            "year": str(year), "symbol": symbol, "periodicity": periodicity,
            "partition": _partition_name(year), "state": "UNSEALED",
        }
        try:
            size = int(row.get("size"))
        except (TypeError, ValueError):
            size = -1
        if row.get("mimeType") != "application/zstd" or size <= 0 or not isinstance(digest, str) or not HEX64.fullmatch(digest) or properties != expected:
            raise VaultError("preserved archive metadata mismatch")
        valid_metadata.append({"name": name, "size": size, "sha256": digest})
    manifest = next(item for item in children if item.get("name") == "YEAR_MANIFEST.json")
    properties = dict(manifest.get("appProperties") or {})
    digest = properties.pop("sha256", None)
    expected_manifest = {
        "vault_version": "v2", "operational_version": "v2.1",
        "run_id": SOURCE_RUN_ID, "head_sha": SOURCE_HEAD_SHA,
        "year": str(year), "state": "YEAR_COMPLETE_UNSEALED",
    }
    try:
        manifest_size = int(manifest.get("size"))
    except (TypeError, ValueError):
        manifest_size = -1
    if manifest.get("mimeType") != "application/json" or manifest_size <= 0 or not isinstance(digest, str) or not HEX64.fullmatch(digest) or properties != expected_manifest:
        raise VaultError("preserved manifest metadata mismatch")
    valid_metadata.sort(key=lambda row: row["name"])
    return {
        "year": year,
        "stage_match_count": 1,
        "stage_metadata_valid": True,
        "child_object_count": 51,
        "expected_archive_count": 50,
        "valid_archive_metadata_count": 50,
        "missing_archive_count": 0,
        "invalid_archive_metadata_count": 0,
        "duplicate_expected_name_extra_count": 0,
        "unexpected_child_object_count": 0,
        "year_manifest_match_count": 1,
        "year_manifest_metadata_valid": True,
        "valid_archive_names_sha256": canonical_sha256([row["name"] for row in valid_metadata]),
        "valid_archive_metadata_sha256": canonical_sha256(valid_metadata),
        "valid_archive_total_bytes": sum(row["size"] for row in valid_metadata),
        "stage_classification": "COMPLETE_YEAR_STAGE_METADATA_ONLY",
    }


def _empty_inventory_row(year: int) -> dict[str, Any]:
    return {
        "year": year,
        "stage_match_count": 1,
        "stage_metadata_valid": True,
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
        "stage_classification": "PARTIAL_OR_INVALID_YEAR_STAGE_METADATA_ONLY",
    }


def _validate_recovered_stage(
    drive: GoogleDrivePrivate, stage: dict[str, Any], year: int,
    recovery_run_id: str, recovery_head_sha: str,
) -> None:
    _validate_stage_folder(stage, year)
    children = drive.list_children(stage["id"])
    names = [row.get("name") for row in children]
    expected_archives = _archive_names(year)
    if len(names) != 51 or len(names) != len(set(names)) or set(names) != set(expected_archives + ["YEAR_MANIFEST.json"]):
        raise VaultError("previous recovered year exact inventory mismatch")
    common = {
        "vault_version": "v2", "operational_version": "v2.1+simple-v1-recovery",
        "run_id": SOURCE_RUN_ID, "head_sha": SOURCE_HEAD_SHA,
        "recovery_run_id": recovery_run_id, "recovery_run_attempt": "1",
        "recovery_head_sha": recovery_head_sha, "year": str(year),
    }
    for name in expected_archives:
        row = next(item for item in children if item.get("name") == name)
        symbol, periodicity = name[len("fxcm-v2-") : -len(".tar.zst")].rsplit("-", 2)[0::2]
        properties = dict(row.get("appProperties") or {})
        digest = properties.pop("sha256", None)
        expected = {**common, "symbol": symbol, "periodicity": periodicity, "partition": _partition_name(year), "state": "UNSEALED"}
        if row.get("mimeType") != "application/zstd" or not isinstance(digest, str) or not HEX64.fullmatch(digest) or properties != expected:
            raise VaultError("previous recovered archive metadata mismatch")
    manifest = next(item for item in children if item.get("name") == "YEAR_MANIFEST.json")
    properties = dict(manifest.get("appProperties") or {})
    digest = properties.pop("sha256", None)
    if manifest.get("mimeType") != "application/json" or not isinstance(digest, str) or not HEX64.fullmatch(digest) or properties != {**common, "state": "YEAR_COMPLETE_UNSEALED"}:
        raise VaultError("previous recovered manifest metadata mismatch")


def verify_existing_transaction(
    drive: GoogleDrivePrivate, contract: dict[str, Any], year: int,
    recovery_run_id: str, recovery_head_sha: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    existing = contract["existing_transaction"]
    drive.verify_private_root(existing["root_folder_name"], existing["root_folder_id"])
    root_children = drive.list_children(existing["root_folder_id"])
    transactions = [row for row in root_children if row.get("name") == TRANSACTION_NAME]
    if len(root_children) != 1 or len(transactions) != 1 or transactions[0].get("mimeType") != FOLDER_MIME:
        raise VaultError("single existing transaction identity mismatch")
    transaction = transactions[0]
    expected_transaction_properties = {
        "vault_version": "v2",
        "operational_version": "v2.1",
        "run_id": SOURCE_RUN_ID,
        "head_sha": SOURCE_HEAD_SHA,
        "state": "ACQUIRING",
        "amendment_sha256": AMENDMENT_SHA256,
    }
    if transaction.get("appProperties") != expected_transaction_properties:
        raise VaultError("existing transaction metadata mismatch")
    children = drive.list_children(transaction["id"])
    expected_names = {f"v2-staging-run-{SOURCE_RUN_ID}-year-{value}" for value in range(2012, 2026)}
    if len(children) != 14 or {row.get("name") for row in children} != expected_names:
        raise VaultError("transaction stage inventory mismatch")
    preserved_rows: list[dict[str, Any]] = []
    for preserved_year in range(2012, 2022):
        name = f"v2-staging-run-{SOURCE_RUN_ID}-year-{preserved_year}"
        matches = [row for row in children if row.get("name") == name]
        if len(matches) != 1:
            raise VaultError("preserved year stage identity mismatch")
        preserved_rows.append(_validate_preserved_stage(drive, matches[0], preserved_year))
    preserved_total = sum(row["valid_archive_total_bytes"] for row in preserved_rows)
    if preserved_total != PRESERVED_ARCHIVE_BYTES:
        raise VaultError("preserved archive byte invariant mismatch")
    baseline_rows = preserved_rows + [_empty_inventory_row(value) for value in RECOVERY_YEARS]
    if canonical_sha256(baseline_rows) != existing["read_only_inventory_year_digest_sha256"]:
        raise VaultError("preserved read-only inventory digest mismatch")
    target_stage = None
    for recovery_year in RECOVERY_YEARS:
        name = f"v2-staging-run-{SOURCE_RUN_ID}-year-{recovery_year}"
        matches = [row for row in children if row.get("name") == name]
        if len(matches) != 1:
            raise VaultError("recovery year stage identity mismatch")
        _validate_stage_folder(matches[0], recovery_year)
        if recovery_year < year:
            _validate_recovered_stage(drive, matches[0], recovery_year, recovery_run_id, recovery_head_sha)
        elif drive.list_children(matches[0]["id"]):
            raise VaultError("current or later recovery stage is not exactly empty")
        if recovery_year == year:
            target_stage = matches[0]
    if target_stage is None:
        raise VaultError("target recovery stage missing")
    return transaction, target_stage


def load_recovery_manifest_schema(contract: dict[str, Any], path: Path) -> dict[str, Any]:
    schema = load_json(path)
    expected = contract["recovery_manifest_schema"]
    if (
        path.name != Path(expected["path"]).name
        or sha256_file(path) != expected["sha256"]
        or schema.get("schema_version") != "phase9-exploratory-fxcm-drive-vault-recovery-manifest-simple-v1.0.0"
        or schema.get("status") != "FROZEN_IMPLEMENTED_NOT_AUTHORIZED_FOR_EXECUTION"
        or schema.get("additional_properties") is not False
    ):
        raise VaultError("recovery manifest schema mismatch")
    return schema


def validate_year_manifest(manifest: dict[str, Any], schema: dict[str, Any]) -> None:
    if set(manifest) != set(schema["year_manifest_exact_keys"]):
        raise VaultError("year manifest exact key mismatch")
    shards = manifest.get("shards")
    derived = manifest.get("derived_qc")
    if not isinstance(shards, list) or len(shards) != 50 or not isinstance(derived, list) or len(derived) != 25:
        raise VaultError("year manifest inventory count mismatch")
    if any(set(row) != set(schema["shard_exact_keys"]) for row in shards):
        raise VaultError("shard manifest exact key mismatch")
    shard_keys = [(row["symbol"], row["periodicity"]) for row in shards]
    archive_names = [row["archive_name"] for row in shards]
    drive_ids = [row["drive_file_id"] for row in shards]
    if len(set(shard_keys)) != 50 or len(set(archive_names)) != 50 or len(set(drive_ids)) != 50:
        raise VaultError("duplicate shard, archive name, or Drive file ID")
    if any(
        row["duplicate_count"] != 0
        or row["archive_exact_member_validation"] is not True
        or row["drive_upload_redownload_sha256_verified"] is not True
        or not HEX64.fullmatch(row["archive_sha256"])
        or not HEX64.fullmatch(row["canonical_csv_sha256"])
        or not HEX64.fullmatch(row["canonical_timestamp_sha256"])
        or not HEX64.fullmatch(row["source_object_inventory_sha256"])
        for row in shards
    ):
        raise VaultError("shard QC or SHA field mismatch")
    required_timeframes = set(schema["derived_required_timeframes"])
    required_keys = set(schema["derived_timeframe_required_keys"])
    symbols = [row.get("symbol") for row in derived]
    if len(set(symbols)) != 25 or set(symbols) != set(SYMBOLS_V2):
        raise VaultError("derived symbol inventory mismatch")
    for row in derived:
        if not required_timeframes.issubset(row):
            raise VaultError("derived timeframe inventory mismatch")
        for timeframe in required_timeframes:
            summary = row[timeframe]
            if not required_keys.issubset(summary):
                raise VaultError("derived timeframe schema mismatch")
            for name in (
                "completed_bucket_timestamp_sha256", "dropped_bucket_timestamp_sha256",
                "missing_component_timestamp_sha256", "extra_component_timestamp_sha256",
                "canonical_bucket_sha256",
            ):
                if not HEX64.fullmatch(summary[name]):
                    raise VaultError("derived timeframe SHA mismatch")
    if manifest["duplicate_shard_count"] != 0 or manifest["archive_exact_member_validation_passed"] is not True:
        raise VaultError("year manifest aggregate QC mismatch")
    if manifest["shards_sha256"] != canonical_sha256(shards) or manifest["derived_qc_sha256"] != canonical_sha256(derived):
        raise VaultError("year manifest aggregate SHA mismatch")
    source_inventory = [
        {"symbol": row["symbol"], "periodicity": row["periodicity"], **source}
        for row in shards for source in row["source_objects"]
    ]
    if (
        manifest["source_object_inventory_sha256"] != canonical_sha256(source_inventory)
        or manifest["source_object_count"] != len(source_inventory)
    ):
        raise VaultError("year source object inventory SHA mismatch")


def reconcile_uploaded_stage(
    drive: GoogleDrivePrivate,
    stage: dict[str, Any],
    shards: list[dict[str, Any]],
    manifest_id: str | None = None,
    manifest_sha256: str | None = None,
) -> None:
    children = drive.list_children(stage["id"])
    expected_names = {row["archive_name"] for row in shards}
    if manifest_id is not None:
        expected_names.add("YEAR_MANIFEST.json")
    names = [row.get("name") for row in children]
    if len(names) != len(expected_names) or len(names) != len(set(names)) or set(names) != expected_names:
        raise VaultError("post-upload stage exact inventory mismatch")
    for shard in shards:
        row = next(item for item in children if item.get("name") == shard["archive_name"])
        try:
            size = int(row.get("size"))
        except (TypeError, ValueError):
            size = -1
        expected_properties = {
            "vault_version": "v2", "operational_version": "v2.1+simple-v1-recovery",
            "run_id": SOURCE_RUN_ID, "head_sha": SOURCE_HEAD_SHA,
            "recovery_run_id": shard["recovery_run_id"],
            "recovery_run_attempt": str(shard["recovery_run_attempt"]),
            "recovery_head_sha": shard["recovery_head_sha"], "year": str(shard["year"]),
            "symbol": shard["symbol"], "periodicity": shard["periodicity"],
            "sha256": shard["archive_sha256"], "partition": shard["partition_id"], "state": "UNSEALED",
        }
        if (
            row.get("id") != shard["drive_file_id"]
            or row.get("mimeType") != "application/zstd"
            or size != shard["archive_bytes"]
            or row.get("appProperties") != expected_properties
        ):
            raise VaultError("post-upload archive metadata mismatch")
    if manifest_id is not None:
        row = next(item for item in children if item.get("name") == "YEAR_MANIFEST.json")
        if row.get("id") != manifest_id or row.get("mimeType") != "application/json":
            raise VaultError("post-upload year manifest identity mismatch")
        properties = row.get("appProperties") or {}
        if properties.get("sha256") != manifest_sha256 or properties.get("state") != "YEAR_COMPLETE_UNSEALED":
            raise VaultError("post-upload year manifest metadata mismatch")


def recover_year(args: argparse.Namespace) -> dict[str, Any]:
    simple = load_simple_contract(args.recovery_contract)
    recovery_manifest_schema = load_recovery_manifest_schema(simple, args.recovery_manifest_schema)
    anchor_paths = (
        args.acquisition_contract,
        args.partitions_contract,
        args.manifest_schema,
        args.formal_boundary,
        args.availability_mask,
        args.operational_amendment,
        args.recovery_design,
    )
    verify_frozen_anchors(simple, anchor_paths)
    acquisition, partitions, _, _, mask = load_v2_contracts(
        args.acquisition_contract,
        args.partitions_contract,
        args.manifest_schema,
        args.formal_boundary,
        args.availability_mask,
    )
    load_v2_1_operational_amendment(args.operational_amendment, anchor_paths[:5])
    if args.year not in RECOVERY_YEARS or args.run_attempt != 1:
        raise VaultError("recovery workflow identity mismatch")
    workflow = simple["workflow"]
    if (
        args.confirmation != workflow["confirmation"]
        or args.scope_confirmation != workflow["scope_confirmation"]
        or args.usage_confirmation != workflow["usage_confirmation"]
    ):
        raise VaultError("exact execution confirmations required")
    if not args.run_id or not args.head_sha or args.run_id == SOURCE_RUN_ID:
        raise VaultError("new recovery provenance required")
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise VaultError("recovery work directory must be new")
    args.work_dir.mkdir(parents=True)

    drive = GoogleDrivePrivate()
    _, stage = verify_existing_transaction(drive, simple, args.year, str(args.run_id), args.head_sha)
    for secret_name in SECRET_NAMES:
        os.environ.pop(secret_name, None)
    opener = urllib.request.build_opener(RejectRedirects())
    partition = partition_for_year_v2(partitions, args.year)
    shard_records: list[dict[str, Any]] = []
    derived_records: list[dict[str, Any]] = []
    pending_uploads: list[tuple[Path, tuple[int, ...], dict[str, str], dict[str, Any]]] = []
    recovery_contract_sha = sha256_file(args.recovery_contract)
    availability_mask_sha = sha256_file(args.availability_mask)
    zstd_version = subprocess.run(
        ["zstd", "--version"], check=True, capture_output=True, text=True,
        env=SANITIZED_SUBPROCESS_ENV,
    ).stdout.strip()

    for symbol in SYMBOLS_V2:
        symbol_dir = args.work_dir / symbol
        symbol_dir.mkdir()
        shard_dirs: dict[str, Path] = {}
        payloads: dict[str, dict[str, Any]] = {}
        weeks_by_periodicity: dict[str, tuple[int, ...]] = {}
        for periodicity in DIRECT_PERIODICITIES_V2:
            weeks = present_weeks(mask, args.year, symbol, periodicity)
            weeks_by_periodicity[periodicity] = weeks
            shard_dir, payload = process_direct_shard(
                acquisition, args.year, symbol, periodicity, symbol_dir, opener,
                weeks=weeks, vault_version="v2",
            )
            shard_dirs[periodicity] = shard_dir
            payloads[periodicity] = payload

        derived_records.append({
            "symbol": symbol,
            **derive_qc_simple_v1(
                shard_dirs["m1"] / "canonical/prices.csv",
                shard_dirs["H1"] / "canonical/prices.csv",
                args.year,
            ),
        })

        for periodicity in DIRECT_PERIODICITIES_V2:
            weeks = weeks_by_periodicity[periodicity]
            archive_name = f"fxcm-v2-{symbol}-{args.year}-{periodicity}.tar.zst"
            archive_path = symbol_dir / archive_name
            archive_sha = make_archive(shard_dirs[periodicity], archive_path, weeks=weeks)
            verify_archive_exact(archive_path, weeks, symbol_dir / f"inspect-{periodicity}.tar")
            archive_bytes = archive_path.stat().st_size
            properties: dict[str, str] = {
                "vault_version": "v2",
                "operational_version": "v2.1+simple-v1-recovery",
                "run_id": SOURCE_RUN_ID,
                "head_sha": SOURCE_HEAD_SHA,
                "recovery_run_id": str(args.run_id),
                "recovery_run_attempt": str(args.run_attempt),
                "recovery_head_sha": args.head_sha,
                "year": str(args.year),
                "symbol": symbol,
                "periodicity": periodicity,
                "sha256": archive_sha,
                "partition": partition["id"],
                "state": "UNSEALED",
            }
            payload = payloads[periodicity]
            record: dict[str, Any] = {
                "vault_version": "v2",
                "recovery_version": RECOVERY_VERSION,
                "source_run_id": SOURCE_RUN_ID,
                "source_head_sha": SOURCE_HEAD_SHA,
                "recovery_run_id": str(args.run_id),
                "recovery_run_attempt": args.run_attempt,
                "recovery_head_sha": args.head_sha,
                "recovery_contract_sha256": recovery_contract_sha,
                "availability_mask_sha256": availability_mask_sha,
                "year": args.year,
                "symbol": symbol,
                "periodicity": periodicity,
                "partition_id": partition["id"],
                "archive_name": archive_name,
                "archive_sha256": archive_sha,
                "archive_bytes": archive_bytes,
                "archive_member_names_sha256": _hash_identities(archive_expected_members(weeks)),
                "archive_exact_member_validation": True,
                "canonical_row_count": payload["canonical_row_count"],
                "canonical_first_timestamp_utc": payload["canonical_first_timestamp_utc"],
                "canonical_last_timestamp_utc": payload["canonical_last_timestamp_utc"],
                "canonical_timestamp_sha256": payload["canonical_timestamp_sha256"],
                "canonical_csv_sha256": payload["canonical_csv_sha256"],
                "base_week_count": len(WEEKS_V2),
                "present_week_indices": list(weeks),
                "known_missing_week_indices": list(known_missing_weeks(mask, args.year, symbol, periodicity)),
                "source_object_count": payload["source_object_count"],
                "source_objects": payload["source_objects"],
                "source_object_inventory_sha256": canonical_sha256(payload["source_objects"]),
                "observed_row_count": payload["observed_row_count"],
                "usable_row_count": payload["usable_row_count"],
                "duplicate_count": payload["duplicate_count"],
                "crossed_quote_count": payload["crossed_quote_count"],
                "crossed_quote_event_sha256": payload["crossed_quote_event_sha256"],
                "gap_segment_count": payload["gap_segment_count"],
                "missing_nominal_slot_count": payload["missing_nominal_slot_count"],
                "volume_status": payload["volume_status"],
                "field_schema": payload["field_schema"],
                "qc_status": payload["qc_status"],
                "drive_upload_redownload_sha256_verified": False,
                "drive_file_id": "PENDING",
            }
            shard_records.append(record)
            pending_uploads.append((archive_path, weeks, properties, record))

    expected_sources = expected_year_source_count(mask, args.year)
    shard_keys = [(row["symbol"], row["periodicity"]) for row in shard_records]
    archive_names = [row["archive_name"] for row in shard_records]
    if (
        len(shard_records) != 50
        or len(set(shard_keys)) != 50
        or len(set(archive_names)) != 50
        or sum(row["source_object_count"] for row in shard_records) != expected_sources
    ):
        raise VaultError("recovery year count mismatch")

    # Phase two begins only after all 50 local archives and all derived QC pass.
    for archive_path, weeks, properties, record in pending_uploads:
        uploaded = drive.upload_file_new(
            stage["id"], archive_path, record["archive_name"], "application/zstd", properties
        )
        verify_path = args.work_dir / f"redownload-{record['archive_name']}"
        drive.download_verify(uploaded["id"], verify_path, record["archive_bytes"], record["archive_sha256"])
        verify_archive_exact(verify_path, weeks, args.work_dir / f"inspect-redownload-{record['symbol']}-{record['periodicity']}.tar")
        verify_path.unlink()
        record["drive_upload_redownload_sha256_verified"] = True
        record["drive_file_id"] = uploaded["id"]
        archive_path.unlink()
    reconcile_uploaded_stage(drive, stage, shard_records)
    source_object_inventory = [
        {"symbol": row["symbol"], "periodicity": row["periodicity"], **source}
        for row in shard_records
        for source in row["source_objects"]
    ]
    year_manifest = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-year-manifest-v2.3-simple-v1",
        "status": "YEAR_STAGED_PRIVATE_DRIVE_REDOWNLOAD_VERIFIED_UNSEALED",
        "vault_version": "v2",
        "recovery_version": RECOVERY_VERSION,
        "source_run_id": SOURCE_RUN_ID,
        "source_head_sha": SOURCE_HEAD_SHA,
        "recovery_run_id": str(args.run_id),
        "recovery_run_attempt": args.run_attempt,
        "recovery_head_sha": args.head_sha,
        "year": args.year,
        "partition_id": partition["id"],
        "recovery_contract_sha256": recovery_contract_sha,
        "availability_mask_sha256": availability_mask_sha,
        "base_source_object_count": 2600,
        "source_object_count": expected_sources,
        "known_missing_source_object_count": 2600 - expected_sources,
        "shard_count": len(shard_records),
        "zstd_version": zstd_version,
        "shards_sha256": canonical_sha256(shard_records),
        "derived_qc_sha256": canonical_sha256(derived_records),
        "source_object_inventory_sha256": canonical_sha256(source_object_inventory),
        "source_payload_sha256_present": True,
        "canonical_csv_sha256_present": True,
        "timestamp_column_sha256_present": True,
        "missing_bucket_timestamp_sha256_present": True,
        "archive_exact_member_validation_passed": True,
        "duplicate_shard_count": 0,
        "forward_fill_count": 0,
        "interpolation_count": 0,
        "formal_phase9_authorization_effect": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "stage_folder_id": stage["id"],
        "shards": shard_records,
        "derived_qc": derived_records,
    }
    validate_year_manifest(year_manifest, recovery_manifest_schema)
    manifest_path = args.work_dir / "YEAR_MANIFEST.json"
    write_canonical_json(manifest_path, year_manifest)
    manifest_sha = sha256_file(manifest_path)
    uploaded_manifest = drive.upload_file_new(
        stage["id"], manifest_path, "YEAR_MANIFEST.json", "application/json",
        {
            "vault_version": "v2",
            "operational_version": "v2.1+simple-v1-recovery",
            "run_id": SOURCE_RUN_ID,
            "head_sha": SOURCE_HEAD_SHA,
            "recovery_run_id": str(args.run_id),
            "recovery_run_attempt": str(args.run_attempt),
            "recovery_head_sha": args.head_sha,
            "year": str(args.year),
            "sha256": manifest_sha,
            "state": "YEAR_COMPLETE_UNSEALED",
        },
    )
    verify_manifest = args.work_dir / "redownload-YEAR_MANIFEST.json"
    drive.download_verify(uploaded_manifest["id"], verify_manifest, manifest_path.stat().st_size, manifest_sha)
    if sha256_file(verify_manifest) != manifest_sha:
        raise VaultError("year manifest re-download SHA mismatch")
    verify_manifest.unlink()
    reconcile_uploaded_stage(drive, stage, shard_records, uploaded_manifest["id"], manifest_sha)
    return {
        "status": "YEAR_PRIVATE_UPLOAD_REDOWNLOAD_VERIFIED_UNSEALED",
        "year": args.year,
        "archive_count": 50,
        "source_object_count": expected_sources,
        "known_missing_source_object_count": 2600 - expected_sources,
        "year_manifest_sha256": manifest_sha,
        "price_artifact_count": 0,
        "research_outcomes_calculated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-contract", type=Path, required=True)
    parser.add_argument("--recovery-manifest-schema", type=Path, required=True)
    parser.add_argument("--recovery-design", type=Path, required=True)
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
    args = parser.parse_args()
    def _handle_signal(signum, _frame):
        raise VaultError(f"termination signal received: {signum}")
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, _handle_signal)
    runner_temp = os.environ.get("RUNNER_TEMP")
    expected_name = f"fxcm-recovery-simple-v1-{args.year}-{args.run_id}-{args.run_attempt}"
    if (
        not runner_temp
        or args.work_dir.parent.resolve() != Path(runner_temp).resolve()
        or args.work_dir.name != expected_name
    ):
        raise VaultError("work directory outside exact ephemeral runner boundary")
    try:
        print(json.dumps(recover_year(args), sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        if args.work_dir.exists() and not args.work_dir.is_symlink():
            shutil.rmtree(args.work_dir)


if __name__ == "__main__":
    raise SystemExit(main())
