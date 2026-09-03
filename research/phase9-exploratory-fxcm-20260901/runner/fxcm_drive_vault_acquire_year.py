#!/usr/bin/env python3
"""Acquire one frozen FXCM calendar-year matrix slice and stage it in private Drive."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

from fxcm_drive_vault_common import (
    CANONICAL_HEADER,
    DIRECT_HEADER,
    DIRECT_PERIODICITIES,
    SYMBOLS,
    WEEKS,
    YEARS,
    VaultError,
    canonical_json_bytes,
    canonical_sha256,
    contract_sha_bundle,
    iso_utc,
    load_frozen_contracts,
    partition_for_year,
    require_exact_confirmations,
    sha256_file,
    source_url,
    validate_safe_member,
    validate_source_url,
    write_canonical_json,
)
from fxcm_google_drive_private import GoogleDrivePrivate


UTC = timezone.utc
MAX_SOURCE_GZIP_BYTES = 64 * 1024 * 1024
MAX_SHARD_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
PERIOD_STEPS = {"m1": timedelta(minutes=1), "H1": timedelta(hours=1), "D1": timedelta(days=1)}
DERIVED_MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise VaultError(f"source redirect prohibited: {code}")


@dataclass(frozen=True)
class Row:
    timestamp: datetime
    bid: tuple[Decimal, Decimal, Decimal, Decimal]
    ask: tuple[Decimal, Decimal, Decimal, Decimal]
    volume: Decimal | None


@dataclass
class Aggregate:
    start: datetime
    first_timestamp: datetime
    last_timestamp: datetime
    count: int
    bid: list[Decimal]
    ask: list[Decimal]
    volume: Decimal | None
    all_volume_present: bool

    @classmethod
    def from_row(cls, start: datetime, row: Row) -> "Aggregate":
        return cls(start, row.timestamp, row.timestamp, 1, list(row.bid), list(row.ask), row.volume, row.volume is not None)

    def add(self, row: Row) -> None:
        self.last_timestamp = row.timestamp
        self.count += 1
        self.bid[1] = max(self.bid[1], row.bid[1])
        self.bid[2] = min(self.bid[2], row.bid[2])
        self.bid[3] = row.bid[3]
        self.ask[1] = max(self.ask[1], row.ask[1])
        self.ask[2] = min(self.ask[2], row.ask[2])
        self.ask[3] = row.ask[3]
        if self.volume is None or row.volume is None:
            self.all_volume_present = False
            self.volume = None
        else:
            self.volume += row.volume


def decimal_value(text: str, field: str, allow_zero: bool = False) -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        raise VaultError(f"invalid decimal field: {field}") from None
    if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        raise VaultError(f"non-positive or non-finite decimal field: {field}")
    return value


def parse_fxcm_timestamp(text: str) -> datetime:
    for pattern in ("%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise VaultError("invalid FXCM timestamp")


def valid_ohlc(values: tuple[Decimal, Decimal, Decimal, Decimal]) -> bool:
    open_, high, low, close = values
    return high >= max(open_, close, low) and low <= min(open_, close, high)


def download_source(opener, url: str, destination: Path) -> tuple[int, str]:
    validate_source_url(url)
    if destination.exists() or destination.is_symlink():
        raise VaultError("source destination must be new")
    for attempt in range(1, 5):
        request = urllib.request.Request(url, headers={"User-Agent": "phase9-fxcm-drive-vault/1.0"})
        try:
            with opener.open(request, timeout=90) as response, destination.open("xb") as handle:
                if response.status != 200:
                    raise VaultError("source status is not 200")
                if response.geturl() != url:
                    raise VaultError("source final URL mismatch")
                total = 0
                digest = hashlib.sha256()
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_SOURCE_GZIP_BYTES:
                        raise VaultError("source object exceeds compressed byte limit")
                    digest.update(block)
                    handle.write(block)
            if total < 20:
                raise VaultError("source object too small")
            with destination.open("rb") as handle:
                if handle.read(2) != b"\x1f\x8b":
                    raise VaultError("source object is not gzip")
            return total, digest.hexdigest()
        except urllib.error.HTTPError as error:
            destination.unlink(missing_ok=True)
            if error.code in RETRYABLE_HTTP and attempt < 4:
                time.sleep(2 ** (attempt - 1))
                continue
            raise VaultError(f"missing or unavailable frozen source object: HTTP {error.code}") from None
        except (urllib.error.URLError, ssl.SSLError, TimeoutError, ConnectionError) as error:
            destination.unlink(missing_ok=True)
            if attempt < 4:
                time.sleep(2 ** (attempt - 1))
                continue
            raise VaultError("source download failed after bounded retries") from error
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    raise AssertionError("unreachable")


def _canonical_event(symbol: str, periodicity: str, year: int, week: int, source_sha: str, row_ordinal: int) -> bytes:
    return f"{symbol}\0{periodicity}\0{year}\0{week}\0{source_sha}\0{row_ordinal}\n".encode("ascii")


def process_direct_shard(
    contract: dict,
    year: int,
    symbol: str,
    periodicity: str,
    work_dir: Path,
    opener,
    weeks: tuple[int, ...] = WEEKS,
    vault_version: str = "v1",
) -> tuple[Path, dict]:
    shard_dir = work_dir / f"{symbol}-{periodicity}"
    source_dir = shard_dir / "source"
    canonical_dir = shard_dir / "canonical"
    source_dir.mkdir(parents=True)
    canonical_dir.mkdir()
    source_objects: list[dict] = []
    if not weeks or tuple(sorted(set(weeks))) != weeks or any(week not in WEEKS for week in weeks):
        raise VaultError("invalid frozen source week set")
    for week in weeks:
        url = source_url(contract, year, symbol, periodicity, week)
        source_path = source_dir / f"{week:02d}.csv.gz"
        size, digest = download_source(opener, url, source_path)
        source_objects.append({
            "week_index": week, "url": url, "http_status": 200, "bytes": size,
            "sha256": digest, "row_count": 0,
        })
        time.sleep(0.02)
    output_path = canonical_dir / "prices.csv"
    observed = usable = crossed = clipped = duplicate = 0
    crossed_digest = hashlib.sha256()
    timestamp_digest = hashlib.sha256()
    previous_observed: datetime | None = None
    previous_usable: datetime | None = None
    first: datetime | None = None
    last: datetime | None = None
    gap_segments = missing_slots = 0
    uncompressed_bytes = 0
    volume_mode: bool | None = None
    year_start = datetime(year, 1, 1, tzinfo=UTC)
    year_end = datetime(year + 1, 1, 1, tzinfo=UTC)
    step = PERIOD_STEPS[periodicity]
    with output_path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CANONICAL_HEADER)
        for source_entry in source_objects:
            source_path = source_dir / f"{source_entry['week_index']:02d}.csv.gz"
            with gzip.open(source_path, "rt", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                header = tuple(reader.fieldnames or ())
                current_volume_mode = header == DIRECT_HEADER + ("Volume",)
                if header not in (DIRECT_HEADER, DIRECT_HEADER + ("Volume",)):
                    raise VaultError("unexpected FXCM direct header")
                if volume_mode is None:
                    volume_mode = current_volume_mode
                elif volume_mode != current_volume_mode:
                    raise VaultError("partial Volume schema across one shard")
                for row_ordinal, raw in enumerate(reader, 1):
                    source_entry["row_count"] += 1
                    if set(raw) != set(header) or any(value is None for value in raw.values()):
                        raise VaultError("invalid FXCM row shape")
                    uncompressed_bytes += sum(len(value) for value in raw.values()) + len(raw)
                    if uncompressed_bytes > MAX_SHARD_UNCOMPRESSED_BYTES:
                        raise VaultError("source shard exceeds uncompressed byte limit")
                    timestamp = parse_fxcm_timestamp(raw["DateTime"])
                    if not year_start <= timestamp < year_end:
                        clipped += 1
                        continue
                    if timestamp.second or timestamp.microsecond:
                        raise VaultError("direct timestamp sub-second misalignment")
                    if periodicity == "m1" and timestamp.second:
                        raise VaultError("m1 timestamp misalignment")
                    if periodicity == "H1" and timestamp.minute:
                        raise VaultError("H1 timestamp misalignment")
                    if periodicity == "D1" and (timestamp.hour or timestamp.minute):
                        raise VaultError("D1 timestamp misalignment")
                    if previous_observed is not None:
                        if timestamp == previous_observed:
                            duplicate += 1
                            raise VaultError("duplicate direct timestamp")
                        if timestamp < previous_observed:
                            raise VaultError("out-of-order direct timestamp")
                    previous_observed = timestamp
                    observed += 1
                    bid = tuple(decimal_value(raw[f"Bid{name}"], f"Bid{name}") for name in ("Open", "High", "Low", "Close"))
                    ask = tuple(decimal_value(raw[f"Ask{name}"], f"Ask{name}") for name in ("Open", "High", "Low", "Close"))
                    if not valid_ohlc(bid) or not valid_ohlc(ask):
                        raise VaultError("invalid direct OHLC geometry")
                    volume = decimal_value(raw["Volume"], "Volume", allow_zero=True) if current_volume_mode else None
                    if ask[0] < bid[0]:
                        crossed += 1
                        crossed_digest.update(_canonical_event(
                            symbol, periodicity, year, source_entry["week_index"], source_entry["sha256"], row_ordinal
                        ))
                        continue
                    if previous_usable is not None:
                        slots = int((timestamp - previous_usable) / step)
                        if slots > 1:
                            gap_segments += 1
                            missing_slots += slots - 1
                    previous_usable = timestamp
                    stamp = iso_utc(timestamp)
                    timestamp_digest.update((stamp + "\n").encode("ascii"))
                    writer.writerow([
                        stamp,
                        *(format(value, "f") for value in bid),
                        *(format(value, "f") for value in ask),
                        "PRESENT" if current_volume_mode else "ABSENT_FROM_SOURCE_SCHEMA",
                        format(volume, "f") if volume is not None else "",
                    ])
                    usable += 1
                    first = first or timestamp
                    last = timestamp
            if source_entry["row_count"] == 0:
                raise VaultError("empty frozen source object")
    if clipped:
        raise VaultError("source object contains rows outside its calendar-year shard")
    if observed == 0 or usable == 0 or first is None or last is None:
        raise VaultError("empty direct calendar-year shard")
    payload = {
        "schema_version": f"phase9-exploratory-fxcm-drive-vault-shard-payload-{vault_version}.0.0",
        "vault_version": vault_version,
        "year": year,
        "symbol": symbol,
        "periodicity": periodicity,
        "calendar_clip": {"start_inclusive": iso_utc(year_start), "end_exclusive": iso_utc(year_end)},
        "base_week_count": len(WEEKS),
        "present_week_indices": list(weeks),
        "known_missing_week_indices": [week for week in WEEKS if week not in set(weeks)],
        "source_object_count": len(source_objects),
        "source_objects": source_objects,
        "observed_row_count": observed,
        "usable_row_count": usable,
        "crossed_quote_count": crossed,
        "crossed_quote_event_sha256": crossed_digest.hexdigest(),
        "clipped_outside_year_row_count": clipped,
        "duplicate_count": duplicate,
        "gap_segment_count": gap_segments,
        "missing_nominal_slot_count": missing_slots,
        "canonical_row_count": usable,
        "canonical_first_timestamp_utc": iso_utc(first),
        "canonical_last_timestamp_utc": iso_utc(last),
        "canonical_timestamp_sha256": timestamp_digest.hexdigest(),
        "canonical_csv_sha256": sha256_file(output_path),
        "field_schema": list(CANONICAL_HEADER),
        "volume_status": "PRESENT" if volume_mode else "ABSENT_FROM_SOURCE_SCHEMA",
        "forward_fill_count": 0,
        "interpolation_count": 0,
        "qc_status": "PASS_WITH_CROSSED_ROWS_QUARANTINED" if crossed else "PASS",
    }
    write_canonical_json(shard_dir / "SHARD_PAYLOAD_MANIFEST.json", payload)
    return shard_dir, payload


def iter_canonical(path: Path) -> Iterator[Row]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CANONICAL_HEADER:
            raise VaultError("canonical CSV header mismatch")
        previous = None
        for raw in reader:
            timestamp = datetime.strptime(raw["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if previous is not None and timestamp <= previous:
                raise VaultError("canonical CSV timestamps not increasing")
            previous = timestamp
            bid = tuple(decimal_value(raw[f"bid_{name}"], f"bid_{name}") for name in ("open", "high", "low", "close"))
            ask = tuple(decimal_value(raw[f"ask_{name}"], f"ask_{name}") for name in ("open", "high", "low", "close"))
            status = raw["volume_status"]
            if status == "PRESENT":
                volume = decimal_value(raw["volume"], "volume", allow_zero=True)
            elif status == "ABSENT_FROM_SOURCE_SCHEMA" and raw["volume"] == "":
                volume = None
            else:
                raise VaultError("canonical Volume representation invalid")
            yield Row(timestamp, bid, ask, volume)


def bucket_start(timestamp: datetime, timeframe: str) -> datetime:
    if timeframe == "M5":
        return timestamp.replace(minute=(timestamp.minute // 5) * 5, second=0, microsecond=0)
    if timeframe == "M15":
        return timestamp.replace(minute=(timestamp.minute // 15) * 15, second=0, microsecond=0)
    if timeframe == "M30":
        return timestamp.replace(minute=(timestamp.minute // 30) * 30, second=0, microsecond=0)
    if timeframe == "H1":
        return timestamp.replace(minute=0, second=0, microsecond=0)
    if timeframe == "H4":
        return timestamp.replace(hour=(timestamp.hour // 4) * 4, minute=0, second=0, microsecond=0)
    if timeframe == "D1":
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    if timeframe == "W1":
        day = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        return day - timedelta(days=day.weekday())
    raise VaultError("unknown derived timeframe")


def row_tuple(row: Row) -> tuple[Decimal, ...]:
    return (*row.bid, *row.ask)


def aggregate_tuple(aggregate: Aggregate) -> tuple[Decimal, ...]:
    return (*aggregate.bid, *aggregate.ask)


def derive_qc(m1_path: Path, h1_path: Path, d1_path: Path, year: int) -> dict:
    references = {
        "H1": {row.timestamp: row_tuple(row) for row in iter_canonical(h1_path)},
        "D1": {row.timestamp: row_tuple(row) for row in iter_canonical(d1_path)},
    }
    summaries = {
        timeframe: {
            "candidate_bucket_count": 0, "complete_bucket_count": 0, "dropped_bucket_count": 0,
            "bucket_sha256": hashlib.sha256(), "reference_timestamp_missing_count": 0,
            "reference_exact_match_count": 0, "reference_ohlc_mismatch_count": 0,
        }
        for timeframe in DERIVED_MINUTES
    }
    active: dict[str, Aggregate] = {}
    completed_d1: dict[datetime, Aggregate] = {}

    def finish(timeframe: str, aggregate: Aggregate) -> None:
        summary = summaries[timeframe]
        summary["candidate_bucket_count"] += 1
        expected = DERIVED_MINUTES[timeframe]
        contiguous = aggregate.count == expected and aggregate.last_timestamp - aggregate.first_timestamp == timedelta(minutes=expected - 1)
        reference = references.get(timeframe)
        if reference is not None and aggregate.start not in reference:
            summary["reference_timestamp_missing_count"] += 1
            contiguous = False
        if not contiguous:
            summary["dropped_bucket_count"] += 1
            return
        values = aggregate_tuple(aggregate)
        summary["complete_bucket_count"] += 1
        line = iso_utc(aggregate.start) + "," + ",".join(format(value, "f") for value in values) + "\n"
        summary["bucket_sha256"].update(line.encode("ascii"))
        if reference is not None:
            if values == reference[aggregate.start]:
                summary["reference_exact_match_count"] += 1
            else:
                summary["reference_ohlc_mismatch_count"] += 1
        if timeframe == "D1":
            completed_d1[aggregate.start] = aggregate

    for row in iter_canonical(m1_path):
        for timeframe in DERIVED_MINUTES:
            start = bucket_start(row.timestamp, timeframe)
            current = active.get(timeframe)
            if current is None:
                active[timeframe] = Aggregate.from_row(start, row)
            elif current.start == start:
                current.add(row)
            else:
                finish(timeframe, current)
                active[timeframe] = Aggregate.from_row(start, row)
    for timeframe, aggregate in active.items():
        finish(timeframe, aggregate)

    w1_digest = hashlib.sha256()
    w1_candidates = w1_complete = w1_dropped = 0
    direct_by_week: dict[datetime, list[datetime]] = {}
    for timestamp in references["D1"]:
        direct_by_week.setdefault(bucket_start(timestamp, "W1"), []).append(timestamp)
    for week_start, timestamps in sorted(direct_by_week.items()):
        w1_candidates += 1
        if week_start.year != year or (year == 2010 and week_start.year == 2009) or week_start == datetime(2025, 12, 29, tzinfo=UTC):
            w1_dropped += 1
            continue
        components = [completed_d1.get(timestamp) for timestamp in sorted(timestamps)]
        if not components or any(component is None for component in components):
            w1_dropped += 1
            continue
        typed = [component for component in components if component is not None]
        combined = Aggregate(
            week_start, typed[0].first_timestamp, typed[-1].last_timestamp,
            sum(item.count for item in typed), list(typed[0].bid), list(typed[0].ask), None, False,
        )
        for component in typed[1:]:
            combined.bid[1] = max(combined.bid[1], component.bid[1])
            combined.bid[2] = min(combined.bid[2], component.bid[2])
            combined.bid[3] = component.bid[3]
            combined.ask[1] = max(combined.ask[1], component.ask[1])
            combined.ask[2] = min(combined.ask[2], component.ask[2])
            combined.ask[3] = component.ask[3]
        values = aggregate_tuple(combined)
        w1_digest.update((iso_utc(week_start) + "," + ",".join(format(value, "f") for value in values) + "\n").encode("ascii"))
        w1_complete += 1
    result = {}
    for timeframe, summary in summaries.items():
        result[timeframe] = {
            key: (value.hexdigest() if hasattr(value, "hexdigest") else value)
            for key, value in summary.items()
        }
    result["W1"] = {
        "candidate_bucket_count": w1_candidates,
        "complete_bucket_count": w1_complete,
        "dropped_bucket_count": w1_dropped,
        "bucket_sha256": w1_digest.hexdigest(),
        "completeness_reference": "DIRECT_D1_TIMESTAMP_SET",
        "year_ownership": "UTC_MONDAY_BUCKET_OPEN_YEAR",
    }
    result["provider_schedule_claimed"] = False
    result["forward_fill_count"] = 0
    result["interpolation_count"] = 0
    result["batch6_compatibility_passed"] = (
        result["H1"]["reference_timestamp_missing_count"] == 0
        and result["H1"]["reference_ohlc_mismatch_count"] == 0
        and result["D1"]["reference_timestamp_missing_count"] == 0
        and result["D1"]["reference_ohlc_mismatch_count"] == 0
    )
    return result


def make_archive(shard_dir: Path, output_path: Path, weeks: tuple[int, ...] = WEEKS) -> str:
    if output_path.exists() or output_path.is_symlink():
        raise VaultError("archive destination must be new")
    tar_path = output_path.with_suffix("")
    members = [
        ("SHARD_PAYLOAD_MANIFEST.json", shard_dir / "SHARD_PAYLOAD_MANIFEST.json"),
        ("canonical/prices.csv", shard_dir / "canonical/prices.csv"),
        *[(f"source/{week:02d}.csv.gz", shard_dir / "source" / f"{week:02d}.csv.gz") for week in weeks],
    ]
    with tarfile.open(tar_path, "x", format=tarfile.USTAR_FORMAT) as archive:
        for name, path in members:
            validate_safe_member(name)
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                raise VaultError("unsafe archive input")
            info = tarfile.TarInfo(name)
            info.size = path.stat().st_size
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    subprocess.run(
        ["zstd", "-T1", "-19", "--no-progress", "--force", "-o", str(output_path), str(tar_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"},
    )
    tar_path.unlink()
    return sha256_file(output_path)


def acquire_year(args: argparse.Namespace) -> dict:
    contract, partitions, _, _ = load_frozen_contracts(
        args.acquisition_contract, args.partitions_contract, args.manifest_schema, args.formal_boundary
    )
    require_exact_confirmations(
        contract, args.confirmation, args.usage_confirmation, args.formal_acknowledgement, "acquisition"
    )
    if args.year not in YEARS:
        raise VaultError("year outside frozen acquisition scope")
    if args.run_attempt != 1:
        raise VaultError("only first run attempt is authorized")
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise VaultError("work directory must not exist")
    args.work_dir.mkdir(parents=True)
    drive = GoogleDrivePrivate()
    drive.verify_root(contract["drive_custody"]["root_folder_name"])
    partition = partition_for_year(partitions, args.year)
    stage_name = f"v1-staging-run-{args.run_id}-year-{args.year}"
    stage = drive.create_folder_new(
        contract["drive_custody"]["root_folder_id"], stage_name,
        {"vault_version": "v1", "run_id": str(args.run_id), "year": str(args.year), "state": "UNSEALED"},
    )
    opener = urllib.request.build_opener(RejectRedirects())
    contract_hashes = contract_sha_bundle((
        args.acquisition_contract, args.partitions_contract, args.manifest_schema, args.formal_boundary
    ))
    shard_records: list[dict] = []
    derived_records: list[dict] = []
    zstd_version = subprocess.run(["zstd", "--version"], check=True, capture_output=True, text=True).stdout.strip()
    for symbol in SYMBOLS:
        symbol_dir = args.work_dir / symbol
        symbol_dir.mkdir()
        payloads: dict[str, dict] = {}
        shard_dirs: dict[str, Path] = {}
        for periodicity in DIRECT_PERIODICITIES:
            shard_dir, payload = process_direct_shard(contract, args.year, symbol, periodicity, symbol_dir, opener)
            shard_dirs[periodicity] = shard_dir
            payloads[periodicity] = payload
        derived = derive_qc(
            shard_dirs["m1"] / "canonical/prices.csv",
            shard_dirs["H1"] / "canonical/prices.csv",
            shard_dirs["D1"] / "canonical/prices.csv",
            args.year,
        )
        derived_records.append({"symbol": symbol, **derived})
        for periodicity in DIRECT_PERIODICITIES:
            archive_name = f"fxcm-{symbol}-{args.year}-{periodicity}.tar.zst"
            archive_path = symbol_dir / archive_name
            archive_sha = make_archive(shard_dirs[periodicity], archive_path)
            archive_bytes = archive_path.stat().st_size
            app_properties = {
                "vault_version": "v1", "run_id": str(args.run_id), "year": str(args.year),
                "symbol": symbol, "periodicity": periodicity, "sha256": archive_sha,
                "partition": partition["id"], "state": "UNSEALED",
            }
            uploaded = drive.upload_file_new(stage["id"], archive_path, archive_name, "application/zstd", app_properties)
            verify_path = symbol_dir / f"verify-{archive_name}"
            drive.download_verify(uploaded["id"], verify_path, archive_bytes, archive_sha)
            verify_path.unlink()
            payload = payloads[periodicity]
            shard_records.append({
                "vault_version": "v1",
                "contract_sha256": contract_hashes[args.acquisition_contract.name],
                "partitions_sha256": contract_hashes[args.partitions_contract.name],
                "run_id": str(args.run_id), "run_attempt": args.run_attempt, "head_sha": args.head_sha,
                "year": args.year, "symbol": symbol, "periodicity": periodicity,
                "partition_id": partition["id"], "archive_name": archive_name,
                "archive_sha256": archive_sha, "archive_bytes": archive_bytes,
                "canonical_row_count": payload["canonical_row_count"],
                "canonical_first_timestamp_utc": payload["canonical_first_timestamp_utc"],
                "canonical_last_timestamp_utc": payload["canonical_last_timestamp_utc"],
                "canonical_timestamp_sha256": payload["canonical_timestamp_sha256"],
                "canonical_csv_sha256": payload["canonical_csv_sha256"],
                "source_object_count": payload["source_object_count"], "source_objects": payload["source_objects"],
                "observed_row_count": payload["observed_row_count"], "usable_row_count": payload["usable_row_count"],
                "crossed_quote_count": payload["crossed_quote_count"],
                "crossed_quote_event_sha256": payload["crossed_quote_event_sha256"],
                "duplicate_count": payload["duplicate_count"], "gap_segment_count": payload["gap_segment_count"],
                "missing_nominal_slot_count": payload["missing_nominal_slot_count"],
                "volume_status": payload["volume_status"], "field_schema": payload["field_schema"],
                "qc_status": payload["qc_status"], "drive_parent_role": "RUN_YEAR_STAGING",
                "drive_upload_redownload_sha256_verified": True,
                "drive_file_id": uploaded["id"], "drive_parent_id": stage["id"],
            })
            archive_path.unlink()
        shutil.rmtree(symbol_dir)
    if len(shard_records) != 84 or len({(row["symbol"], row["periodicity"]) for row in shard_records}) != 84:
        raise VaultError("year shard inventory mismatch")
    year_manifest = {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-year-manifest-v1.0.0",
        "status": "YEAR_STAGED_PRIVATE_DRIVE_REDOWNLOAD_VERIFIED_UNSEALED",
        "vault_version": "v1", "run_id": str(args.run_id), "run_attempt": args.run_attempt,
        "head_sha": args.head_sha, "year": args.year, "partition_id": partition["id"],
        "contract_sha256": contract_hashes,
        "source_object_count": 28 * 3 * 52,
        "shard_count": len(shard_records),
        "zstd_version": zstd_version,
        "shards_sha256": canonical_sha256(shard_records),
        "derived_qc_sha256": canonical_sha256(derived_records),
        "batch6_compatibility_passed": all(row["batch6_compatibility_passed"] for row in derived_records),
        "provider_schedule_claimed": False,
        "forward_fill_count": 0, "interpolation_count": 0,
        "formal_phase9_authorization_effect": False, "count_only_authorized": False,
        "research_outcomes_calculated": False, "outcome_fields": [],
        "stage_folder_id": stage["id"], "shards": shard_records, "derived_qc": derived_records,
    }
    year_manifest_path = args.work_dir / "YEAR_MANIFEST.json"
    write_canonical_json(year_manifest_path, year_manifest)
    year_sha = sha256_file(year_manifest_path)
    uploaded_manifest = drive.upload_file_new(
        stage["id"], year_manifest_path, "YEAR_MANIFEST.json", "application/json",
        {"vault_version": "v1", "run_id": str(args.run_id), "year": str(args.year), "sha256": year_sha, "state": "YEAR_COMPLETE_UNSEALED"},
    )
    verify_manifest = args.work_dir / "verify-YEAR_MANIFEST.json"
    drive.download_verify(uploaded_manifest["id"], verify_manifest, year_manifest_path.stat().st_size, year_sha)
    verify_manifest.unlink()
    return {
        "year": args.year, "shard_count": 84, "source_object_count": 4368,
        "batch6_compatibility_passed": year_manifest["batch6_compatibility_passed"],
        "year_manifest_sha256": year_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-contract", type=Path, required=True)
    parser.add_argument("--partitions-contract", type=Path, required=True)
    parser.add_argument("--manifest-schema", type=Path, required=True)
    parser.add_argument("--formal-boundary", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--formal-acknowledgement", required=True)
    args = parser.parse_args()
    runner_temp = os.environ.get("RUNNER_TEMP")
    expected_name = f"fxcm-vault-year-{args.year}-{args.run_id}-{args.run_attempt}"
    if not runner_temp or args.work_dir.parent.resolve() != Path(runner_temp).resolve() or args.work_dir.name != expected_name:
        raise VaultError("work directory is outside the exact ephemeral runner boundary")
    try:
        summary = acquire_year(args)
        print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        if args.work_dir.exists() and not args.work_dir.is_symlink():
            shutil.rmtree(args.work_dir)


if __name__ == "__main__":
    raise SystemExit(main())
