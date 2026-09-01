#!/usr/bin/env python3
"""Streaming, return-blind validation for the frozen Phase 9 48-series corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import zip_longest
from pathlib import Path
from typing import Iterator


UTC = timezone.utc
START = datetime(2013, 1, 1, tzinfo=UTC)
END = {"M15": datetime(2019, 8, 28, tzinfo=UTC), "H1": datetime(2019, 8, 1, tzinfo=UTC)}
STEP = {"M15": timedelta(minutes=15), "H1": timedelta(hours=1)}
INSTRUMENTS = (
    "AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY",
    "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD",
)
SIDES = ("bid", "ask")
TIMEFRAMES = ("M15", "H1")
FROZEN_GROUPS = {
    "FX8": INSTRUMENTS[:8],
    "METALS2": INSTRUMENTS[8:10],
    "ENERGY2": INSTRUMENTS[10:12],
}
CSV_HEADER = b"timestamp,open,high,low,close,volume\n"
TIMESTAMP_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_METADATA = re.compile(r"^[A-Za-z0-9._:/+-]{1,160}$")
CONFIRMATION = "RUN_PHASE9_ACTUAL_FULL_QC_AFTER_AUTHORIZED_ACQUISITION"
CANONICAL_ALLOWLIST = Path(
    "research/phase9-hypothesis-redesign-20260828/spec/"
    "provider_schedule_exact_allowlist.frozen.json"
)
_PINNED_RAW: dict[str, tuple] = {}
_PINNED_SCHEDULE: dict[str, tuple] = {}
_PINNED_RAW_ROOT: tuple | None = None
_PINNED_SCHEDULE_ROOT: tuple | None = None


class ActualQcError(ValueError):
    pass


def stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
        stat.S_IMODE(info.st_mode), info.st_uid, info.st_nlink,
    )


def require_pinned_root(path: Path, expected: tuple | None, label: str) -> None:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat_identity(info) != expected:
        raise ActualQcError(f"{label} root changed after custody pin")


@dataclass(frozen=True)
class SeriesSpec:
    instrument: str
    timeframe: str
    side: str

    @property
    def filename(self) -> str:
        return f"{self.instrument}_{self.timeframe}_{self.side}.csv"

    @property
    def schedule_filename(self) -> str:
        return f"{self.instrument}_{self.timeframe}.timestamps"


@dataclass(frozen=True)
class Row:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


SPECS = tuple(
    SeriesSpec(instrument, timeframe, side)
    for instrument in INSTRUMENTS for timeframe in TIMEFRAMES for side in SIDES
)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str, timeframe: str) -> datetime:
    if not TIMESTAMP_PATTERN.fullmatch(value):
        raise ActualQcError("Timestamp must use exact UTC second precision with Z suffix")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    step_seconds = int(STEP[timeframe].total_seconds())
    if int(parsed.timestamp()) % step_seconds != 0:
        raise ActualQcError("Timestamp is not aligned to the frozen timeframe")
    if parsed < START or parsed >= END[timeframe]:
        raise ActualQcError("Timestamp is outside the frozen series interval")
    return parsed


def parse_row(raw: bytes, spec: SeriesSpec) -> Row:
    try:
        line = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ActualQcError("CSV must be strict ASCII-compatible UTF-8") from error
    if not line.endswith("\n") or line.endswith("\r\n"):
        raise ActualQcError("CSV rows must use LF termination")
    fields = line[:-1].split(",")
    if len(fields) != 6:
        raise ActualQcError("CSV row must contain exactly six fields")
    try:
        values = tuple(Decimal(item) for item in fields[1:])
    except InvalidOperation as error:
        raise ActualQcError("CSV numeric field is malformed") from error
    if not all(value.is_finite() for value in values):
        raise ActualQcError("CSV numeric fields must be finite")
    open_value, high, low, close, volume = values
    if min(open_value, high, low, close) <= 0 or volume < 0:
        raise ActualQcError("Prices must be positive and volume nonnegative")
    if high < max(open_value, close) or low > min(open_value, close) or high < low:
        raise ActualQcError("Invalid OHLC geometry")
    return Row(parse_timestamp(fields[0], spec.timeframe), open_value, high, low, close, volume)


def iter_rows(path: Path, spec: SeriesSpec) -> Iterator[Row]:
    if _PINNED_RAW_ROOT is not None:
        require_pinned_root(path.parent, _PINNED_RAW_ROOT, "Raw")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        before = os.fstat(handle.fileno())
        expected = _PINNED_RAW.get(path.name)
        identity = stat_identity(before)
        if expected is not None and identity != expected[:-1]:
            raise ActualQcError(f"Raw identity changed after custody pin: {spec.filename}")
        digest = hashlib.sha256()
        header = handle.readline()
        digest.update(header)
        if header != CSV_HEADER:
            raise ActualQcError(f"CSV header mismatch: {spec.filename}")
        previous = None
        for raw in handle:
            digest.update(raw)
            row = parse_row(raw, spec)
            if previous is not None and row.timestamp <= previous:
                raise ActualQcError(f"Timestamps must be strictly increasing: {spec.filename}")
            previous = row.timestamp
            yield row
        after = os.fstat(handle.fileno())
        final_identity = stat_identity(after)
        if final_identity != identity:
            raise ActualQcError(f"Raw file changed during streaming read: {spec.filename}")
        if expected is not None and digest.hexdigest() != expected[-1]:
            raise ActualQcError(f"Raw content changed after custody pin: {spec.filename}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_series(path: Path, spec: SeriesSpec) -> dict:
    rows = 0
    first = None
    last = None
    nominal_gap_slots = 0
    previous = None
    timestamp_digest = hashlib.sha256()
    for row in iter_rows(path, spec):
        if previous is not None:
            difference = row.timestamp - previous
            if difference > STEP[spec.timeframe]:
                nominal_gap_slots += int(difference / STEP[spec.timeframe]) - 1
        previous = row.timestamp
        first = first or row.timestamp
        last = row.timestamp
        timestamp_digest.update((iso(row.timestamp) + "\n").encode("ascii"))
        rows += 1
    if rows == 0:
        raise ActualQcError(f"Empty source series: {spec.filename}")
    pinned = _PINNED_RAW.get(path.name)
    return {
        "instrument": spec.instrument,
        "timeframe": spec.timeframe,
        "side": spec.side,
        "filename": spec.filename,
        "sha256": pinned[-1] if pinned is not None else sha256_file(path),
        "bytes": pinned[2] if pinned is not None else path.stat().st_size,
        "row_count": rows,
        "first_timestamp": iso(first),
        "last_timestamp": iso(last),
        "timestamp_sha256": timestamp_digest.hexdigest(),
        "nominal_gap_slots_unclassified_until_schedule_match": nominal_gap_slots,
    }


def validate_bid_ask(raw_dir: Path, instrument: str, timeframe: str) -> dict:
    bid_spec = SeriesSpec(instrument, timeframe, "bid")
    ask_spec = SeriesSpec(instrument, timeframe, "ask")
    count = 0
    volume_mismatch_count = 0
    for bid, ask in zip_longest(
        iter_rows(raw_dir / bid_spec.filename, bid_spec),
        iter_rows(raw_dir / ask_spec.filename, ask_spec),
    ):
        if bid is None or ask is None or bid.timestamp != ask.timestamp:
            raise ActualQcError(f"BID/ASK timestamp sequence mismatch: {instrument} {timeframe}")
        if ask.open < bid.open:
            raise ActualQcError(f"ASK open below BID: {instrument} {timeframe} {iso(bid.timestamp)}")
        if ask.volume != bid.volume:
            volume_mismatch_count += 1
        count += 1
    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "matched_timestamp_count": count,
        "bid_ask_volume_mismatch_count": volume_mismatch_count,
        "canonical_tick_volume_side": "BID",
    }


def reconcile_m15_h1(raw_dir: Path, instrument: str, side: str) -> dict:
    m15_spec = SeriesSpec(instrument, "M15", side)
    h1_spec = SeriesSpec(instrument, "H1", side)
    m15 = iter(iter_rows(raw_dir / m15_spec.filename, m15_spec))
    h1 = iter(iter_rows(raw_dir / h1_spec.filename, h1_spec))
    current_m15 = next(m15, None)
    current_h1 = next(h1, None)
    eligible = 0
    source_missing = 0
    direct_h1_missing_with_complete_m15 = 0
    mismatch = 0
    while current_m15 is not None and current_m15.timestamp < END["H1"]:
        bucket_open = current_m15.timestamp.replace(minute=0, second=0, microsecond=0)
        bucket = []
        while current_m15 is not None and current_m15.timestamp < bucket_open + timedelta(hours=1):
            bucket.append(current_m15)
            current_m15 = next(m15, None)
        expected = [bucket_open + timedelta(minutes=15 * index) for index in range(4)]
        while current_h1 is not None and current_h1.timestamp < bucket_open:
            source_missing += 1
            current_h1 = next(h1, None)
        if current_h1 is None or current_h1.timestamp > bucket_open:
            if [row.timestamp for row in bucket] == expected:
                direct_h1_missing_with_complete_m15 += 1
            continue
        hour = current_h1
        current_h1 = next(h1, None)
        if [row.timestamp for row in bucket] != expected:
            source_missing += 1
            continue
        rebuilt = {
            "open": bucket[0].open,
            "high": max(row.high for row in bucket),
            "low": min(row.low for row in bucket),
            "close": bucket[-1].close,
            "volume": sum((row.volume for row in bucket), Decimal(0)),
        }
        if any(rebuilt[field] != getattr(hour, field) for field in rebuilt):
            mismatch += 1
        else:
            eligible += 1
    while current_h1 is not None:
        source_missing += 1
        current_h1 = next(h1, None)
    for _ in m15:
        pass
    if mismatch:
        raise ActualQcError(f"M15/H1 value mismatch: {instrument} {side} count={mismatch}")
    return {
        "instrument": instrument,
        "side": side,
        "eligible_match_count": eligible,
        "source_missing_count": source_missing,
        "direct_h1_missing_with_complete_m15_count": direct_h1_missing_with_complete_m15,
        "value_mismatch_count": 0,
    }


def validate_raw_set(raw_dir: Path) -> None:
    global _PINNED_RAW_ROOT
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise ActualQcError("Raw root must be a real directory")
    root_info = raw_dir.lstat()
    if root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700:
        raise ActualQcError("Raw root must be runner-owned with mode 0700")
    expected = {spec.filename for spec in SPECS}
    actual = {path.name for path in raw_dir.iterdir()}
    if actual != expected or len(actual) != 48 or len({name.casefold() for name in actual}) != 48:
        raise ActualQcError("Raw root differs from the exact canonical 48-file set")
    pinned: dict[str, tuple] = {}
    for path in raw_dir.iterdir():
        info = path.lstat()
        if (
            path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ActualQcError("Raw entries must be runner-owned single-link 0600 regular files")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            digest = hashlib.sha256()
            while True:
                block = os.read(descriptor, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        before_identity = stat_identity(before)
        after_identity = stat_identity(after)
        lstat_identity = stat_identity(info)
        if before_identity != after_identity or before_identity != lstat_identity:
            raise ActualQcError("Raw entry changed while custody identity was pinned")
        pinned[path.name] = (*before_identity, digest.hexdigest())
    _PINNED_RAW.clear()
    _PINNED_RAW.update(pinned)
    _PINNED_RAW_ROOT = stat_identity(root_info)


def read_regular_snapshot(path: Path) -> tuple[bytes, tuple]:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ActualQcError("Metadata input must be a regular file")
        chunks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = stat_identity(before)
    identity_after = stat_identity(after)
    if identity_before != identity_after:
        raise ActualQcError("Metadata input changed while it was read")
    payload = b"".join(chunks)
    return payload, (*identity_before, hashlib.sha256(payload).hexdigest())


def read_regular_bytes(path: Path) -> bytes:
    return read_regular_snapshot(path)[0]


def validate_schedule_contract(manifest: Path | dict) -> dict:
    if isinstance(manifest, Path):
        value = json.loads(read_regular_bytes(manifest).decode("utf-8"))
    else:
        value = manifest
    required = {
        "schema_version", "status", "source", "provider_version", "observed_at_utc",
        "timezone", "bar_timestamp", "coverage_start_inclusive",
        "coverage_end_exclusive_by_timeframe", "complete_interval_inventory",
        "derived_from_raw_prices", "inventory_sha256", "series",
    }
    if set(value) != required:
        raise ActualQcError("Provider schedule manifest schema mismatch")
    if value["schema_version"] != "phase9-provider-schedule-inventory-v1.0":
        raise ActualQcError("Provider schedule schema version mismatch")
    if value["status"] != "FROZEN_PROVIDER_SCHEDULE_INVENTORY":
        raise ActualQcError("Provider schedule is not separately frozen")
    if value["timezone"] != "UTC" or value["bar_timestamp"] != "BAR_OPEN":
        raise ActualQcError("Provider schedule UTC/bar-open convention mismatch")
    if not isinstance(value["source"], str) or not SAFE_METADATA.fullmatch(value["source"]):
        raise ActualQcError("Provider schedule source is malformed")
    if not isinstance(value["provider_version"], str) or not SAFE_METADATA.fullmatch(value["provider_version"]):
        raise ActualQcError("Provider schedule version is malformed")
    if value["provider_version"] == "NO_VERSION_AVAILABLE_YET":
        raise ActualQcError("Provider schedule source/version is missing")
    if not isinstance(value["observed_at_utc"], str) or not TIMESTAMP_PATTERN.fullmatch(value["observed_at_utc"]):
        raise ActualQcError("Provider schedule observation time is malformed")
    if value["coverage_start_inclusive"] != iso(START) or value["coverage_end_exclusive_by_timeframe"] != {
        "M15": iso(END["M15"]), "H1": iso(END["H1"])
    }:
        raise ActualQcError("Provider schedule does not claim the complete frozen intervals")
    if value["complete_interval_inventory"] is not True or value["derived_from_raw_prices"] is not False:
        raise ActualQcError("Provider schedule must be complete and independent of raw prices")
    if not HEX64.fullmatch(value["inventory_sha256"]):
        raise ActualQcError("Provider schedule inventory SHA-256 is malformed")
    expected = {f"{instrument}_{timeframe}.timestamps" for instrument in INSTRUMENTS for timeframe in TIMEFRAMES}
    rows = value["series"]
    if not isinstance(rows, list) or len(rows) != 24 or {row.get("path") for row in rows} != expected:
        raise ActualQcError("Provider schedule manifest must freeze exactly 24 files")
    for row in rows:
        if set(row) != {"path", "sha256", "scheduled_slot_count", "first_timestamp", "last_timestamp"}:
            raise ActualQcError("Provider schedule series schema mismatch")
        if not HEX64.fullmatch(row["sha256"]) or not isinstance(row["scheduled_slot_count"], int) or row["scheduled_slot_count"] <= 0:
            raise ActualQcError("Provider schedule series identity is malformed")
    return value


def git_output(repo_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments], cwd=repo_root, check=False, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise ActualQcError(f"Git anchor verification failed: {' '.join(arguments)}")
    return result.stdout


def validate_schedule_allowlist(
    allowlist_path: Path, manifest_sha256: str, repo_root: Path
) -> dict:
    canonical = repo_root / CANONICAL_ALLOWLIST
    if allowlist_path.resolve(strict=True) != canonical.resolve(strict=True):
        raise ActualQcError("Provider schedule allowlist must use the canonical repository path")
    top = Path(git_output(repo_root, "rev-parse", "--show-toplevel").decode().strip())
    if top.resolve() != repo_root.resolve():
        raise ActualQcError("Repository root differs from the Git toplevel")
    allowlist_bytes = read_regular_bytes(allowlist_path)
    value = json.loads(allowlist_bytes.decode("utf-8"))
    required = {
        "schema_version", "status", "source_run_id", "source_head_sha", "source_artifact_id",
        "source_artifact_zip_sha256", "inventory_manifest_sha256", "freeze_parent_sha",
        "same_run_self_authorization_used",
    }
    if set(value) != required:
        raise ActualQcError("Provider schedule allowlist schema mismatch")
    if value["schema_version"] != "phase9-provider-schedule-exact-allowlist-v1.0":
        raise ActualQcError("Provider schedule allowlist version mismatch")
    if value["status"] != "SEPARATE_COMMIT_EXACT_ALLOWLIST_FROZEN":
        raise ActualQcError("Provider schedule allowlist is not frozen")
    if not isinstance(value["source_run_id"], int) or value["source_run_id"] <= 0:
        raise ActualQcError("Provider schedule source Run ID is malformed")
    if not isinstance(value["source_artifact_id"], int) or value["source_artifact_id"] <= 0:
        raise ActualQcError("Provider schedule source Artifact ID is malformed")
    for field in (
        "source_head_sha", "source_artifact_zip_sha256", "inventory_manifest_sha256", "freeze_parent_sha"
    ):
        expected_length = 40 if field in {"source_head_sha", "freeze_parent_sha"} else 64
        item = value[field]
        if not isinstance(item, str) or len(item) != expected_length or any(c not in "0123456789abcdef" for c in item):
            raise ActualQcError(f"Provider schedule allowlist identity malformed: {field}")
    if value["same_run_self_authorization_used"] is not False:
        raise ActualQcError("Provider schedule same-run self-authorization is prohibited")
    if manifest_sha256 != value["inventory_manifest_sha256"]:
        raise ActualQcError("Provider schedule manifest differs from the separate-commit exact allowlist")
    source = value["source_head_sha"]
    freeze_parent = value["freeze_parent_sha"]
    current = git_output(repo_root, "rev-parse", "HEAD").decode().strip()
    git_output(repo_root, "cat-file", "-e", f"{source}^{{commit}}")
    git_output(repo_root, "cat-file", "-e", f"{freeze_parent}^{{commit}}")
    git_output(repo_root, "merge-base", "--is-ancestor", source, freeze_parent)
    last_change = git_output(
        repo_root, "log", "-1", "--format=%H", "--", CANONICAL_ALLOWLIST.as_posix()
    ).decode().strip()
    if not last_change or last_change == current:
        raise ActualQcError("Canonical allowlist must be frozen in a strict ancestor commit")
    git_output(repo_root, "merge-base", "--is-ancestor", last_change, current)
    actual_parent = git_output(repo_root, "rev-parse", f"{last_change}^").decode().strip()
    if actual_parent != freeze_parent:
        raise ActualQcError("freeze_parent_sha is not the parent of the allowlist freeze commit")
    frozen_bytes = git_output(repo_root, "show", f"{last_change}:{CANONICAL_ALLOWLIST.as_posix()}")
    if frozen_bytes != allowlist_bytes:
        raise ActualQcError("Canonical allowlist differs from its frozen Git object")
    if git_output(repo_root, "status", "--porcelain", "--", CANONICAL_ALLOWLIST.as_posix()).strip():
        raise ActualQcError("Canonical allowlist is modified or untracked")
    return value


def iter_schedule(path: Path, timeframe: str) -> Iterator[datetime]:
    previous = None
    if _PINNED_SCHEDULE_ROOT is not None:
        require_pinned_root(path.parent, _PINNED_SCHEDULE_ROOT, "Provider schedule")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rt", encoding="ascii", newline="", closefd=True) as handle:
        before = os.fstat(handle.fileno())
        expected = _PINNED_SCHEDULE.get(path.name)
        identity = stat_identity(before)
        if expected is not None and identity != expected[:-1]:
            raise ActualQcError("Provider schedule identity changed after custody pin")
        digest = hashlib.sha256()
        for line in handle:
            digest.update(line.encode("ascii"))
            if not line.endswith("\n") or line.endswith("\r\n"):
                raise ActualQcError("Provider schedule lines must use LF termination")
            value = parse_timestamp(line[:-1], timeframe)
            if previous is not None and value <= previous:
                raise ActualQcError("Provider schedule timestamps must be strictly increasing")
            previous = value
            yield value
        after = os.fstat(handle.fileno())
        if stat_identity(after) != identity:
            raise ActualQcError("Provider schedule changed during streaming read")
        if expected is not None and digest.hexdigest() != expected[-1]:
            raise ActualQcError("Provider schedule content changed after custody pin")


def validate_schedule_files(manifest: dict, schedule_dir: Path) -> dict[str, Path]:
    global _PINNED_SCHEDULE_ROOT
    if schedule_dir.is_symlink() or not schedule_dir.is_dir():
        raise ActualQcError("Provider schedule root must be a real directory")
    root_info = schedule_dir.lstat()
    if root_info.st_uid != os.getuid() or stat.S_IMODE(root_info.st_mode) != 0o700:
        raise ActualQcError("Provider schedule root must be runner-owned with mode 0700")
    expected = {f"{instrument}_{timeframe}.timestamps" for instrument in INSTRUMENTS for timeframe in TIMEFRAMES}
    entries = list(schedule_dir.iterdir())
    if {path.name for path in entries} != expected or len(entries) != 24:
        raise ActualQcError("Provider schedule root differs from the exact 24-file set")
    rows_by_path = {row["path"]: row for row in manifest["series"]}
    paths: dict[str, Path] = {}
    pinned: dict[str, tuple] = {}
    inventory_digest = hashlib.sha256()
    for name in sorted(expected):
        path = schedule_dir / name
        info = path.lstat()
        if (
            path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise ActualQcError("Provider schedule entries must be runner-owned single-link 0600 files")
        instrument, timeframe = name.removesuffix(".timestamps").rsplit("_", 1)
        payload, snapshot = read_regular_snapshot(path)
        if snapshot[:-1] != stat_identity(info):
            raise ActualQcError("Provider schedule entry changed before custody pin")
        pinned[name] = snapshot
        count = 0
        first = None
        last = None
        previous = None
        try:
            lines = payload.decode("ascii").splitlines(keepends=True)
        except UnicodeDecodeError as error:
            raise ActualQcError("Provider schedule must be ASCII") from error
        for line in lines:
            if not line.endswith("\n") or line.endswith("\r\n"):
                raise ActualQcError("Provider schedule lines must use LF termination")
            timestamp = parse_timestamp(line[:-1], timeframe)
            if previous is not None and timestamp <= previous:
                raise ActualQcError("Provider schedule timestamps must be strictly increasing")
            previous = timestamp
            first = first or timestamp
            last = timestamp
            count += 1
        if count == 0:
            raise ActualQcError("Provider schedule series must not be empty")
        nominal = int((END[timeframe] - START) / STEP[timeframe])
        if count < (nominal * 3) // 5:
            raise ActualQcError("Provider schedule is implausibly sparse for the frozen full interval")
        if first > START + timedelta(days=7) or last < END[timeframe] - timedelta(days=7):
            raise ActualQcError("Provider schedule does not span the frozen full interval")
        row = rows_by_path[name]
        digest = snapshot[-1]
        if count != row["scheduled_slot_count"] or digest != row["sha256"]:
            raise ActualQcError("Provider schedule file identity differs from its frozen manifest")
        if iso(first) != row["first_timestamp"] or iso(last) != row["last_timestamp"]:
            raise ActualQcError("Provider schedule first/last timestamp mismatch")
        inventory_digest.update(f"{digest}  {name}\n".encode("ascii"))
        paths[name] = path
    if inventory_digest.hexdigest() != manifest["inventory_sha256"]:
        raise ActualQcError("Provider schedule aggregate inventory SHA-256 mismatch")
    _PINNED_SCHEDULE.clear()
    _PINNED_SCHEDULE.update(pinned)
    _PINNED_SCHEDULE_ROOT = stat_identity(root_info)
    return paths


def compare_series_to_schedule(raw_path: Path, spec: SeriesSpec, schedule_path: Path) -> dict:
    raw = iter(iter_rows(raw_path, spec))
    current = next(raw, None)
    expected_count = 0
    observed_count = 0
    missing_count = 0
    missing_segments = 0
    missing_digest = hashlib.sha256()
    previous_missing = None
    for scheduled in iter_schedule(schedule_path, spec.timeframe):
        expected_count += 1
        if current is not None and current.timestamp < scheduled:
            raise ActualQcError(f"Raw timestamp outside provider schedule: {spec.filename}")
        if current is not None and current.timestamp == scheduled:
            observed_count += 1
            current = next(raw, None)
            previous_missing = None
        else:
            missing_count += 1
            missing_digest.update((iso(scheduled) + "\n").encode("ascii"))
            if previous_missing is None or scheduled - previous_missing != STEP[spec.timeframe]:
                missing_segments += 1
            previous_missing = scheduled
    if current is not None:
        raise ActualQcError(f"Raw timestamp after provider schedule ended: {spec.filename}")
    return {
        "filename": spec.filename,
        "expected_scheduled_slots": expected_count,
        "observed_slots": observed_count,
        "scheduled_missing_slots": missing_count,
        "missing_segment_count": missing_segments,
        "missing_timestamp_sha256": missing_digest.hexdigest(),
        "classification_coverage": 1.0,
        "forward_fill_count": 0,
    }


def iter_schedule_presence(raw_path: Path, spec: SeriesSpec, schedule_path: Path) -> Iterator[tuple[datetime, Row | None]]:
    raw = iter(iter_rows(raw_path, spec))
    current = next(raw, None)
    for scheduled in iter_schedule(schedule_path, spec.timeframe):
        if current is not None and current.timestamp < scheduled:
            raise ActualQcError(f"Raw timestamp outside provider schedule: {spec.filename}")
        if current is not None and current.timestamp == scheduled:
            yield scheduled, current
            current = next(raw, None)
        else:
            yield scheduled, None
    if current is not None:
        raise ActualQcError(f"Raw timestamp after provider schedule ended: {spec.filename}")


def derived_bucket_open(value: datetime, hours: int) -> datetime:
    if hours == 24:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(hour=(value.hour // hours) * hours, minute=0, second=0, microsecond=0)


def iter_complete_buckets(
    raw_path: Path, spec: SeriesSpec, schedule_path: Path, hours: int
) -> Iterator[tuple[datetime, Row]]:
    if spec.timeframe != "H1" or hours not in (4, 24):
        raise ActualQcError("Derived buckets require canonical H1 and frozen H4/D1 sizes")
    current_bucket = None
    expected = 0
    scheduled_times: list[datetime] = []
    present_rows: list[Row] = []
    for scheduled, row in iter_schedule_presence(raw_path, spec, schedule_path):
        bucket = derived_bucket_open(scheduled, hours)
        if current_bucket is not None and bucket != current_bucket:
            required = [current_bucket + timedelta(hours=index) for index in range(hours)]
            if expected == hours and scheduled_times == required and len(present_rows) == hours:
                yield current_bucket, Row(
                    current_bucket, present_rows[0].open,
                    max(row.high for row in present_rows),
                    min(row.low for row in present_rows),
                    present_rows[-1].close,
                    sum((row.volume for row in present_rows), Decimal(0)),
                )
            current_bucket = bucket
            expected = 0
            scheduled_times = []
            present_rows = []
        if current_bucket is None:
            current_bucket = bucket
        expected += 1
        scheduled_times.append(scheduled)
        if row is not None:
            present_rows.append(row)
    if current_bucket is not None:
        required = [current_bucket + timedelta(hours=index) for index in range(hours)]
        if expected == hours and scheduled_times == required and len(present_rows) == hours:
            yield current_bucket, Row(
                current_bucket, present_rows[0].open,
                max(row.high for row in present_rows),
                min(row.low for row in present_rows),
                present_rows[-1].close,
                sum((row.volume for row in present_rows), Decimal(0)),
            )


def iter_complete_bucket_opens(
    raw_path: Path, spec: SeriesSpec, schedule_path: Path, hours: int
) -> Iterator[datetime]:
    for bucket_open, _ in iter_complete_buckets(raw_path, spec, schedule_path, hours):
        yield bucket_open


def derived_bucket_audit(raw_path: Path, spec: SeriesSpec, schedule_path: Path, hours: int) -> dict:
    complete: set[datetime] = set()
    timestamp_digest = hashlib.sha256()
    ohlcv_digest = hashlib.sha256()
    for value, row in iter_complete_buckets(raw_path, spec, schedule_path, hours):
        complete.add(value)
        timestamp_digest.update((iso(value) + "\n").encode("ascii"))
        canonical = ",".join(
            [iso(value)] + [format(getattr(row, field), "f") for field in ("open", "high", "low", "close", "volume")]
        ) + "\n"
        ohlcv_digest.update(canonical.encode("ascii"))
    all_buckets = {derived_bucket_open(value, hours) for value in iter_schedule(schedule_path, "H1")}
    return {
        "instrument": spec.instrument,
        "side": spec.side,
        "timeframe": "H4" if hours == 4 else "D1",
        "created_complete_bucket_count": len(complete),
        "dropped_source_missing_bucket_count": len(all_buckets - complete),
        "created_bucket_timestamp_sha256": timestamp_digest.hexdigest(),
        "derived_ohlcv_sha256": ohlcv_digest.hexdigest(),
        "derived_ohlcv_fields": ["timestamp", "open", "high", "low", "close", "volume"],
        "source": "canonical H1 only",
        "forward_fill_count": 0,
    }


def cross_market_stream(group: str, timeframe: str, factories: dict[str, object]) -> dict:
    members = FROZEN_GROUPS.get(group)
    if members is None or set(factories) != set(members):
        raise ActualQcError("Cross-market group differs from the frozen membership")
    iterators = {member: iter(factories[member]()) for member in members}
    current = {member: next(iterators[member], None) for member in members}
    counts = {member: 0 for member in members}
    union_count = 0
    intersection_count = 0
    missing_occurrences = 0
    intersection_digest = hashlib.sha256()
    while any(value is not None for value in current.values()):
        timestamp = min(value for value in current.values() if value is not None)
        present = [member for member in members if current[member] == timestamp]
        union_count += 1
        missing_occurrences += len(members) - len(present)
        if len(present) == len(members):
            intersection_count += 1
            intersection_digest.update((iso(timestamp) + "\n").encode("ascii"))
        for member in present:
            counts[member] += 1
            current[member] = next(iterators[member], None)
    return {
        "group": group,
        "timeframe": timeframe,
        "members": list(members),
        "union_count": union_count,
        "intersection_count": intersection_count,
        "per_member_count": counts,
        "missing_member_occurrences": missing_occurrences,
        "intersection_timestamp_sha256": intersection_digest.hexdigest(),
    }


def _structural_report_impl(
    raw_dir: Path, schedule_manifest: Path, schedule_allowlist: Path, schedule_dir: Path,
    repo_root: Path | None = None,
) -> dict:
    repo_root = repo_root or Path(__file__).resolve().parents[3]
    manifest_bytes = read_regular_bytes(schedule_manifest)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    schedule = validate_schedule_contract(json.loads(manifest_bytes.decode("utf-8")))
    allowlist = validate_schedule_allowlist(schedule_allowlist, manifest_sha256, repo_root)
    schedule_paths = validate_schedule_files(schedule, schedule_dir)
    validate_raw_set(raw_dir)
    series = [scan_series(raw_dir / spec.filename, spec) for spec in SPECS]
    bid_ask = [validate_bid_ask(raw_dir, instrument, timeframe) for instrument in INSTRUMENTS for timeframe in TIMEFRAMES]
    reconciliation = [reconcile_m15_h1(raw_dir, instrument, side) for instrument in INSTRUMENTS for side in SIDES]
    missingness = [
        compare_series_to_schedule(raw_dir / spec.filename, spec, schedule_paths[spec.schedule_filename])
        for spec in SPECS
    ]
    derived = [
        derived_bucket_audit(
            raw_dir / SeriesSpec(instrument, "H1", side).filename,
            SeriesSpec(instrument, "H1", side),
            schedule_paths[f"{instrument}_H1.timestamps"],
            hours,
        )
        for instrument in INSTRUMENTS for side in SIDES for hours in (4, 24)
    ]
    cross_market = []
    for group, members in FROZEN_GROUPS.items():
        for timeframe in ("M15", "H1"):
            factories = {
                member: (
                    lambda member=member, timeframe=timeframe: (
                        row.timestamp
                        for row in iter_rows(
                            raw_dir / SeriesSpec(member, timeframe, "bid").filename,
                            SeriesSpec(member, timeframe, "bid"),
                        )
                    )
                )
                for member in members
            }
            cross_market.append(cross_market_stream(group, timeframe, factories))
        for label, hours in (("H4", 4), ("D1", 24)):
            factories = {
                member: (
                    lambda member=member, hours=hours: iter_complete_bucket_opens(
                        raw_dir / SeriesSpec(member, "H1", "bid").filename,
                        SeriesSpec(member, "H1", "bid"),
                        schedule_paths[f"{member}_H1.timestamps"],
                        hours,
                    )
                )
                for member in members
            }
            cross_market.append(cross_market_stream(group, label, factories))
    return {
        "schema_version": "phase9-actual-full-qc-v1.0",
        "status": "STREAMING_48_SERIES_QC_PASS_ENERGY_METADATA_AND_SEPARATE_COUNT_GATE_PENDING",
        "series_count": 48,
        "series": series,
        "bid_ask": bid_ask,
        "m15_h1_reconciliation": reconciliation,
        "missingness": missingness,
        "h4_d1_bucket_audit": derived,
        "cross_market_overlap": cross_market,
        "provider_schedule_source": schedule["source"],
        "provider_schedule_version": schedule["provider_version"],
        "provider_schedule_source_run_id": allowlist["source_run_id"],
        "provider_schedule_freeze_parent_sha": allowlist["freeze_parent_sha"],
        "provider_schedule_allowlist_git_anchor_verified": True,
        "provider_schedule_same_run_self_authorization_used": False,
        "provider_schedule_file_match_passed": True,
        "h4_d1_complete_utc_bucket_audit_passed": True,
        "streaming_48_series_qc_implementation_passed": True,
        "energy_metadata_gate_passed": False,
        "forward_fill_count": 0,
        "period_extension_count": 0,
        "h1_forbidden_tail_rows": 0,
        "actual_market_data_full_quality_gate_passed": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def structural_report(
    raw_dir: Path, schedule_manifest: Path, schedule_allowlist: Path, schedule_dir: Path,
    repo_root: Path | None = None,
) -> dict:
    global _PINNED_RAW_ROOT, _PINNED_SCHEDULE_ROOT
    _PINNED_RAW.clear()
    _PINNED_SCHEDULE.clear()
    _PINNED_RAW_ROOT = None
    _PINNED_SCHEDULE_ROOT = None
    try:
        return _structural_report_impl(
            raw_dir, schedule_manifest, schedule_allowlist, schedule_dir, repo_root
        )
    finally:
        _PINNED_RAW.clear()
        _PINNED_SCHEDULE.clear()
        _PINNED_RAW_ROOT = None
        _PINNED_SCHEDULE_ROOT = None


def atomic_json(path: Path, value: object) -> None:
    if not path.is_absolute():
        raise ActualQcError("QC report target must be absolute")
    parent = path.parent
    parent_info = parent.lstat()
    if parent.is_symlink() or not parent.is_dir() or parent_info.st_uid != os.getuid():
        raise ActualQcError("QC report parent must be a runner-owned real directory")
    if parent_info.st_mode & 0o077:
        raise ActualQcError("QC report parent must use mode 0700")
    temporary_name = path.name + ".part"
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = None
    created = False
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if stat_identity(os.fstat(directory)) != stat_identity(parent_info):
            raise ActualQcError("QC report parent changed before directory pin")
        for name, message in (
            (path.name, "QC report target must be new"),
            (temporary_name, "QC report temporary target must be new"),
        ):
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ActualQcError(message)
        descriptor = os.open(
            temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory,
        )
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(
                temporary_name, path.name, src_dir_fd=directory, dst_dir_fd=directory,
                follow_symlinks=False,
            )
        except FileExistsError as error:
            raise ActualQcError("QC report target must remain new") from error
        os.unlink(temporary_name, dir_fd=directory)
        created = False
        os.fsync(directory)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                os.unlink(temporary_name, dir_fd=directory)
            except FileNotFoundError:
                pass
        raise
    finally:
        os.close(directory)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--provider-schedule-manifest", type=Path, required=True)
    parser.add_argument("--provider-schedule-allowlist", type=Path, required=True)
    parser.add_argument("--provider-schedule-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise ActualQcError("Exact post-acquisition Full-QC confirmation required")
    report = structural_report(
        args.raw_dir,
        args.provider_schedule_manifest,
        args.provider_schedule_allowlist,
        args.provider_schedule_dir,
    )
    atomic_json(args.report, report)
    print(json.dumps({"status": report["status"], "count_only_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
