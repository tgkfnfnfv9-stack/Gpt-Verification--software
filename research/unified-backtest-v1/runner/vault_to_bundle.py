#!/usr/bin/env python3
"""Convert the completed private FXCM 2022-2025 Vault into ephemeral unified input."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VAULT_RUNNER = REPOSITORY_ROOT / "research/phase9-exploratory-fxcm-20260901/runner"
if str(VAULT_RUNNER) not in sys.path:
    sys.path.insert(0, str(VAULT_RUNNER))

from fxcm_google_drive_private import FOLDER_MIME, GoogleDrivePrivate  # noqa: E402
from fxcm_drive_vault_common import VaultError  # noqa: E402


ROOT_FOLDER_ID = "1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v"
ROOT_FOLDER_NAME = "Phase9 FXCM Data Vault"
SOURCE_RUN_ID = "33705800232"
SOURCE_HEAD_SHA = "be864557a8e16d253e6aecf1519f85ad6162c1a3"
TRANSACTION_NAME = "v2-txn-run-33705800232"
TRANSACTION_AMENDMENT_SHA256 = "03b8ecaa6a75a1df797f8c4de5fbdf5b59ce0a5655957a5f04c1ab595301434b"
YEARS = (2022, 2023, 2024, 2025)
SYMBOLS = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD",
    "CADCHF", "CADJPY", "EURAUD", "EURCHF", "EURGBP",
    "EURJPY", "EURNZD", "EURUSD", "GBPCAD", "GBPCHF",
    "GBPJPY", "GBPNZD", "GBPUSD", "NZDCAD", "NZDCHF",
    "NZDJPY", "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
)
SOURCE_PERIODICITIES = ("m1", "H1")
TARGET_TIMEFRAMES = {"m1": "M1", "H1": "H1"}
RECOVERY_VERSION = "simple-v1.2"
OPERATIONAL_VERSION = "v2.1+simple-v1.2-recovery"
CONFIRMATION = "RUN_UNIFIED_BACKTEST_FROM_COMPLETED_FXCM_VAULT_2022_2025"
USAGE_CONFIRMATION = "I_APPROVE_RESEARCH_INPUT_FROM_2022_2025_FXCM_VAULT"
DATASET_ID = "FXCM25-2022-2025-DIRECT-M1-H1-V1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ID = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
MAX_JSON_BYTES = 10_000_000
MAX_ARCHIVE_BYTES = 4_000_000_000
MAX_TAR_BYTES = 8_000_000_000
MAX_CANONICAL_BYTES = 4_000_000_000
SANITIZED_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}
SOURCE_HEADER = (
    "timestamp_utc",
    "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close",
    "volume_status", "volume",
)
TARGET_HEADER = SOURCE_HEADER[:9]


class BridgeError(RuntimeError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    if path.exists() or path.is_symlink():
        raise BridgeError(f"JSON destination must be new: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def strict_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    if not payload or len(payload) > MAX_JSON_BYTES:
        raise BridgeError(f"JSON size mismatch: {label}")

    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise BridgeError(f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise BridgeError(f"non-finite JSON value in {label}: {value}")

    try:
        value = json.loads(payload, object_pairs_hook=pairs, parse_constant=reject)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BridgeError(f"invalid JSON: {label}") from exc
    if not isinstance(value, dict):
        raise BridgeError(f"JSON root must be object: {label}")
    return value


def partition(year: int) -> str:
    return "ROBUSTNESS" if year <= 2023 else "FINAL_HOLDOUT"


def stage_properties(year: int) -> dict[str, str]:
    return {
        "vault_version": "v2",
        "operational_version": "v2.1",
        "run_id": SOURCE_RUN_ID,
        "head_sha": SOURCE_HEAD_SHA,
        "year": str(year),
        "state": "UNSEALED",
    }


def recovery_common(year: int, recovery_run_id: str, recovery_head_sha: str) -> dict[str, str]:
    return {
        "vault_version": "v2",
        "operational_version": OPERATIONAL_VERSION,
        "recovery_version": RECOVERY_VERSION,
        "run_id": SOURCE_RUN_ID,
        "head_sha": SOURCE_HEAD_SHA,
        "recovery_run_id": recovery_run_id,
        "recovery_run_attempt": "1",
        "recovery_head_sha": recovery_head_sha,
        "year": str(year),
    }


def expected_archive_name(year: int, symbol: str, periodicity: str) -> str:
    return f"fxcm-v2-{symbol}-{year}-{periodicity}.tar.zst"


def validate_year_manifest(
    manifest: dict[str, Any], year: int, recovery_run_id: str, recovery_head_sha: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    if (
        manifest.get("schema_version") != "phase9-exploratory-fxcm-drive-vault-year-manifest-v2.3-simple-v1"
        or manifest.get("status") != "YEAR_STAGED_PRIVATE_DRIVE_REDOWNLOAD_VERIFIED_UNSEALED"
        or manifest.get("vault_version") != "v2"
        or manifest.get("recovery_version") != RECOVERY_VERSION
        or manifest.get("source_run_id") != SOURCE_RUN_ID
        or manifest.get("source_head_sha") != SOURCE_HEAD_SHA
        or manifest.get("recovery_run_id") != recovery_run_id
        or manifest.get("recovery_run_attempt") != 1
        or manifest.get("recovery_head_sha") != recovery_head_sha
        or manifest.get("year") != year
        or manifest.get("partition_id") != partition(year)
        or manifest.get("shard_count") != 50
        or manifest.get("duplicate_shard_count") != 0
        or manifest.get("archive_exact_member_validation_passed") is not True
        or manifest.get("forward_fill_count") != 0
        or manifest.get("interpolation_count") != 0
        or manifest.get("research_outcomes_calculated") is not False
        or manifest.get("outcome_fields") != []
    ):
        raise BridgeError(f"year manifest identity/QC mismatch: {year}")
    shards = manifest.get("shards")
    derived = manifest.get("derived_qc")
    if not isinstance(shards, list) or len(shards) != 50 or not isinstance(derived, list) or len(derived) != 25:
        raise BridgeError(f"year manifest matrix mismatch: {year}")
    if manifest.get("shards_sha256") != canonical_sha256(shards) or manifest.get("derived_qc_sha256") != canonical_sha256(derived):
        raise BridgeError(f"year manifest aggregate hash mismatch: {year}")
    if {row.get("symbol") for row in derived if isinstance(row, dict)} != set(SYMBOLS):
        raise BridgeError(f"derived QC symbol inventory mismatch: {year}")
    for derived_row in derived:
        h1_cross_check = derived_row.get("H1_cross_check")
        if (
            derived_row.get("availability_mask_applied") is not True
            or derived_row.get("forward_fill_count") != 0
            or derived_row.get("interpolation_count") != 0
            or not isinstance(h1_cross_check, dict)
            or not isinstance(h1_cross_check.get("reference_ohlc_mismatch_count"), int)
            or any(
                not isinstance(h1_cross_check.get(field), str)
                or not HEX64.fullmatch(h1_cross_check[field])
                for field in (
                    "completed_bucket_timestamp_sha256",
                    "dropped_bucket_timestamp_sha256",
                    "missing_component_timestamp_sha256",
                    "extra_component_timestamp_sha256",
                    "canonical_bucket_sha256",
                )
            )
        ):
            raise BridgeError(f"derived H1 QC content mismatch: {year}")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in shards:
        if not isinstance(row, dict):
            raise BridgeError("shard record must be object")
        symbol = row.get("symbol")
        periodicity = row.get("periodicity")
        key = (symbol, periodicity)
        if symbol not in SYMBOLS or periodicity not in SOURCE_PERIODICITIES or key in result:
            raise BridgeError(f"invalid/duplicate shard identity: {year}")
        expected_name = expected_archive_name(year, symbol, periodicity)
        expected_weeks = row.get("present_week_indices")
        missing_weeks = row.get("known_missing_week_indices")
        if (
            row.get("vault_version") != "v2"
            or row.get("recovery_version") != RECOVERY_VERSION
            or row.get("source_run_id") != SOURCE_RUN_ID
            or row.get("source_head_sha") != SOURCE_HEAD_SHA
            or row.get("recovery_run_id") != recovery_run_id
            or row.get("recovery_run_attempt") != 1
            or row.get("recovery_head_sha") != recovery_head_sha
            or row.get("year") != year
            or row.get("partition_id") != partition(year)
            or row.get("archive_name") != expected_name
            or not isinstance(row.get("archive_bytes"), int)
            or not 0 < row["archive_bytes"] <= MAX_ARCHIVE_BYTES
            or not isinstance(row.get("archive_sha256"), str)
            or not HEX64.fullmatch(row["archive_sha256"])
            or not isinstance(row.get("canonical_csv_sha256"), str)
            or not HEX64.fullmatch(row["canonical_csv_sha256"])
            or not isinstance(row.get("canonical_row_count"), int)
            or row["canonical_row_count"] <= 0
            or row.get("canonical_row_count") != row.get("usable_row_count")
            or row.get("duplicate_count") != 0
            or row.get("archive_exact_member_validation") is not True
            or row.get("drive_upload_redownload_sha256_verified") is not True
            or not ID.fullmatch(str(row.get("drive_file_id", "")))
            or row.get("field_schema") != list(SOURCE_HEADER)
            or row.get("qc_status") not in ("PASS", "PASS_WITH_CROSSED_ROWS_QUARANTINED")
            or not isinstance(expected_weeks, list)
            or not isinstance(missing_weeks, list)
            or sorted(expected_weeks + missing_weeks) != list(range(1, 53))
            or set(expected_weeks) & set(missing_weeks)
            or row.get("source_object_count") != len(expected_weeks)
        ):
            raise BridgeError(f"shard content/QC mismatch: {expected_name}")
        result[key] = row
    if set(result) != {(symbol, periodicity) for symbol in SYMBOLS for periodicity in SOURCE_PERIODICITIES}:
        raise BridgeError(f"year shard matrix incomplete: {year}")
    return result


def exact_archive_members(weeks: list[int]) -> list[str]:
    return [
        "SHARD_PAYLOAD_MANIFEST.json",
        "canonical/prices.csv",
        *[f"source/{week:02d}.csv.gz" for week in weeks],
    ]


def validate_payload_manifest(payload: dict[str, Any], source_row: dict[str, Any]) -> None:
    fields = (
        "vault_version", "year", "symbol", "periodicity", "base_week_count",
        "present_week_indices", "known_missing_week_indices", "source_object_count",
        "source_objects", "observed_row_count", "usable_row_count", "crossed_quote_count",
        "crossed_quote_event_sha256", "duplicate_count", "gap_segment_count",
        "missing_nominal_slot_count", "canonical_row_count",
        "canonical_first_timestamp_utc", "canonical_last_timestamp_utc",
        "canonical_timestamp_sha256", "canonical_csv_sha256", "field_schema",
        "volume_status", "qc_status",
    )
    if (
        payload.get("schema_version") != "phase9-exploratory-fxcm-drive-vault-shard-payload-v2.0.0"
        or payload.get("forward_fill_count") != 0
        or payload.get("interpolation_count") != 0
        or payload.get("clipped_outside_year_row_count") != 0
        or any(payload.get(field) != source_row.get(field) for field in fields)
    ):
        raise BridgeError("archive payload manifest does not match pinned year manifest")


def extract_canonical_csv(
    archive_path: Path,
    output_path: Path,
    source_row: dict[str, Any],
    scratch_tar: Path,
) -> None:
    if output_path.exists() or output_path.is_symlink() or scratch_tar.exists() or scratch_tar.is_symlink():
        raise BridgeError("archive extraction destinations must be new")
    try:
        process = subprocess.Popen(
            ["zstd", "-d", "--quiet", "--stdout", str(archive_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=SANITIZED_ENV,
        )
        total = 0
        try:
            if process.stdout is None:
                raise BridgeError("zstd output pipe unavailable")
            with scratch_tar.open("xb") as destination:
                while True:
                    block = process.stdout.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_TAR_BYTES:
                        process.kill()
                        raise BridgeError("archive expands beyond limit")
                    destination.write(block)
            if process.wait() != 0:
                raise BridgeError("zstd archive decompression failed")
        finally:
            if process.poll() is None:
                process.kill()
            if process.stdout is not None:
                process.stdout.close()
            process.wait()
        with tarfile.open(scratch_tar, mode="r:") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if names != exact_archive_members(source_row["present_week_indices"]) or len(names) != len(set(names)):
                raise BridgeError("archive exact member inventory mismatch")
            if any(
                not member.isfile() or member.issym() or member.islnk()
                or member.uid != 0 or member.gid != 0 or member.mtime != 0 or member.mode != 0o644
                or PurePosixPath(member.name).is_absolute()
                or any(part in ("", ".", "..") for part in PurePosixPath(member.name).parts)
                for member in members
            ):
                raise BridgeError("archive member safety/metadata mismatch")
            payload_member = archive.getmember("SHARD_PAYLOAD_MANIFEST.json")
            if not 0 < payload_member.size <= MAX_JSON_BYTES:
                raise BridgeError("archive payload manifest size mismatch")
            payload_source = archive.extractfile(payload_member)
            if payload_source is None:
                raise BridgeError("archive payload manifest body missing")
            validate_payload_manifest(
                strict_json_bytes(payload_source.read(payload_member.size + 1), "SHARD_PAYLOAD_MANIFEST.json"),
                source_row,
            )
            member = archive.getmember("canonical/prices.csv")
            if not 0 < member.size <= MAX_CANONICAL_BYTES:
                raise BridgeError("canonical CSV size mismatch")
            source = archive.extractfile(member)
            if source is None:
                raise BridgeError("canonical CSV body missing")
            remaining = member.size
            with output_path.open("xb") as destination:
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise BridgeError("truncated canonical CSV")
                    destination.write(block)
                    remaining -= len(block)
                if source.read(1):
                    raise BridgeError("oversized canonical CSV")
    finally:
        scratch_tar.unlink(missing_ok=True)


UTC = timezone.utc


def parse_timestamp(text: str) -> datetime:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise BridgeError("invalid canonical timestamp") from exc


def price_values(values: list[str]) -> tuple[Decimal, ...]:
    try:
        result = tuple(Decimal(value) for value in values[1:9])
    except InvalidOperation as exc:
        raise BridgeError("invalid canonical decimal") from exc
    if len(result) != 8 or any(not value.is_finite() or value <= 0 for value in result):
        raise BridgeError("canonical price domain mismatch")
    bid = result[:4]
    ask = result[4:]
    if bid[1] < max(bid[0], bid[3]) or bid[2] > min(bid[0], bid[3]) or bid[2] > bid[1]:
        raise BridgeError("canonical BID OHLC geometry mismatch")
    if ask[1] < max(ask[0], ask[3]) or ask[2] > min(ask[0], ask[3]) or ask[2] > ask[1]:
        raise BridgeError("canonical ASK OHLC geometry mismatch")
    return result


def append_m1_and_build_h1(
    source_path: Path,
    output: Any,
    row: dict[str, Any],
    previous_timestamp: str | None,
) -> tuple[str, int, dict[str, tuple[Decimal, ...]], list[str]]:
    if sha256_file(source_path) != row["canonical_csv_sha256"]:
        raise BridgeError("canonical CSV SHA-256 mismatch")
    source_count = 0
    retained_count = 0
    first = None
    last = previous_timestamp
    buckets: dict[datetime, list[tuple[datetime, tuple[Decimal, ...]]]] = {}
    quarantined: list[str] = []
    with source_path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.reader(source, strict=True)
        if tuple(next(reader, ())) != SOURCE_HEADER:
            raise BridgeError("canonical CSV header mismatch")
        for values in reader:
            if len(values) != len(SOURCE_HEADER):
                raise BridgeError("canonical CSV row width mismatch")
            timestamp = values[0]
            if first is None:
                first = timestamp
            if last is not None and timestamp <= last:
                raise BridgeError("canonical CSV timestamps not globally increasing")
            last = timestamp
            source_count += 1
            prices = price_values(values)
            stamp = parse_timestamp(timestamp)
            if stamp.second or stamp.microsecond:
                raise BridgeError("M1 timestamp alignment mismatch")
            if prices[4] < prices[0] or prices[7] < prices[3]:
                quarantined.append(timestamp)
                continue
            output.writerow(values[:9])
            retained_count += 1
            bucket = stamp.replace(minute=0)
            buckets.setdefault(bucket, []).append((stamp, prices))
    if (
        source_count != row["canonical_row_count"]
        or first != row["canonical_first_timestamp_utc"]
        or last != row["canonical_last_timestamp_utc"]
    ):
        raise BridgeError("canonical CSV row/timestamp identity mismatch")
    if last is None:
        raise BridgeError("empty canonical CSV")
    complete: dict[str, tuple[Decimal, ...]] = {}
    for bucket, rows in buckets.items():
        expected = [bucket + timedelta(minutes=index) for index in range(60)]
        if len(rows) != 60 or [stamp for stamp, _ in rows] != expected:
            continue
        values = [prices for _, prices in rows]
        complete[bucket.strftime("%Y-%m-%dT%H:%M:%SZ")] = (
            values[0][0], max(item[1] for item in values), min(item[2] for item in values), values[-1][3],
            values[0][4], max(item[5] for item in values), min(item[6] for item in values), values[-1][7],
        )
    return last, retained_count, complete, quarantined


def append_h1_intersection(
    source_path: Path,
    output: Any,
    row: dict[str, Any],
    previous_timestamp: str | None,
    complete_m1_h1: dict[str, tuple[Decimal, ...]],
) -> tuple[str, int, list[str], list[str], list[str]]:
    if sha256_file(source_path) != row["canonical_csv_sha256"]:
        raise BridgeError("canonical H1 CSV SHA-256 mismatch")
    source_count = 0
    retained_count = 0
    first = None
    last = previous_timestamp
    no_complete_m1: list[str] = []
    ohlc_mismatch: list[str] = []
    crossed: list[str] = []
    with source_path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.reader(source, strict=True)
        if tuple(next(reader, ())) != SOURCE_HEADER:
            raise BridgeError("canonical H1 CSV header mismatch")
        for values in reader:
            if len(values) != len(SOURCE_HEADER):
                raise BridgeError("canonical H1 CSV row width mismatch")
            timestamp = values[0]
            if first is None:
                first = timestamp
            if last is not None and timestamp <= last:
                raise BridgeError("canonical H1 timestamps not globally increasing")
            last = timestamp
            source_count += 1
            stamp = parse_timestamp(timestamp)
            if stamp.minute or stamp.second or stamp.microsecond:
                raise BridgeError("H1 timestamp alignment mismatch")
            prices = price_values(values)
            derived = complete_m1_h1.get(timestamp)
            if derived is None:
                no_complete_m1.append(timestamp)
                continue
            if prices[4] < prices[0] or prices[7] < prices[3]:
                crossed.append(timestamp)
                continue
            if prices != derived:
                ohlc_mismatch.append(timestamp)
            output.writerow(values[:9])
            retained_count += 1
    if (
        source_count != row["canonical_row_count"]
        or first != row["canonical_first_timestamp_utc"]
        or last != row["canonical_last_timestamp_utc"]
    ):
        raise BridgeError("canonical H1 row/timestamp identity mismatch")
    if last is None:
        raise BridgeError("empty canonical H1 CSV")
    return last, retained_count, no_complete_m1, ohlc_mismatch, crossed


def verify_transaction(drive: GoogleDrivePrivate) -> dict[int, dict[str, Any]]:
    drive.verify_private_root(ROOT_FOLDER_NAME, ROOT_FOLDER_ID)
    root_children = drive.list_children(ROOT_FOLDER_ID)
    transactions = [row for row in root_children if row.get("name") == TRANSACTION_NAME]
    expected_properties = {
        "vault_version": "v2",
        "operational_version": "v2.1",
        "run_id": SOURCE_RUN_ID,
        "head_sha": SOURCE_HEAD_SHA,
        "state": "ACQUIRING",
        "amendment_sha256": TRANSACTION_AMENDMENT_SHA256,
    }
    if len(transactions) != 1 or transactions[0].get("mimeType") != FOLDER_MIME or transactions[0].get("appProperties") != expected_properties:
        raise BridgeError("source transaction identity mismatch")
    stages = drive.list_children(transactions[0]["id"])
    expected_names = {f"v2-staging-run-{SOURCE_RUN_ID}-year-{year}" for year in range(2012, 2026)}
    if len(stages) != 14 or {row.get("name") for row in stages} != expected_names:
        raise BridgeError("source transaction stage inventory mismatch")
    result: dict[int, dict[str, Any]] = {}
    for year in YEARS:
        name = f"v2-staging-run-{SOURCE_RUN_ID}-year-{year}"
        stage = next(row for row in stages if row.get("name") == name)
        if stage.get("mimeType") != FOLDER_MIME or stage.get("appProperties") != stage_properties(year):
            raise BridgeError(f"source year stage identity mismatch: {year}")
        result[year] = stage
    return result


def read_source_manifests(
    drive: GoogleDrivePrivate,
    stages: dict[int, dict[str, Any]],
    recovery_run_id: str,
    recovery_head_sha: str,
    expected_manifest_sha256s: dict[int, str],
    scratch: Path,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[tuple[str, str], dict[str, Any]]], list[dict[str, Any]]]:
    manifests: dict[int, dict[str, Any]] = {}
    matrix: dict[int, dict[tuple[str, str], dict[str, Any]]] = {}
    provenance: list[dict[str, Any]] = []
    for year in YEARS:
        stage = stages[year]
        children = drive.list_children(stage["id"])
        expected_names = {
            *(expected_archive_name(year, symbol, periodicity) for symbol in SYMBOLS for periodicity in SOURCE_PERIODICITIES),
            "YEAR_MANIFEST.json",
        }
        names = [row.get("name") for row in children]
        if len(names) != 51 or len(names) != len(set(names)) or set(names) != expected_names:
            raise BridgeError(f"source year Drive inventory mismatch: {year}")
        by_name = {row["name"]: row for row in children}
        manifest_object = by_name["YEAR_MANIFEST.json"]
        properties = dict(manifest_object.get("appProperties") or {})
        digest = properties.pop("sha256", None)
        expected = {**recovery_common(year, recovery_run_id, recovery_head_sha), "state": "YEAR_COMPLETE_UNSEALED"}
        try:
            size = int(manifest_object.get("size"))
        except (TypeError, ValueError):
            size = -1
        if (
            manifest_object.get("mimeType") != "application/json"
            or not isinstance(digest, str)
            or not HEX64.fullmatch(digest)
            or digest != expected_manifest_sha256s[year]
            or not 0 < size <= MAX_JSON_BYTES
            or properties != expected
        ):
            raise BridgeError(f"source year manifest metadata mismatch: {year}")
        local = scratch / f"YEAR_MANIFEST-{year}.json"
        drive.download_verify(manifest_object["id"], local, size, digest)
        payload = local.read_bytes()
        manifest = strict_json_bytes(payload, f"YEAR_MANIFEST-{year}")
        shards = validate_year_manifest(manifest, year, recovery_run_id, recovery_head_sha)
        for (symbol, periodicity), shard in shards.items():
            remote = by_name[shard["archive_name"]]
            remote_properties = dict(remote.get("appProperties") or {})
            expected_properties = {
                **recovery_common(year, recovery_run_id, recovery_head_sha),
                "symbol": symbol,
                "periodicity": periodicity,
                "sha256": shard["archive_sha256"],
                "partition": partition(year),
                "state": "UNSEALED",
            }
            try:
                remote_size = int(remote.get("size"))
            except (TypeError, ValueError):
                remote_size = -1
            if (
                remote.get("id") != shard["drive_file_id"]
                or remote.get("mimeType") != "application/zstd"
                or remote_size != shard["archive_bytes"]
                or remote_properties != expected_properties
            ):
                raise BridgeError(f"source archive Drive metadata mismatch: {shard['archive_name']}")
        manifests[year] = manifest
        matrix[year] = shards
        provenance.append({
            "year": year,
            "year_manifest_drive_file_id": manifest_object["id"],
            "year_manifest_bytes": size,
            "year_manifest_sha256": digest,
            "shards_sha256": manifest["shards_sha256"],
            "derived_qc_sha256": manifest["derived_qc_sha256"],
            "source_object_inventory_sha256": manifest["source_object_inventory_sha256"],
            "source_object_count": manifest["source_object_count"],
            "known_missing_source_object_count": manifest["known_missing_source_object_count"],
        })
        local.unlink()
    return manifests, matrix, provenance


def build_dataset(
    drive: GoogleDrivePrivate,
    matrix: dict[int, dict[tuple[str, str], dict[str, Any]]],
    provenance_rows: list[dict[str, Any]],
    recovery_run_id: str,
    recovery_head_sha: str,
    work_dir: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    dataset = work_dir / "dataset"
    scratch = work_dir / "scratch"
    dataset.mkdir()
    scratch.mkdir()
    estimated_csv_bytes = sum(
        row["canonical_row_count"] * 210
        for year in YEARS for row in matrix[year].values()
    )
    largest_archive = max(row["archive_bytes"] for year in YEARS for row in matrix[year].values())
    if shutil.disk_usage(work_dir).free < estimated_csv_bytes + largest_archive * 3 + 1_000_000_000:
        raise BridgeError("insufficient disk space for combined CSVs and one bounded archive")

    files: list[dict[str, Any]] = []
    reconciliation_rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        series_dir = dataset / "series" / symbol
        series_dir.mkdir(parents=True)
        complete_m1_by_year: dict[int, dict[str, tuple[Decimal, ...]]] = {}
        for periodicity in SOURCE_PERIODICITIES:
            timeframe = TARGET_TIMEFRAMES[periodicity]
            output_path = series_dir / f"{timeframe}.csv"
            total_rows = 0
            previous_timestamp = None
            with output_path.open("x", encoding="utf-8", newline="") as output:
                writer = csv.writer(output, lineterminator="\n")
                writer.writerow(TARGET_HEADER)
                for year in YEARS:
                    source = matrix[year][(symbol, periodicity)]
                    archive_path = scratch / source["archive_name"]
                    canonical_path = scratch / f"canonical-{year}-{symbol}-{periodicity}.csv"
                    tar_path = scratch / f"inspect-{year}-{symbol}-{periodicity}.tar"
                    drive.download_verify(source["drive_file_id"], archive_path, source["archive_bytes"], source["archive_sha256"])
                    try:
                        extract_canonical_csv(archive_path, canonical_path, source, tar_path)
                        if periodicity == "m1":
                            previous_timestamp, retained, complete_h1, quarantined = append_m1_and_build_h1(
                                canonical_path, writer, source, previous_timestamp
                            )
                            complete_m1_by_year[year] = complete_h1
                            total_rows += retained
                            reconciliation_rows.append({
                                "year": year,
                                "symbol": symbol,
                                "timeframe": "M1",
                                "source_row_count": source["canonical_row_count"],
                                "retained_row_count": retained,
                                "additional_crossed_open_or_close_quarantine_count": len(quarantined),
                                "additional_quarantine_timestamp_sha256": hashlib.sha256("".join(
                                    f"{stamp}\n" for stamp in quarantined
                                ).encode("ascii")).hexdigest(),
                                "complete_m1_derived_h1_count": len(complete_h1),
                            })
                        else:
                            previous_timestamp, retained, missing, mismatches, crossed = append_h1_intersection(
                                canonical_path,
                                writer,
                                source,
                                previous_timestamp,
                                complete_m1_by_year[year],
                            )
                            total_rows += retained
                            reconciliation_rows.append({
                                "year": year,
                                "symbol": symbol,
                                "timeframe": "H1",
                                "source_row_count": source["canonical_row_count"],
                                "retained_row_count": retained,
                                "direct_h1_without_complete_60_m1_count": len(missing),
                                "direct_h1_without_complete_60_m1_timestamp_sha256": hashlib.sha256("".join(
                                    f"{stamp}\n" for stamp in missing
                                ).encode("ascii")).hexdigest(),
                                "direct_vs_m1_derived_ohlc_mismatch_count": len(mismatches),
                                "direct_vs_m1_derived_ohlc_mismatch_timestamp_sha256": hashlib.sha256("".join(
                                    f"{stamp}\n" for stamp in mismatches
                                ).encode("ascii")).hexdigest(),
                                "additional_crossed_open_or_close_quarantine_count": len(crossed),
                                "additional_crossed_open_or_close_timestamp_sha256": hashlib.sha256("".join(
                                    f"{stamp}\n" for stamp in crossed
                                ).encode("ascii")).hexdigest(),
                                "direct_h1_remains_canonical": True,
                                "forward_fill_count": 0,
                                "interpolation_count": 0,
                            })
                    finally:
                        archive_path.unlink(missing_ok=True)
                        canonical_path.unlink(missing_ok=True)
                        tar_path.unlink(missing_ok=True)
            files.append({
                "instrument_id": symbol,
                "timeframe": timeframe,
                "source_role": "DIRECT_PROVIDER",
                "path": f"series/{symbol}/{timeframe}.csv",
                "sha256": sha256_file(output_path),
                "bytes": output_path.stat().st_size,
                "row_count": total_rows,
            })

    provenance = {
        "schema_version": "fxcm-vault-to-unified-input-provenance-v1.0.0",
        "status": "SOURCE_QC_VERIFIED_RESEARCH_USE_EXPLICITLY_APPROVED",
        "provider": "FXCM CandleData",
        "provider_primary_locator": "https://candledata.fxcorporate.com/",
        "source_root_folder_id": ROOT_FOLDER_ID,
        "source_root_folder_name": ROOT_FOLDER_NAME,
        "source_transaction_name": TRANSACTION_NAME,
        "source_transaction_state": "ACQUIRING",
        "source_run_id": SOURCE_RUN_ID,
        "source_head_sha": SOURCE_HEAD_SHA,
        "recovery_version": RECOVERY_VERSION,
        "recovery_run_id": recovery_run_id,
        "recovery_head_sha": recovery_head_sha,
        "interval_start_inclusive": "2022-01-01T00:00:00Z",
        "interval_end_exclusive": "2026-01-01T00:00:00Z",
        "source_year_stage_state": "YEAR_COMPLETE_UNSEALED",
        "source_stage_mutated": False,
        "timestamp_semantics": "FXCM_CANDLEDATA_DATETIME_TREATED_AS_UTC_INTERVAL_OPEN",
        "timestamp_semantics_basis": "EMPIRICAL_DIRECT_H1_TIMESTAMP_TO_COMPLETE_60_M1_ALIGNMENT_PROVIDER_NOT_EXPLICIT",
        "year_manifests": provenance_rows,
        "year_manifests_identity_sha256": canonical_sha256(provenance_rows),
        "conversion_reconciliation": reconciliation_rows,
        "conversion_reconciliation_sha256": canonical_sha256(reconciliation_rows),
        "forward_fill_count": 0,
        "interpolation_count": 0,
        "research_outcomes_calculated_during_conversion": False,
    }
    provenance_path = dataset / "evidence/fxcm-vault-provenance.json"
    write_json(provenance_path, provenance)
    timestamp_evidence = {
        "schema_version": "timestamp-semantics-evidence-v1.0.0",
        "status": "EMPIRICALLY_ALIGNED_ASSUMPTION",
        "providers": [{
            "provider": "FXCM CandleData",
            "dataset_or_endpoint": "FXCM CandleData weekly CSV canonical private Vault V2",
            "timestamp_column": "timestamp_utc",
            "timezone": "UTC",
            "timeframes": ["M1", "H1"],
            "semantics_by_timeframe": {"M1": "INTERVAL_OPEN_INSTANT", "H1": "INTERVAL_OPEN_INSTANT"},
            "primary_source_locator": "https://candledata.fxcorporate.com/",
            "primary_source_artifact_path": "evidence/fxcm-vault-provenance.json",
            "primary_source_artifact_sha256": sha256_file(provenance_path),
            "primary_source_artifact_bytes": provenance_path.stat().st_size,
            "review_status": "APPROVED_FOR_EXPLORATORY_BACKTEST_ONLY",
        }],
    }
    timestamp_path = dataset / "evidence/timestamp-semantics.json"
    write_json(timestamp_path, timestamp_evidence)
    instruments = [{
        "instrument_id": symbol,
        "provider": "FXCM CandleData",
        "provider_symbol": f"{symbol[:3]}/{symbol[3:]}",
        "asset_class": "FX",
        "series_type": "SPOT",
        "quote_currency": symbol[3:],
        "price_domain": "STRICTLY_POSITIVE",
        "tick_size": "0.001" if symbol.endswith("JPY") else "0.00001",
        "roll_policy_id": None,
        "roll_policy_path": None,
        "roll_policy_sha256": None,
        "roll_policy_bytes": None,
    } for symbol in SYMBOLS]
    manifest = {
        "schema_version": "unified-market-dataset-v1.0.0",
        "dataset_id": DATASET_ID,
        "timezone": "UTC",
        "timestamp_semantics": "BAR_OPEN",
        "source_timestamp_semantics": "BAR_OPEN_EMPIRICALLY_ALIGNED_PROVIDER_NOT_EXPLICIT",
        "timestamp_semantics_evidence": {
            "path": "evidence/timestamp-semantics.json",
            "sha256": sha256_file(timestamp_path),
            "bytes": timestamp_path.stat().st_size,
        },
        "aggregation_profile_id": "UTC_FIXED_V1",
        "required_direct_timeframes": ["M1", "H1"],
        "start_inclusive": "2022-01-01T00:00:00Z",
        "end_exclusive": "2026-01-01T00:00:00Z",
        "instruments": instruments,
        "files": files,
    }
    manifest_path = dataset / "DATASET_MANIFEST.json"
    write_json(manifest_path, manifest)
    return dataset, manifest_path, provenance


def parse_expected_manifest_sha256s(text: str) -> dict[int, str]:
    rows = text.split(",")
    result: dict[int, str] = {}
    for row in rows:
        parts = row.split(":")
        if len(parts) != 2:
            raise BridgeError("expected year manifest SHA list format mismatch")
        try:
            year = int(parts[0])
        except ValueError as exc:
            raise BridgeError("invalid year in expected manifest SHA list") from exc
        digest = parts[1]
        if year in result or year not in YEARS or not HEX64.fullmatch(digest):
            raise BridgeError("invalid/duplicate expected year manifest SHA")
        result[year] = digest
    if set(result) != set(YEARS):
        raise BridgeError("exact 2022-2025 manifest SHA list required")
    return result


def run(args: argparse.Namespace, drive: GoogleDrivePrivate | None = None) -> dict[str, Any]:
    if args.confirmation != CONFIRMATION or args.usage_confirmation != USAGE_CONFIRMATION:
        raise BridgeError("exact conversion and research-use confirmations required")
    if not ID.fullmatch(args.recovery_run_id) or not HEX40.fullmatch(args.recovery_head_sha):
        raise BridgeError("invalid recovery run/head identity")
    expected_manifest_sha256s = parse_expected_manifest_sha256s(args.expected_year_manifest_sha256s)
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise BridgeError("work directory must be new")
    args.work_dir.mkdir(parents=True, mode=0o700)
    drive = drive or GoogleDrivePrivate()
    stages = verify_transaction(drive)
    manifests, matrix, provenance_rows = read_source_manifests(
        drive,
        stages,
        args.recovery_run_id,
        args.recovery_head_sha,
        expected_manifest_sha256s,
        args.work_dir,
    )
    dataset_path, manifest_path, _ = build_dataset(
        drive, matrix, provenance_rows, args.recovery_run_id, args.recovery_head_sha, args.work_dir
    )
    manifest_sha = sha256_file(manifest_path)
    return {
        "status": "UNIFIED_BACKTEST_EPHEMERAL_INPUT_READY",
        "dataset_root": str(dataset_path),
        "dataset_manifest_sha256": manifest_sha,
        "dataset_id": DATASET_ID,
        "instrument_count": len(SYMBOLS),
        "input_file_count": len(SYMBOLS) * 2,
        "source_year_manifest_count": len(manifests),
        "source_archive_count": sum(len(rows) for rows in matrix.values()),
        "source_stage_mutated": False,
        "drive_write_performed": False,
        "research_outcomes_calculated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-run-id", required=True)
    parser.add_argument("--recovery-head-sha", required=True)
    parser.add_argument("--expected-year-manifest-sha256s", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except (BridgeError, VaultError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
