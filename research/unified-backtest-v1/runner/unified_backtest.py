#!/usr/bin/env python3
"""Reusable, stdlib-only FX/commodity backtest engine."""

from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from types import MappingProxyType
from typing import Iterable, Sequence


RUNNER_ROOT = Path(__file__).resolve().parent
if str(RUNNER_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNNER_ROOT))

from core import (  # noqa: E402
    Bar,
    CoreError,
    Outcome,
    QuoteBar,
    Signal,
    TIMEFRAME_STEPS,
    atr_before,
    clustered_lower_bound,
    collapse_connected,
    evaluate_horizon,
    metrics,
    midpoint_series,
    signal_identity,
)


UTC = timezone.utc
HEX64 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
CSV_HEADER = (
    "timestamp_utc",
    "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close",
)
MAX_JSON_BYTES = 5_000_000
MAX_INSTRUMENTS = 50
MAX_INPUT_FILES = 100
MAX_FILE_BYTES = 20_000_000_000
MAX_ROWS_PER_FILE = 3_000_000
MAX_SIGNALS_PER_STRATEGY = 1_000_000
MANIFEST_KEYS = {
    "schema_version", "dataset_id", "timezone", "timestamp_semantics",
    "source_timestamp_semantics", "timestamp_semantics_evidence", "aggregation_profile_id",
    "required_direct_timeframes", "start_inclusive", "end_exclusive", "instruments", "files",
}
EVIDENCE_KEYS = {"path", "sha256", "bytes"}
TIMESTAMP_EVIDENCE_KEYS = {"schema_version", "status", "providers"}
TIMESTAMP_PROVIDER_KEYS = {
    "provider", "dataset_or_endpoint", "timestamp_column", "timezone",
    "timeframes", "semantics_by_timeframe", "primary_source_locator",
    "primary_source_artifact_path", "primary_source_artifact_sha256",
    "primary_source_artifact_bytes", "review_status",
}
ROLL_POLICY_KEYS = {
    "schema_version", "status", "roll_policy_id", "instrument_id", "provider", "provider_symbol",
    "series_type", "adjustment_method", "coverage_start_inclusive",
    "coverage_end_exclusive", "source_evidence_path", "source_evidence_sha256",
    "source_evidence_bytes", "applied_series_sha256", "events",
}
ROLL_EVENT_KEYS = {"roll_at_utc", "from_contract", "to_contract", "adjustment_value"}
INSTRUMENT_KEYS = {
    "instrument_id", "provider", "provider_symbol", "asset_class", "series_type",
    "quote_currency", "price_domain", "tick_size", "roll_policy_id", "roll_policy_path",
    "roll_policy_sha256", "roll_policy_bytes",
}
FILE_KEYS = {"instrument_id", "timeframe", "source_role", "path", "sha256", "bytes", "row_count"}


class BacktestError(RuntimeError):
    pass


def strict_json(path: Path) -> dict:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise BacktestError(f"JSON resource limit exceeded: {path}")
    def pairs(rows):
        output = {}
        for key, value in rows:
            if key in output:
                raise BacktestError(f"duplicate JSON key in {path.name}: {key}")
            output[key] = value
        return output

    def reject(value):
        raise BacktestError(f"non-finite JSON constant in {path.name}: {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BacktestError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BacktestError(f"JSON root must be object: {path}")
    return value


def exact_keys(value: dict, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        missing = sorted(expected - set(value)) if isinstance(value, dict) else sorted(expected)
        extra = sorted(set(value) - expected) if isinstance(value, dict) else []
        raise BacktestError(f"{label} key mismatch; missing={missing}, extra={extra}")


def parse_utc(text: object, label: str) -> datetime:
    if not isinstance(text, str):
        raise BacktestError(f"{label} must be UTC timestamp")
    try:
        value = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise BacktestError(f"invalid UTC timestamp for {label}") from exc
    return value


def utc_text(value: datetime) -> str:
    if value.tzinfo != UTC:
        raise BacktestError("non-UTC datetime")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular_single_link(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise BacktestError(f"missing file: {path}") from exc
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise BacktestError(f"regular single-link file required: {path}")


def safe_child(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise BacktestError("unsafe relative path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise BacktestError(f"unsafe relative path: {relative}")
    root = root.resolve()
    candidate = root.joinpath(*pure.parts)
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise BacktestError(f"symlink path component rejected: {relative}")
    try:
        candidate.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise BacktestError(f"path escapes root: {relative}") from exc
    require_regular_single_link(candidate)
    return candidate


def finite_decimal(text: object, domain: str, label: str) -> float:
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError) as exc:
        raise BacktestError(f"invalid decimal at {label}") from exc
    if not value.is_finite() or (domain == "STRICTLY_POSITIVE" and value <= 0):
        raise BacktestError(f"price domain violation at {label}")
    result = float(value)
    if not math.isfinite(result):
        raise BacktestError(f"float overflow at {label}")
    return result


def validate_ohlc(bar: Bar, label: str) -> None:
    values = (bar.open, bar.high, bar.low, bar.close)
    if not all(math.isfinite(value) for value in values):
        raise BacktestError(f"non-finite OHLC: {label}")
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.low > bar.high:
        raise BacktestError(f"OHLC geometry mismatch: {label}")


def validate_timestamp_evidence(
    path: Path, root: Path, provider_names: set[str], source_timestamp_semantics: str,
) -> list[str]:
    value = strict_json(path)
    exact_keys(value, TIMESTAMP_EVIDENCE_KEYS, "timestamp evidence")
    profiles = {
        "BAR_OPEN_VERIFIED": ("VERIFIED", "APPROVED_FOR_BACKTEST"),
        "BAR_OPEN_EMPIRICALLY_ALIGNED_PROVIDER_NOT_EXPLICIT": (
            "EMPIRICALLY_ALIGNED_ASSUMPTION",
            "APPROVED_FOR_EXPLORATORY_BACKTEST_ONLY",
        ),
    }
    expected = profiles.get(source_timestamp_semantics)
    if (
        expected is None
        or value["schema_version"] != "timestamp-semantics-evidence-v1.0.0"
        or value["status"] != expected[0]
    ):
        raise BacktestError("timestamp evidence version/status mismatch")
    rows = value["providers"]
    if not isinstance(rows, list) or not rows:
        raise BacktestError("timestamp provider evidence required")
    seen = set()
    source_paths = []
    for index, row in enumerate(rows):
        exact_keys(row, TIMESTAMP_PROVIDER_KEYS, f"timestamp provider[{index}]")
        provider = row["provider"]
        if not isinstance(provider, str) or not provider or provider in seen:
            raise BacktestError("invalid/duplicate timestamp evidence provider")
        seen.add(provider)
        if (
            not isinstance(row["dataset_or_endpoint"], str) or not row["dataset_or_endpoint"]
            or row["timestamp_column"] != "timestamp_utc"
            or row["timezone"] != "UTC"
            or row["timeframes"] != ["M1", "H1"]
            or row["semantics_by_timeframe"] != {
                "M1": "INTERVAL_OPEN_INSTANT", "H1": "INTERVAL_OPEN_INSTANT"
            }
            or not isinstance(row["primary_source_locator"], str) or not row["primary_source_locator"].startswith("https://")
            or not isinstance(row["primary_source_artifact_path"], str) or not row["primary_source_artifact_path"]
            or not isinstance(row["primary_source_artifact_sha256"], str) or not HEX64.fullmatch(row["primary_source_artifact_sha256"])
            or type(row["primary_source_artifact_bytes"]) is not int or row["primary_source_artifact_bytes"] <= 0
            or row["review_status"] != expected[1]
        ):
            raise BacktestError("timestamp provider evidence content mismatch")
        source = safe_child(root, row["primary_source_artifact_path"])
        if source.stat().st_size != row["primary_source_artifact_bytes"] or sha256_file(source) != row["primary_source_artifact_sha256"]:
            raise BacktestError("timestamp primary evidence byte/hash mismatch")
        source_paths.append(PurePosixPath(row["primary_source_artifact_path"]).as_posix())
    if seen != provider_names:
        raise BacktestError("timestamp evidence provider set mismatch")
    if len(source_paths) != len(set(source_paths)):
        raise BacktestError("duplicate timestamp primary evidence path")
    return source_paths


def validate_roll_policy(
    path: Path,
    root: Path,
    instrument: dict,
    start: datetime,
    end: datetime,
    applied_hashes: dict[str, str],
) -> str:
    value = strict_json(path)
    exact_keys(value, ROLL_POLICY_KEYS, "roll policy")
    if (
        value["schema_version"] != "continuous-roll-policy-v1.0.0"
        or value["status"] != "VERIFIED_AND_APPLIED_TO_SERIES"
        or value["roll_policy_id"] != instrument["roll_policy_id"]
        or value["instrument_id"] != instrument["instrument_id"]
        or value["provider"] != instrument["provider"]
        or value["provider_symbol"] != instrument["provider_symbol"]
        or value["series_type"] != instrument["series_type"]
        or value["adjustment_method"] not in ("BACK_ADJUSTED", "RATIO_ADJUSTED")
        or parse_utc(value["coverage_start_inclusive"], "roll coverage start") > start
        or parse_utc(value["coverage_end_exclusive"], "roll coverage end") < end
        or type(value["source_evidence_bytes"]) is not int or value["source_evidence_bytes"] <= 0
        or not isinstance(value["source_evidence_sha256"], str) or not HEX64.fullmatch(value["source_evidence_sha256"])
        or value["applied_series_sha256"] != applied_hashes
    ):
        raise BacktestError("roll policy content mismatch")
    source = safe_child(root, value["source_evidence_path"])
    if source.stat().st_size != value["source_evidence_bytes"] or sha256_file(source) != value["source_evidence_sha256"]:
        raise BacktestError("roll source evidence byte/hash mismatch")
    events = value["events"]
    if not isinstance(events, list) or not events:
        raise BacktestError("continuous series requires roll events")
    previous = None
    for index, event in enumerate(events):
        exact_keys(event, ROLL_EVENT_KEYS, f"roll event[{index}]")
        stamp = parse_utc(event["roll_at_utc"], "roll event")
        if not start <= stamp < end or (previous is not None and stamp <= previous):
            raise BacktestError("roll event order mismatch")
        if event["from_contract"] == event["to_contract"]:
            raise BacktestError("roll contracts must differ")
        if index and events[index - 1]["to_contract"] != event["from_contract"]:
            raise BacktestError("roll contract chain mismatch")
        previous = stamp
        if not all(isinstance(event[key], str) and event[key] for key in ("from_contract", "to_contract")):
            raise BacktestError("roll contract identity missing")
        finite_decimal(event["adjustment_value"], "FINITE_REAL", "roll adjustment")
    return PurePosixPath(value["source_evidence_path"]).as_posix()


def validate_manifest(manifest: dict) -> tuple[datetime, datetime, dict[str, dict], list[dict]]:
    exact_keys(manifest, MANIFEST_KEYS, "dataset manifest")
    if manifest["schema_version"] != "unified-market-dataset-v1.0.0":
        raise BacktestError("dataset schema version mismatch")
    if not isinstance(manifest["dataset_id"], str) or not IDENTIFIER.fullmatch(manifest["dataset_id"]):
        raise BacktestError("dataset_id required")
    if (
        manifest["timezone"] != "UTC"
        or manifest["timestamp_semantics"] != "BAR_OPEN"
        or manifest["source_timestamp_semantics"] not in (
            "BAR_OPEN_VERIFIED",
            "BAR_OPEN_EMPIRICALLY_ALIGNED_PROVIDER_NOT_EXPLICIT",
        )
        or manifest["aggregation_profile_id"] != "UTC_FIXED_V1"
        or manifest["required_direct_timeframes"] != ["M1", "H1"]
    ):
        raise BacktestError("dataset time convention mismatch")
    evidence = manifest["timestamp_semantics_evidence"]
    exact_keys(evidence, EVIDENCE_KEYS, "timestamp semantics evidence")
    if not isinstance(evidence["sha256"], str) or not HEX64.fullmatch(evidence["sha256"]) or type(evidence["bytes"]) is not int or evidence["bytes"] <= 0:
        raise BacktestError("invalid timestamp semantics evidence identity")
    start = parse_utc(manifest["start_inclusive"], "start_inclusive")
    end = parse_utc(manifest["end_exclusive"], "end_exclusive")
    if start >= end:
        raise BacktestError("invalid dataset interval")
    instruments = manifest["instruments"]
    if not isinstance(instruments, list) or not instruments or len(instruments) > MAX_INSTRUMENTS:
        raise BacktestError("non-empty instruments required")
    instrument_map = {}
    for index, row in enumerate(instruments):
        exact_keys(row, INSTRUMENT_KEYS, f"instrument[{index}]")
        instrument_id = row["instrument_id"]
        if not isinstance(instrument_id, str) or not IDENTIFIER.fullmatch(instrument_id):
            raise BacktestError("invalid instrument_id")
        if instrument_id in instrument_map:
            raise BacktestError("duplicate instrument_id")
        if row["asset_class"] not in ("FX", "COMMODITY"):
            raise BacktestError("asset_class must be FX or COMMODITY")
        if row["price_domain"] not in ("STRICTLY_POSITIVE", "FINITE_REAL"):
            raise BacktestError("invalid price_domain")
        if not all(isinstance(row[key], str) and row[key] for key in (
            "provider", "provider_symbol", "series_type", "quote_currency", "tick_size"
        )):
            raise BacktestError("instrument text fields required")
        if row["series_type"] not in ("SPOT", "CFD_SINGLE_CONTRACT", "CFD_CONTINUOUS", "FUTURES_CONTINUOUS"):
            raise BacktestError("invalid series_type")
        finite_decimal(row["tick_size"], "STRICTLY_POSITIVE", "tick_size")
        continuous = row["series_type"] in ("CFD_CONTINUOUS", "FUTURES_CONTINUOUS")
        roll_id = row["roll_policy_id"]
        roll_path = row["roll_policy_path"]
        roll_hash = row["roll_policy_sha256"]
        roll_bytes = row["roll_policy_bytes"]
        if continuous:
            if (
                not isinstance(roll_id, str) or not roll_id
                or not isinstance(roll_path, str) or not roll_path
                or not isinstance(roll_hash, str) or not HEX64.fullmatch(roll_hash)
                or type(roll_bytes) is not int or roll_bytes <= 0
            ):
                raise BacktestError("continuous future requires pinned roll policy")
        elif any(value is not None for value in (roll_id, roll_path, roll_hash, roll_bytes)):
            raise BacktestError("roll policy is only valid for continuous futures")
        instrument_map[instrument_id] = row
    files = manifest["files"]
    if not isinstance(files, list) or not files or len(files) > MAX_INPUT_FILES:
        raise BacktestError("non-empty files required")
    seen = set()
    for index, row in enumerate(files):
        exact_keys(row, FILE_KEYS, f"file[{index}]")
        key = (row["instrument_id"], row["timeframe"])
        if row["instrument_id"] not in instrument_map or row["timeframe"] not in ("M1", "H1"):
            raise BacktestError("unknown file instrument/timeframe")
        if row["source_role"] != "DIRECT_PROVIDER":
            raise BacktestError("only direct provider M1/H1 inputs are accepted")
        if key in seen:
            raise BacktestError("duplicate instrument/timeframe file")
        seen.add(key)
        if not isinstance(row["sha256"], str) or not HEX64.fullmatch(row["sha256"]):
            raise BacktestError("file sha256 must be lowercase hex")
        if type(row["bytes"]) is not int or not 0 < row["bytes"] <= MAX_FILE_BYTES:
            raise BacktestError("file bytes must be positive integer")
        if type(row["row_count"]) is not int or not 0 < row["row_count"] <= MAX_ROWS_PER_FILE:
            raise BacktestError("file row_count must be positive integer")
    expected = {(instrument_id, timeframe) for instrument_id in instrument_map for timeframe in ("M1", "H1")}
    if seen != expected:
        raise BacktestError("exact instrument x direct-timeframe matrix required")
    return start, end, instrument_map, files


def load_quote_csv(
    path: Path,
    timeframe: str,
    domain: str,
    start: datetime,
    end: datetime,
) -> tuple[list[QuoteBar], dict]:
    output = []
    previous = None
    step = TIMEFRAME_STEPS[timeframe]
    gaps = 0
    missing_slots = 0
    max_gap_seconds = 0
    gap_digest = hashlib.sha256()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_HEADER:
            raise BacktestError(f"CSV header mismatch: {path.name}")
        for line, row in enumerate(reader, start=2):
            if None in row or set(row) != set(CSV_HEADER):
                raise BacktestError(f"CSV shape mismatch: {path.name}:{line}")
            stamp = parse_utc(row["timestamp_utc"], f"{path.name}:{line}")
            if not start <= stamp < end:
                raise BacktestError(f"timestamp outside manifest interval: {path.name}:{line}")
            if int(stamp.timestamp()) % int(step.total_seconds()) != 0:
                raise BacktestError(f"timestamp alignment mismatch: {path.name}:{line}")
            if previous is not None:
                if stamp <= previous:
                    raise BacktestError(f"timestamp order/duplicate mismatch: {path.name}:{line}")
                if stamp - previous != step:
                    gaps += 1
                    gap_seconds = int((stamp - previous).total_seconds())
                    missing = max(0, gap_seconds // int(step.total_seconds()) - 1)
                    missing_slots += missing
                    max_gap_seconds = max(max_gap_seconds, gap_seconds)
                    gap_digest.update(f"{utc_text(previous)}\0{utc_text(stamp)}\0{missing}\n".encode("utf-8"))
            previous = stamp
            bid_values = [finite_decimal(row[f"bid_{field}"], domain, f"{path.name}:{line}") for field in ("open", "high", "low", "close")]
            ask_values = [finite_decimal(row[f"ask_{field}"], domain, f"{path.name}:{line}") for field in ("open", "high", "low", "close")]
            bid = Bar(stamp, *bid_values)
            ask = Bar(stamp, *ask_values)
            validate_ohlc(bid, f"{path.name}:{line}:BID")
            validate_ohlc(ask, f"{path.name}:{line}:ASK")
            if ask.open < bid.open or ask.close < bid.close:
                raise BacktestError(f"crossed BID/ASK open or close: {path.name}:{line}")
            output.append(QuoteBar(stamp, bid, ask))
    if not output:
        raise BacktestError(f"empty CSV: {path.name}")
    return output, {
        "row_count": len(output),
        "gap_transition_count": gaps,
        "missing_nominal_slot_count": missing_slots,
        "maximum_gap_seconds": max_gap_seconds,
        "gap_identity_sha256": gap_digest.hexdigest(),
    }


def aggregate_quotes(source: Sequence[QuoteBar], source_timeframe: str, target_timeframe: str) -> tuple[list[QuoteBar], dict]:
    source_step = TIMEFRAME_STEPS[source_timeframe]
    target_step = TIMEFRAME_STEPS[target_timeframe]
    source_seconds = int(source_step.total_seconds())
    target_seconds = int(target_step.total_seconds())
    if target_seconds <= source_seconds or target_seconds % source_seconds:
        raise BacktestError("invalid aggregation ratio")
    expected_count = target_seconds // source_seconds
    buckets: dict[datetime, list[QuoteBar]] = defaultdict(list)
    for row in source:
        seconds = int(row.timestamp.timestamp())
        bucket_seconds = seconds - seconds % target_seconds
        bucket = datetime.fromtimestamp(bucket_seconds, tz=UTC)
        buckets[bucket].append(row)
    output = []
    dropped = 0
    for bucket in sorted(buckets):
        rows = sorted(buckets[bucket], key=lambda item: item.timestamp)
        expected = [bucket + source_step * index for index in range(expected_count)]
        if len(rows) != expected_count or [row.timestamp for row in rows] != expected:
            dropped += 1
            continue

        def side(name: str) -> Bar:
            bars = [getattr(row, name) for row in rows]
            return Bar(bucket, bars[0].open, max(row.high for row in bars), min(row.low for row in bars), bars[-1].close)

        output.append(QuoteBar(bucket, side("bid"), side("ask")))
    return output, {
        "source_timeframe": source_timeframe,
        "target_timeframe": target_timeframe,
        "complete_bucket_count": len(output),
        "dropped_incomplete_bucket_count": dropped,
        "forward_fill_count": 0,
        "interpolation_count": 0,
    }


def monthly_h1_coverage(
    h1_store: dict[tuple[str, str], list[QuoteBar]],
    instrument_ids: Iterable[str],
    evaluation_start: datetime,
    evaluation_end: datetime,
) -> tuple[list[dict], set[tuple[str, str]]]:
    rows = []
    month = datetime(evaluation_start.year, evaluation_start.month, 1, tzinfo=UTC)
    while month < evaluation_end:
        next_month = datetime(
            month.year + (1 if month.month == 12 else 0),
            1 if month.month == 12 else month.month + 1,
            1,
            tzinfo=UTC,
        )
        window_start = max(month, evaluation_start)
        window_end = min(next_month, evaluation_end)
        duration_hours = max(1, int((window_end - window_start).total_seconds() // 3600))
        required_h1 = min(240, max(1, math.ceil(duration_hours * 0.5)))
        required_dates = min(15, max(1, math.ceil((window_end - window_start).total_seconds() / 86400 * 0.5)))
        for symbol in sorted(instrument_ids):
            timestamps = [
                row.timestamp for row in h1_store[(symbol, "H1")]
                if window_start <= row.timestamp < window_end
            ]
            active_dates = len({stamp.date() for stamp in timestamps})
            passed = len(timestamps) >= required_h1 and active_dates >= required_dates
            rows.append({
                "instrument_id": symbol,
                "month_utc": month.strftime("%Y-%m"),
                "h1_count": len(timestamps),
                "active_utc_date_count": active_dates,
                "minimum_h1_count": required_h1,
                "minimum_active_utc_date_count": required_dates,
                "status": "PASS" if passed else "FAIL",
            })
        month = next_month
    failed_symbol_months = {
        (row["instrument_id"], row["month_utc"])
        for row in rows
        if row["status"] == "FAIL"
    }
    return rows, failed_symbol_months


def load_dataset(
    data_root: Path,
    manifest_path: Path,
    derive_targets: Sequence[str],
    retained_timeframes: Sequence[str],
    evaluation_start: datetime,
    evaluation_end: datetime,
    allow_empirical_timestamp_assumption: bool = False,
):
    require_regular_single_link(manifest_path)
    manifest = strict_json(manifest_path)
    start, end, instruments, file_rows = validate_manifest(manifest)
    if (
        manifest["source_timestamp_semantics"] == "BAR_OPEN_EMPIRICALLY_ALIGNED_PROVIDER_NOT_EXPLICIT"
        and not allow_empirical_timestamp_assumption
    ):
        raise BacktestError("empirical timestamp assumption requires explicit execution acknowledgement")
    if start > evaluation_start or end < evaluation_end:
        raise BacktestError("dataset does not cover the complete configured evaluation interval")
    root = data_root.resolve()
    for path in root.rglob("*"):
        info = path.lstat()
        if path.is_symlink() or (not path.is_dir() and not stat.S_ISREG(info.st_mode)):
            raise BacktestError("dataset artifact symlink/special member rejected")
    expected_files = {manifest_path.relative_to(root).as_posix()}
    evidence = manifest["timestamp_semantics_evidence"]
    evidence_path = safe_child(root, evidence["path"])
    if evidence_path.stat().st_size != evidence["bytes"] or sha256_file(evidence_path) != evidence["sha256"]:
        raise BacktestError("timestamp semantics evidence byte/hash mismatch")
    timestamp_source_paths = validate_timestamp_evidence(
        evidence_path,
        root,
        {row["provider"] for row in instruments.values()},
        manifest["source_timestamp_semantics"],
    )
    evidence_relative = PurePosixPath(evidence["path"]).as_posix()
    if evidence_relative in expected_files:
        raise BacktestError("timestamp evidence path collision")
    expected_files.add(evidence_relative)
    for relative in timestamp_source_paths:
        if relative in expected_files:
            raise BacktestError("timestamp primary evidence path collision")
        expected_files.add(relative)
    file_hashes = {
        (row["instrument_id"], row["timeframe"]): row["sha256"]
        for row in file_rows
    }
    for instrument in instruments.values():
        if instrument["roll_policy_path"] is not None:
            roll_path = safe_child(root, instrument["roll_policy_path"])
            if roll_path.stat().st_size != instrument["roll_policy_bytes"] or sha256_file(roll_path) != instrument["roll_policy_sha256"]:
                raise BacktestError("roll policy byte/hash mismatch")
            source_relative = validate_roll_policy(
                roll_path,
                root,
                instrument,
                start,
                end,
                {timeframe: file_hashes[(instrument["instrument_id"], timeframe)] for timeframe in ("M1", "H1")},
            )
            roll_relative = PurePosixPath(instrument["roll_policy_path"]).as_posix()
            if roll_relative in expected_files:
                raise BacktestError("roll policy path collision")
            expected_files.add(roll_relative)
            if source_relative in expected_files:
                raise BacktestError("roll source evidence path collision")
            expected_files.add(source_relative)
    direct_files = {}
    for row in sorted(file_rows, key=lambda item: (item["instrument_id"], item["timeframe"])):
        path = safe_child(root, row["path"])
        relative_path = PurePosixPath(row["path"]).as_posix()
        if relative_path in expected_files:
            raise BacktestError(f"duplicate/colliding dataset path: {row['path']}")
        expected_files.add(relative_path)
        direct_files[(row["instrument_id"], row["timeframe"])] = (row, path)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise BacktestError(f"dataset artifact member mismatch; missing={sorted(expected_files - actual_files)}, extra={sorted(actual_files - expected_files)}")

    direct_qc = []

    def read_direct(key: tuple[str, str]) -> list[QuoteBar]:
        row, path = direct_files[key]
        if path.stat().st_size != row["bytes"] or sha256_file(path) != row["sha256"]:
            raise BacktestError(f"file byte/hash mismatch: {row['path']}")
        quotes, qc = load_quote_csv(path, key[1], instruments[key[0]]["price_domain"], start, end)
        if sha256_file(path) != row["sha256"]:
            raise BacktestError(f"file changed while parsing: {row['path']}")
        if len(quotes) != row["row_count"]:
            raise BacktestError(f"file row_count mismatch: {row['path']}")
        if quotes[0].timestamp > start + timedelta(days=7) or quotes[-1].timestamp + TIMEFRAME_STEPS[key[1]] < end - timedelta(days=7):
            raise BacktestError(f"direct series does not span declared interval: {row['path']}")
        direct_qc.append({"instrument_id": key[0], "timeframe": key[1], **qc})
        return quotes

    store = {}
    derived_qc = []
    requested = set(derive_targets)
    retained = set(retained_timeframes)
    h1_diagnostic = []

    # Direct H1 is small enough to retain and is the canonical execution series.
    for symbol in sorted(instruments):
        store[(symbol, "H1")] = read_direct((symbol, "H1"))

    monthly_coverage, failed_symbol_months = monthly_h1_coverage(
        store, instruments, evaluation_start, evaluation_end
    )

    # Hold only one instrument's M1 rows at a time unless an enabled strategy truly requires M1.
    for symbol in sorted(instruments):
        m1 = read_direct((symbol, "M1"))
        derived_h1, h1_qc = aggregate_quotes(m1, "M1", "H1")
        direct_by_time = {row.timestamp: row for row in store[(symbol, "H1")]}
        derived_by_time = {row.timestamp: row for row in derived_h1}
        direct_only = set(direct_by_time) - set(derived_by_time)
        if direct_only:
            raise BacktestError(
                f"direct H1 lacks an exact 60-M1 source bucket: {symbol}:count={len(direct_only)}"
            )

        def quote_values(row: QuoteBar) -> tuple[float, ...]:
            return tuple(
                getattr(side, field)
                for side in (row.bid, row.ask)
                for field in ("open", "high", "low", "close")
            )

        shared = sorted(set(direct_by_time) & set(derived_by_time))
        mismatch_times = [
            stamp for stamp in shared
            if quote_values(direct_by_time[stamp]) != quote_values(derived_by_time[stamp])
        ]
        h1_diagnostic.append({
            "instrument_id": symbol,
            "direct_h1_count": len(direct_by_time),
            "m1_derived_complete_h1_count": len(derived_by_time),
            "shared_timestamp_count": len(shared),
            "direct_only_timestamp_count": len(direct_only),
            "derived_only_timestamp_count": len(set(derived_by_time) - set(direct_by_time)),
            "bid_ask_ohlc_mismatch_count": len(mismatch_times),
            "mismatch_timestamp_identity_sha256": hashlib.sha256("".join(
                f"{utc_text(stamp)}\n" for stamp in mismatch_times
            ).encode("utf-8")).hexdigest(),
            "direct_h1_remains_canonical": True,
            "all_direct_h1_has_exact_60_m1": True,
            "aggregation_qc": h1_qc,
        })
        for target in ("M5", "M15", "M30"):
            if target in requested:
                rows, qc = aggregate_quotes(m1, "M1", target)
                if rows:
                    store[(symbol, target)] = rows
                derived_qc.append({"instrument_id": symbol, **qc})
        if "M1" in retained:
            store[(symbol, "M1")] = m1

    for symbol in sorted(instruments):
        for target in ("H4", "D1"):
            if target in requested:
                rows, qc = aggregate_quotes(store[(symbol, "H1")], "H1", target)
                if rows:
                    store[(symbol, target)] = rows
                derived_qc.append({"instrument_id": symbol, **qc})
    missing_required = [
        f"{symbol}:{timeframe}"
        for symbol in sorted(instruments)
        for timeframe in sorted(retained | set(derive_targets) | {"H1"})
        if (symbol, timeframe) not in store
    ]
    if missing_required:
        raise BacktestError(f"required direct/derived series unavailable: {missing_required}")
    return manifest, instruments, store, {
        "status": "PASS_WITH_COVERAGE_WARNINGS" if failed_symbol_months else "PASS",
        "source_timestamp_semantics": manifest["source_timestamp_semantics"],
        "coverage_warning_symbol_month_count": len(failed_symbol_months),
        "coverage_warning_symbol_month_identity_sha256": hashlib.sha256("".join(
            f"{symbol}\0{month}\n" for symbol, month in sorted(failed_symbol_months)
        ).encode("utf-8")).hexdigest(),
        "direct": direct_qc,
        "monthly_h1_coverage": monthly_coverage,
        "derived": derived_qc,
        "m1_derived_h1_diagnostic": h1_diagnostic,
        "series_available": [f"{symbol}:{timeframe}" for symbol, timeframe in sorted(store)],
    }


def deep_freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    return value


class StrategyAPI:
    def __init__(self, strategy: dict, store: dict[tuple[str, str], list[QuoteBar]]):
        self._strategy = strategy
        self._store = store
        self._midpoints = {}

    def symbols(self, required_timeframes: Sequence[str]) -> list[str]:
        if not isinstance(required_timeframes, (list, tuple)) or not required_timeframes:
            raise BacktestError("required_timeframes must be non-empty sequence")
        candidates = {symbol for symbol, _ in self._store}
        return sorted(symbol for symbol in candidates if all((symbol, tf) in self._store for tf in required_timeframes))

    def series(self, symbol: str, timeframe: str) -> tuple[Bar, ...]:
        try:
            key = (symbol, timeframe)
            if key not in self._midpoints:
                self._midpoints[key] = tuple(midpoint_series(self._store[key]))
            return self._midpoints[key]
        except KeyError as exc:
            raise BacktestError(f"series unavailable: {symbol}:{timeframe}") from exc

    def atr_before(self, symbol: str, timeframe: str, index: int, period: int) -> float | None:
        return atr_before(self.series(symbol, timeframe), index, period, TIMEFRAME_STEPS[timeframe])

    def signal(self, strategy_id: str, symbol: str, direction: str, signal_time: datetime, entry_time: datetime) -> Signal:
        if strategy_id != self._strategy["strategy_id"] or symbol not in {item[0] for item in self._store}:
            raise BacktestError("plugin signal identity mismatch")
        if direction not in ("BUY", "SELL") or signal_time.tzinfo != UTC or entry_time.tzinfo != UTC or signal_time > entry_time:
            raise BacktestError("invalid plugin signal")
        execution_timeframe = self._strategy["execution_timeframe"]
        return Signal(strategy_id, symbol, direction, signal_time, entry_time, execution_timeframe)

    @staticmethod
    def add_time(value: datetime, **kwargs) -> datetime:
        return value + timedelta(**kwargs)

    @staticmethod
    def replace_hour(value: datetime, hour: int) -> datetime:
        if not isinstance(hour, int) or not 0 <= hour <= 23:
            raise BacktestError("invalid hour")
        return value.replace(hour=hour, minute=0, second=0, microsecond=0)

    @staticmethod
    def make_time(year: int, month: int, day: int, hour: int) -> datetime:
        return datetime(year, month, day, hour, tzinfo=UTC)


def validate_config(config: dict) -> tuple[list[str], str]:
    exact_keys(config, {"schema_version", "status", "horizons", "execution", "splits", "aggregation", "output", "promotion_gate"}, "config")
    if config["schema_version"] != "unified-backtest-config-v1.0.0" or config["status"] != "FROZEN_BEFORE_FIRST_UNIFIED_BACKTEST":
        raise BacktestError("config version/status mismatch")
    horizons = config["horizons"]
    exact_keys(horizons, {"bar_counts", "clock_hours", "primary"}, "horizons")
    if horizons["bar_counts"] != [1, 3, 6] or horizons["clock_hours"] != [4, 12, 24]:
        raise BacktestError("frozen horizons mismatch")
    labels = [f"BAR_{value}" for value in horizons["bar_counts"]] + [f"CLOCK_{value}H" for value in horizons["clock_hours"]]
    if horizons["primary"] != "CLOCK_12H" or horizons["primary"] not in labels:
        raise BacktestError("primary horizon mismatch")
    execution = config["execution"]
    exact_keys(execution, {
        "entry", "buy_entry", "buy_exit", "sell_entry", "sell_exit", "atr_period",
        "additional_commission_price", "slippage_price", "financing_included",
    }, "execution")
    expected_execution = {
        "entry": "EXACT_SIGNAL_ENTRY_BAR_OPEN", "buy_entry": "ASK_OPEN", "buy_exit": "BID_OPEN",
        "sell_entry": "BID_OPEN", "sell_exit": "ASK_OPEN",
    }
    if any(execution[key] != value for key, value in expected_execution.items()):
        raise BacktestError("execution convention mismatch")
    if not isinstance(execution["atr_period"], int) or execution["atr_period"] <= 0:
        raise BacktestError("invalid execution ATR period")
    for key in ("additional_commission_price", "slippage_price"):
        if execution[key] != 0.0:
            raise BacktestError(f"V1 permits spread-only execution; {key} must be 0.0")
    if execution["financing_included"] is not False:
        raise BacktestError("V1 does not implement financing; flag must be false")
    aggregation = config["aggregation"]
    exact_keys(aggregation, {"derive_if_missing", "incomplete_bucket_action", "forward_fill", "interpolation"}, "aggregation")
    if aggregation["derive_if_missing"] != ["M5", "M15", "M30", "H4", "D1"] or aggregation["incomplete_bucket_action"] != "DROP" or aggregation["forward_fill"] is not False or aggregation["interpolation"] is not False:
        raise BacktestError("aggregation policy mismatch")
    splits = config["splits"]
    if not isinstance(splits, list) or not splits:
        raise BacktestError("splits required")
    previous_end = None
    names = set()
    for index, split in enumerate(splits):
        exact_keys(split, {"name", "start_inclusive", "end_exclusive"}, f"split[{index}]")
        start = parse_utc(split["start_inclusive"], "split start")
        end = parse_utc(split["end_exclusive"], "split end")
        if split["name"] in names or start >= end or (previous_end is not None and start < previous_end):
            raise BacktestError("split order/identity mismatch")
        names.add(split["name"])
        previous_end = end
    output = config["output"]
    exact_keys(output, {"phase1_primary_horizon_only", "phase1_max_candles_per_chart", "include_trade_rows_in_summary"}, "output")
    if output["phase1_primary_horizon_only"] is not True or output["include_trade_rows_in_summary"] is not False or not isinstance(output["phase1_max_candles_per_chart"], int) or output["phase1_max_candles_per_chart"] <= 0:
        raise BacktestError("output policy mismatch")
    gate = config["promotion_gate"]
    exact_keys(gate, {
        "required_splits", "minimum_primary_completion_rate", "primary_mean_r_strictly_positive",
        "minimum_primary_profit_factor", "minimum_positive_instrument_count",
        "minimum_positive_mean_r_quarters", "cluster_bootstrap_resamples",
        "familywise_method", "familywise_alpha", "prior_outcome_tested_candidate_count",
        "current_candidate_count", "per_candidate_alpha", "bootstrap_seed",
    }, "promotion_gate")
    if not isinstance(gate["required_splits"], list) or not set(gate["required_splits"]).issubset(names):
        raise BacktestError("promotion split mismatch")
    if not isinstance(gate["minimum_primary_completion_rate"], (int, float)) or not 0 <= gate["minimum_primary_completion_rate"] <= 1:
        raise BacktestError("invalid promotion completion rate")
    if gate["primary_mean_r_strictly_positive"] is not True or not isinstance(gate["minimum_primary_profit_factor"], (int, float)) or gate["minimum_primary_profit_factor"] < 0:
        raise BacktestError("invalid promotion return gate")
    if type(gate["minimum_positive_instrument_count"]) is not int or gate["minimum_positive_instrument_count"] <= 0:
        raise BacktestError("invalid positive instrument minimum")
    if type(gate["minimum_positive_mean_r_quarters"]) is not int or gate["minimum_positive_mean_r_quarters"] <= 0:
        raise BacktestError("invalid positive quarter minimum")
    if type(gate["cluster_bootstrap_resamples"]) is not int or gate["cluster_bootstrap_resamples"] < 1000:
        raise BacktestError("invalid bootstrap resamples")
    if not isinstance(gate["familywise_alpha"], (int, float)) or not 0 < gate["familywise_alpha"] < 0.5:
        raise BacktestError("invalid familywise alpha")
    if gate["familywise_method"] != "BONFERRONI_PRIOR_7_PLUS_CURRENT_2":
        raise BacktestError("familywise method mismatch")
    if type(gate["prior_outcome_tested_candidate_count"]) is not int or gate["prior_outcome_tested_candidate_count"] != 7:
        raise BacktestError("prior tested candidate count mismatch")
    if type(gate["current_candidate_count"]) is not int or gate["current_candidate_count"] != 2:
        raise BacktestError("current candidate count mismatch")
    denominator = gate["prior_outcome_tested_candidate_count"] + gate["current_candidate_count"]
    if not isinstance(gate["per_candidate_alpha"], (int, float)) or not math.isclose(
        gate["per_candidate_alpha"], gate["familywise_alpha"] / denominator, rel_tol=0.0, abs_tol=1e-15
    ):
        raise BacktestError("per-candidate alpha mismatch")
    if type(gate["bootstrap_seed"]) is not int:
        raise BacktestError("invalid bootstrap seed")
    return labels, horizons["primary"]


def validate_registry(registry: dict, split_names: set[str] | None = None) -> list[dict]:
    exact_keys(registry, {"schema_version", "status", "strategies"}, "strategy registry")
    if registry["schema_version"] != "unified-strategy-registry-v1.0.0" or registry["status"] != "FROZEN_BEFORE_FIRST_UNIFIED_BACKTEST":
        raise BacktestError("registry version/status mismatch")
    rows = registry["strategies"]
    if not isinstance(rows, list) or not rows:
        raise BacktestError("non-empty strategy registry required")
    ids = set()
    for index, row in enumerate(rows):
        exact_keys(row, {
            "strategy_id", "enabled", "plugin", "plugin_sha256", "name_ja", "hypothesis_ja",
            "entry_logic_ja", "exit_logic_ja", "required_timeframes", "execution_timeframe",
            "signal_to_entry_hours", "episode_overlap_hours", "timestamp_geometry_gate",
            "frequency_gate_split", "minimum_primary_trades_per_split",
            "parameters", "frequency_gate",
        }, f"strategy[{index}]")
        if not isinstance(row["strategy_id"], str) or not IDENTIFIER.fullmatch(row["strategy_id"]) or row["strategy_id"] in ids:
            raise BacktestError("invalid/duplicate strategy_id")
        ids.add(row["strategy_id"])
        if not isinstance(row["enabled"], bool):
            raise BacktestError("enabled must be boolean")
        if not isinstance(row["plugin"], str) or PurePosixPath(row["plugin"]).name != row["plugin"] or not row["plugin"].endswith(".py"):
            raise BacktestError("plugin must be safe basename")
        if not isinstance(row["plugin_sha256"], str) or not HEX64.fullmatch(row["plugin_sha256"]):
            raise BacktestError("plugin sha256 must be pinned")
        if not isinstance(row["required_timeframes"], list) or not row["required_timeframes"] or any(tf not in TIMEFRAME_STEPS for tf in row["required_timeframes"]):
            raise BacktestError("invalid required_timeframes")
        if row["execution_timeframe"] not in row["required_timeframes"]:
            raise BacktestError("execution timeframe must be required")
        if type(row["signal_to_entry_hours"]) is not int or row["signal_to_entry_hours"] < 0:
            raise BacktestError("invalid signal-to-entry lag")
        if not isinstance(row["episode_overlap_hours"], int) or row["episode_overlap_hours"] <= 0:
            raise BacktestError("invalid episode overlap")
        if not isinstance(row["frequency_gate_split"], str) or (split_names is not None and row["frequency_gate_split"] not in split_names):
            raise BacktestError("invalid frequency gate split")
        if type(row["minimum_primary_trades_per_split"]) is not int or row["minimum_primary_trades_per_split"] <= 0:
            raise BacktestError("invalid primary trade minimum")
        if not isinstance(row["parameters"], dict):
            raise BacktestError("strategy parameters must be object")
        gate = row["frequency_gate"]
        exact_keys(gate, {"episodes_min", "active_dates_min", "instruments_with_minimum_count", "minimum_count_per_instrument", "maximum_instrument_share", "minimum_each_year_share"}, "frequency gate")
        for key in ("episodes_min", "active_dates_min", "instruments_with_minimum_count", "minimum_count_per_instrument"):
            if type(gate[key]) is not int or gate[key] <= 0:
                raise BacktestError(f"invalid frequency gate {key}")
        for key in ("maximum_instrument_share", "minimum_each_year_share"):
            if not isinstance(gate[key], (int, float)) or not 0 <= gate[key] <= 1:
                raise BacktestError(f"invalid frequency gate {key}")
        geometry = row["timestamp_geometry_gate"]
        if geometry is not None:
            exact_keys(geometry, {"kind", "decision_hour_utc", "entry_hour_utc", "completed_d1_count", "slots_min", "distinct_entry_utc_dates_min", "each_evaluation_year_capacity_min", "instruments_with_minimum_count", "minimum_count_per_instrument", "maximum_instrument_share"}, "timestamp geometry gate")
            if geometry["kind"] != "MONTHLY_FIRST_ELIGIBLE_DATE" or geometry["entry_hour_utc"] != geometry["decision_hour_utc"] + 1:
                raise BacktestError("invalid timestamp geometry kind/hours")
            for key in ("decision_hour_utc", "entry_hour_utc", "completed_d1_count", "slots_min", "distinct_entry_utc_dates_min", "each_evaluation_year_capacity_min", "instruments_with_minimum_count", "minimum_count_per_instrument"):
                if type(geometry[key]) is not int or geometry[key] < 0:
                    raise BacktestError(f"invalid timestamp geometry {key}")
            if not isinstance(geometry["maximum_instrument_share"], (int, float)) or not 0 <= geometry["maximum_instrument_share"] <= 1:
                raise BacktestError("invalid timestamp geometry share")
    return rows


def timestamp_geometry_result(strategy: dict, store: dict, split: dict) -> dict:
    gate = strategy["timestamp_geometry_gate"]
    if gate is None:
        return {"status": "NOT_REQUIRED"}
    start = parse_utc(split["start_inclusive"], "geometry start")
    end = parse_utc(split["end_exclusive"], "geometry end")
    slots = []
    for symbol in sorted({key[0] for key in store if key[1] == "H1"}):
        timestamps = {row.timestamp for row in store[(symbol, "H1")] if start <= row.timestamp < end}
        d1_timestamps = {
            row.timestamp for row in store.get((symbol, "D1"), [])
        }
        dates_by_month = defaultdict(set)
        for stamp in timestamps:
            dates_by_month[(stamp.year, stamp.month)].add((stamp.year, stamp.month, stamp.day))
        for month in sorted(dates_by_month):
            decision = None
            for year, month_number, day in sorted(dates_by_month[month]):
                midnight = datetime(year, month_number, day, tzinfo=UTC)
                if any(midnight + timedelta(hours=hour) in timestamps for hour in range(gate["decision_hour_utc"])):
                    decision = midnight + timedelta(hours=gate["decision_hour_utc"])
                    break
            completed_d1 = sum(stamp + timedelta(days=1) <= decision for stamp in d1_timestamps) if decision is not None else 0
            if decision is not None and decision + timedelta(hours=1) in timestamps and completed_d1 >= gate["completed_d1_count"]:
                slots.append((symbol, decision))
    counts = Counter(symbol for symbol, _ in slots)
    total = len(slots)
    maximum_share = max(counts.values(), default=0) / total if total else 0.0
    year_counts = Counter(stamp.year for _, stamp in slots)
    checks = {
        "slots_min": total >= gate["slots_min"],
        "distinct_entry_utc_dates_min": len({stamp.date() for _, stamp in slots}) >= gate["distinct_entry_utc_dates_min"],
        "each_evaluation_year_capacity_min": all(
            year_counts[year] >= gate["each_evaluation_year_capacity_min"]
            for year in range(start.year, end.year)
        ),
        "instruments_with_minimum_count": sum(value >= gate["minimum_count_per_instrument"] for value in counts.values()) >= gate["instruments_with_minimum_count"],
        "maximum_instrument_share": maximum_share <= gate["maximum_instrument_share"],
    }
    identity = hashlib.sha256("".join(
        f"{symbol}\0{utc_text(stamp)}\n" for symbol, stamp in sorted(slots)
    ).encode("utf-8")).hexdigest()
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "slot_count": total,
        "distinct_entry_utc_date_count": len({stamp.date() for _, stamp in slots}),
        "counts_by_year": {str(year): year_counts[year] for year in range(start.year, end.year)},
        "counts_by_instrument": dict(sorted(counts.items())),
        "maximum_instrument_share": round(maximum_share, 10),
        "slot_identity_sha256": identity,
    }


def load_plugin(strategies_root: Path, row: dict):
    path = safe_child(strategies_root, row["plugin"])
    source_hash = sha256_file(path)
    if source_hash != row["plugin_sha256"]:
        raise BacktestError(f"plugin hash mismatch: {row['strategy_id']}")
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=path.name)
    except SyntaxError as exc:
        raise BacktestError(f"plugin syntax error: {path.name}") from exc
    validate_plugin_ast(tree, path.name)
    safe_builtins = {
        "abs": abs, "all": all, "any": any, "enumerate": enumerate, "len": len,
        "list": list, "max": max, "min": min, "range": range, "set": set, "sorted": sorted,
        "sum": sum, "zip": zip,
    }
    namespace = {"__builtins__": safe_builtins}
    exec(compile(tree, path.name, "exec"), namespace, namespace)
    if sha256_file(path) != source_hash:
        raise BacktestError("plugin changed during import")
    generate = namespace.get("generate_signals")
    if not callable(generate):
        raise BacktestError("plugin generate_signals missing")
    return generate


def validate_plugin_ast(tree: ast.AST, filename: str) -> None:
    """Allow a small signal-only language; plugins are not general Python programs."""
    body = list(getattr(tree, "body", []))
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.FunctionDef) or body[0].name != "generate_signals":
        raise BacktestError(f"plugin must contain only generate_signals: {filename}")
    function = body[0]
    if function.decorator_list or function.returns is not None or [arg.arg for arg in function.args.args] != ["api", "strategy"] or function.args.vararg or function.args.kwarg or function.args.kwonlyargs:
        raise BacktestError(f"plugin function signature mismatch: {filename}")
    forbidden = (
        ast.Import, ast.ImportFrom, ast.ClassDef, ast.AsyncFunctionDef, ast.Lambda,
        ast.With, ast.AsyncWith, ast.Try, ast.Raise, ast.Global, ast.Nonlocal,
        ast.Delete, ast.Await, ast.Yield, ast.YieldFrom, ast.NamedExpr,
    )
    api_methods = {"symbols", "series", "atr_before", "signal", "add_time", "replace_hour", "make_time"}
    data_attributes = {
        "timestamp", "open", "high", "low", "close", "year", "month", "day", "hour",
        "direction", "signal_time", "entry_time", "execution_timeframe", "append", "add", "get", "setdefault",
    }
    safe_calls = {"abs", "all", "any", "enumerate", "len", "list", "max", "min", "range", "set", "sorted", "sum", "zip"}
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            raise BacktestError(f"forbidden plugin syntax {type(node).__name__}: {filename}")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise BacktestError(f"private/dunder plugin name forbidden: {filename}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise BacktestError(f"private/dunder plugin attribute forbidden: {filename}")
            if isinstance(node.value, ast.Name) and node.value.id == "api":
                if node.attr not in api_methods:
                    raise BacktestError(f"plugin API attribute forbidden: {node.attr}")
            elif node.attr not in data_attributes:
                raise BacktestError(f"plugin data attribute forbidden: {node.attr}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in safe_calls:
                    raise BacktestError(f"plugin call forbidden: {node.func.id}")
            elif isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "api":
                    if node.func.attr not in api_methods:
                        raise BacktestError(f"plugin API call forbidden: {node.func.attr}")
                elif node.func.attr not in {"append", "add", "get", "setdefault"}:
                    raise BacktestError(f"plugin method call forbidden: {node.func.attr}")
            else:
                raise BacktestError(f"indirect plugin call forbidden: {filename}")
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, (ast.Name, ast.Tuple)):
                    raise BacktestError(f"plugin assignment target forbidden: {filename}")


def frequency_result(signals: Sequence[Signal], gate: dict, coverage_years: Sequence[int]) -> dict:
    instrument_counts = Counter(row.symbol for row in signals)
    year_counts = Counter(row.entry_time.year for row in signals)
    total = len(signals)
    active_dates = len({row.entry_time.date() for row in signals})
    qualifying_instruments = sum(count >= gate["minimum_count_per_instrument"] for count in instrument_counts.values())
    maximum_share = max(instrument_counts.values(), default=0) / total if total else 0.0
    year_shares = {str(year): (year_counts[year] / total if total else 0.0) for year in sorted(set(coverage_years))}
    checks = {
        "episodes_min": total >= gate["episodes_min"],
        "active_dates_min": active_dates >= gate["active_dates_min"],
        "instruments_with_minimum_count": qualifying_instruments >= gate["instruments_with_minimum_count"],
        "maximum_instrument_share": maximum_share <= gate["maximum_instrument_share"],
        "minimum_each_year_share": bool(year_shares) and all(value >= gate["minimum_each_year_share"] for value in year_shares.values()),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "episode_count": total,
        "active_date_count": active_dates,
        "qualifying_instrument_count": qualifying_instruments,
        "maximum_instrument_share": round(maximum_share, 10),
        "counts_by_instrument": dict(sorted(instrument_counts.items())),
        "shares_by_year": year_shares,
        "episode_identity_sha256": signal_identity(signals),
    }


def causality_audit(generate, strategy: dict, store: dict, full_signals: Sequence[Signal], boundaries: Sequence[datetime]) -> dict:
    checked = []
    for cutoff in sorted(set(boundaries)):
        truncated = {
            key: [row for row in values if row.timestamp < cutoff]
            for key, values in store.items()
        }
        if any(not truncated.get((symbol, timeframe)) for symbol in {key[0] for key in store} for timeframe in strategy["required_timeframes"]):
            continue
        api = StrategyAPI(strategy, truncated)
        prefix_rows = generate(api, strategy)
        if not isinstance(prefix_rows, list) or any(not isinstance(row, Signal) for row in prefix_rows):
            raise BacktestError("plugin causality audit returned invalid signals")
        expected = [row for row in full_signals if row.entry_time < cutoff]
        actual = [row for row in prefix_rows if row.entry_time < cutoff]
        if signal_identity(expected) != signal_identity(actual):
            raise BacktestError(f"future suffix changed earlier signals before {utc_text(cutoff)}")
        checked.append(cutoff.year)
    return {"status": "PASS", "checked_cutoff_years": checked}


def outcome_key(row: Outcome) -> tuple:
    return (row.symbol, row.direction, row.entry_time)


def episodes_for_interval(strategy: dict, raw_signals: Sequence[Signal], start: datetime, end: datetime) -> tuple[list[Signal], list[Signal], int]:
    raw = [row for row in raw_signals if start <= row.entry_time < end]
    local_episodes = collapse_connected(raw, strategy["episode_overlap_hours"])
    global_episodes = collapse_connected(raw_signals, strategy["episode_overlap_hours"])
    episodes = [row for row in global_episodes if start <= row.entry_time < end]
    return raw, episodes, max(0, len(local_episodes) - len(episodes))


def split_result(strategy: dict, raw_signals: Sequence[Signal], split: dict, store: dict, midpoint_store: dict, config: dict, horizons: Sequence[str]) -> tuple[dict, dict[str, list[Outcome]]]:
    start = parse_utc(split["start_inclusive"], "split start")
    end = parse_utc(split["end_exclusive"], "split end")
    raw, episodes, purged_count = episodes_for_interval(strategy, raw_signals, start, end)
    execution = config["execution"]
    for signal in episodes:
        key = (signal.symbol, signal.execution_timeframe)
        if key in store and key not in midpoint_store:
            midpoint_store[key] = midpoint_series(store[key])
    timestamp_indexes = {
        key: {row.timestamp: index for index, row in enumerate(rows)}
        for key, rows in midpoint_store.items()
        if key in {(row.symbol, row.execution_timeframe) for row in episodes}
    }
    by_horizon = {}
    summaries = {}
    for horizon in horizons:
        outcomes = []
        for signal in episodes:
            key = (signal.symbol, signal.execution_timeframe)
            if key not in store:
                continue
            midpoint = midpoint_store[key]
            outcome = evaluate_horizon(
                signal, store[key], midpoint, horizon, execution["atr_period"],
                float(execution["additional_commission_price"]), float(execution["slippage_price"]),
                timestamp_indexes[key],
            )
            if outcome is not None and outcome.exit_time < end:
                outcomes.append(outcome)
        by_horizon[horizon] = outcomes
        instrument_metrics = {
            symbol: metrics([row for row in outcomes if row.symbol == symbol])
            for symbol in sorted({key[0] for key in store if key[1] == strategy["execution_timeframe"]})
        }
        positive_instruments = sum(
            value["mean_r"] is not None and value["mean_r"] > 0
            for value in instrument_metrics.values()
        )
        quarter_metrics = {
            f"{year}-Q{quarter}": metrics([
                row for row in outcomes
                if row.entry_time.year == year and (row.entry_time.month - 1) // 3 + 1 == quarter
            ])
            for year, quarter in sorted({(row.entry_time.year, (row.entry_time.month - 1) // 3 + 1) for row in outcomes})
        }
        summaries[horizon] = {
            "completion_count": len(outcomes),
            "completion_rate": round(len(outcomes) / len(episodes), 10) if episodes else None,
            "metrics": metrics(outcomes),
            "by_instrument": instrument_metrics,
            "by_direction": {direction: metrics([row for row in outcomes if row.direction == direction]) for direction in ("BUY", "SELL")},
            "by_year": {str(year): metrics([row for row in outcomes if row.entry_time.year == year]) for year in sorted({row.entry_time.year for row in outcomes})},
            "positive_instrument_count": positive_instruments,
            "positive_mean_r_quarter_count": sum(value["mean_r"] is not None and value["mean_r"] > 0 for value in quarter_metrics.values()),
            "by_quarter": quarter_metrics,
            "clustered_mean_r_lower_bound": clustered_lower_bound(
                outcomes,
                config["promotion_gate"]["cluster_bootstrap_resamples"],
                config["promotion_gate"]["per_candidate_alpha"],
                config["promotion_gate"]["bootstrap_seed"],
            ) if horizon == config["horizons"]["primary"] else None,
        }
    joint_keys = None
    for rows in by_horizon.values():
        keys = {outcome_key(row) for row in rows}
        joint_keys = keys if joint_keys is None else joint_keys & keys
    joint_keys = joint_keys or set()
    joint = {
        horizon: metrics([row for row in rows if outcome_key(row) in joint_keys])
        for horizon, rows in by_horizon.items()
    }
    result = {
        "raw_signal_count": len(raw),
        "boundary_purged_signal_count": purged_count,
        "episode_count": len(episodes),
        "episode_identity_sha256": signal_identity(episodes),
        "horizons": summaries,
        "joint_complete_count": len(joint_keys),
        "joint_complete_metrics": joint,
    }
    return result, by_horizon


def promotion_result(strategy: dict, split_results: dict, config: dict, primary: str) -> dict:
    gate = config["promotion_gate"]
    details = {}
    for name in gate["required_splits"]:
        split = split_results.get(name)
        horizon = split["horizons"][primary] if split else None
        values = horizon["metrics"] if horizon else None
        checks = {
            "split_present": split is not None,
            "minimum_trades": bool(values) and values["trade_count"] >= strategy["minimum_primary_trades_per_split"],
            "minimum_completion_rate": bool(horizon) and horizon["completion_rate"] is not None and horizon["completion_rate"] >= gate["minimum_primary_completion_rate"],
            "mean_r_positive": bool(values) and values["mean_r"] is not None and values["mean_r"] > 0,
            "minimum_profit_factor": bool(values) and (
                (values["profit_factor"] is not None and values["profit_factor"] >= gate["minimum_primary_profit_factor"])
                or (values["profit_factor"] is None and values["trade_count"] > 0 and values["win_rate"] == 1.0)
            ),
            "minimum_positive_instrument_count": bool(horizon) and horizon["positive_instrument_count"] >= gate["minimum_positive_instrument_count"],
            "minimum_positive_mean_r_quarters": bool(horizon) and horizon["positive_mean_r_quarter_count"] >= gate["minimum_positive_mean_r_quarters"],
            "clustered_lower_bound_positive": bool(horizon) and horizon["clustered_mean_r_lower_bound"] is not None and horizon["clustered_mean_r_lower_bound"] > 0,
        }
        details[name] = {"pass": all(checks.values()), "checks": checks}
    passed = bool(details) and all(row["pass"] for row in details.values())
    return {"status": "ROBUSTNESS_CANDIDATE_REUSED_DATA" if passed else "NOT_PROMOTED", "primary_horizon": primary, "splits": details, "strict_unused_holdout_passed": False}


def phase1_payload(strategy: dict, primary_rows: list[tuple[str, Outcome]], store: dict, config: dict, promotion: dict) -> dict:
    grouped: dict[tuple[str, str, int], list[Outcome]] = defaultdict(list)
    for split_name, row in primary_rows:
        grouped[(split_name, row.symbol, row.entry_time.year)].append(row)
    charts = []
    trade_records = []
    for split_name, symbol, year in sorted(grouped):
        outcomes = grouped[(split_name, symbol, year)]
        timeframe = strategy["execution_timeframe"]
        quotes = store[(symbol, timeframe)]
        start = datetime(year, 1, 1, tzinfo=UTC)
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
        selected = [row for row in quotes if start <= row.timestamp < end]
        if len(selected) > config["output"]["phase1_max_candles_per_chart"]:
            raise BacktestError("Phase 1 candle limit exceeded")
        midpoint = midpoint_series(selected)
        chart_id = f"{strategy['strategy_id'].lower()}_{symbol.lower()}_{timeframe.lower()}_{split_name.lower()}_{year}"
        index_by_time = {row.timestamp: index for index, row in enumerate(midpoint)}
        candles = [{
            "time": utc_text(row.timestamp), "open": row.open, "high": row.high,
            "low": row.low, "close": row.close, "volume": None,
        } for row in midpoint]
        charts.append({
            "id": chart_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "period": f"{split_name} {year}",
            "candles": candles,
            "overlays": [],
            "panes": [],
        })
        for outcome in outcomes:
            if outcome.entry_time not in index_by_time or outcome.exit_time not in index_by_time:
                raise BacktestError("Phase 1 outcome outside chart")
            result = "WIN" if outcome.r > 0 else "LOSS" if outcome.r < 0 else "EVEN"
            trade_records.append((outcome.exit_time, outcome.entry_time, symbol, {
                "no": 0,
                "chart_id": chart_id,
                "side": outcome.direction,
                "entry_i": index_by_time[outcome.entry_time],
                "exit_i": index_by_time[outcome.exit_time],
                "entry_price": outcome.entry_price,
                "exit_price": outcome.exit_price,
                "stop": None,
                "target": None,
                "r": round(outcome.r, 10),
                "result": result,
                "confidence": None,
                "setup": strategy["name_ja"],
                "note": f"{split_name} / CLOCK_12H / spread込み",
            }))
    trades = []
    for number, (_, _, _, trade) in enumerate(sorted(trade_records, key=lambda row: row[:3]), start=1):
        trade["no"] = number
        trades.append(trade)
    payload = {
        "meta": {"report_title": f"{strategy['strategy_id']} 統一バックテスト", "status": "再利用データ頑健性候補" if promotion["status"] == "ROBUSTNESS_CANDIDATE_REUSED_DATA" else "未採用"},
        "strategy": {
            "strategy_id": strategy["strategy_id"],
            "name": strategy["name_ja"],
            "hypothesis": strategy["hypothesis_ja"],
            "entry_logic": strategy["entry_logic_ja"],
            "exit_logic": strategy["exit_logic_ja"],
            "future_tests": ["MT5 demo forward", "費用・スリッページ感応度", "未使用期間での再確認"],
        },
        "charts": charts,
        "trades": trades,
        "notes": [
            "BUYはASK始値でEntryしBID始値でExit、SELLはBID始値でEntryしASK始値でExit。",
            f"追加commission={config['execution']['additional_commission_price']}、slippage={config['execution']['slippage_price']}。",
            f"financing_included={str(config['execution']['financing_included']).lower()}。",
            "表示用candleはBID/ASK midpoint。判断は事前固定のCLOCK_12Hのみ。",
        ],
    }
    validate_phase1(payload)
    return payload


def validate_phase1(payload: dict) -> None:
    exact_keys(payload, {"meta", "strategy", "charts", "trades", "notes"}, "Phase 1 root")
    exact_keys(payload["meta"], {"report_title", "status"}, "Phase 1 meta")
    exact_keys(payload["strategy"], {"strategy_id", "name", "hypothesis", "entry_logic", "exit_logic", "future_tests"}, "Phase 1 strategy")
    chart_map = {}
    for chart in payload["charts"]:
        exact_keys(chart, {"id", "symbol", "timeframe", "period", "candles", "overlays", "panes"}, "Phase 1 chart")
        if chart["id"] in chart_map:
            raise BacktestError("duplicate Phase 1 chart id")
        previous = None
        for candle in chart["candles"]:
            exact_keys(candle, {"time", "open", "high", "low", "close", "volume"}, "Phase 1 candle")
            stamp = parse_utc(candle["time"], "Phase 1 candle time")
            if previous is not None and stamp <= previous:
                raise BacktestError("Phase 1 candle order mismatch")
            previous = stamp
            validate_ohlc(Bar(stamp, candle["open"], candle["high"], candle["low"], candle["close"]), "Phase 1 candle")
        chart_map[chart["id"]] = chart
    expected_trade_keys = {"no", "chart_id", "side", "entry_i", "exit_i", "entry_price", "exit_price", "stop", "target", "r", "result", "confidence", "setup", "note"}
    for expected_no, trade in enumerate(payload["trades"], start=1):
        exact_keys(trade, expected_trade_keys, "Phase 1 trade")
        if trade["no"] != expected_no or trade["chart_id"] not in chart_map or trade["side"] not in ("BUY", "SELL"):
            raise BacktestError("Phase 1 trade identity mismatch")
        candles = chart_map[trade["chart_id"]]["candles"]
        if not isinstance(trade["entry_i"], int) or not isinstance(trade["exit_i"], int) or not 0 <= trade["entry_i"] <= trade["exit_i"] < len(candles):
            raise BacktestError("Phase 1 trade index mismatch")
        if not all(isinstance(trade[key], (int, float)) and math.isfinite(trade[key]) for key in ("entry_price", "exit_price", "r")):
            raise BacktestError("Phase 1 trade numeric mismatch")
        expected_result = "WIN" if trade["r"] > 0 else "LOSS" if trade["r"] < 0 else "EVEN"
        if trade["result"] != expected_result:
            raise BacktestError("Phase 1 result/R mismatch")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def prepare_output_root(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir() or any(path.iterdir()):
            raise BacktestError("output root must be absent or empty directory")
    else:
        path.mkdir(parents=True)


def run(args) -> dict:
    config_argument = Path(args.config)
    registry_argument = Path(args.strategy_registry)
    manifest_argument = Path(args.dataset_manifest)
    data_argument = Path(args.data_root)
    if any(path.is_symlink() for path in (config_argument, registry_argument, manifest_argument, data_argument)):
        raise BacktestError("symlink argument rejected")
    config_path = config_argument.resolve()
    registry_path = registry_argument.resolve()
    require_regular_single_link(config_path)
    require_regular_single_link(registry_path)
    config = strict_json(config_path)
    registry = strict_json(registry_path)
    horizons, primary = validate_config(config)
    strategy_rows = validate_registry(registry, {row["name"] for row in config["splits"]})
    manifest_path = manifest_argument.resolve()
    data_root = data_argument.resolve()
    try:
        manifest_path.relative_to(data_root)
    except ValueError as exc:
        raise BacktestError("dataset manifest must be inside data root") from exc
    selected = set(args.strategy_id or [])
    unknown = selected - {row["strategy_id"] for row in strategy_rows}
    if unknown:
        raise BacktestError(f"unknown strategy ids: {sorted(unknown)}")
    effective_strategies = [
        row for row in strategy_rows
        if row["enabled"] and (not selected or row["strategy_id"] in selected)
    ]
    required_timeframes = {
        timeframe for row in effective_strategies for timeframe in row["required_timeframes"]
    }
    derive_targets = [
        timeframe for timeframe in config["aggregation"]["derive_if_missing"]
        if timeframe in required_timeframes
    ]
    evaluation_start = min(parse_utc(row["start_inclusive"], "evaluation start") for row in config["splits"])
    evaluation_end = max(parse_utc(row["end_exclusive"], "evaluation end") for row in config["splits"])
    manifest, instruments, store, data_qc = load_dataset(
        data_root,
        manifest_path,
        derive_targets,
        sorted(required_timeframes),
        evaluation_start,
        evaluation_end,
        args.allow_empirical_timestamp_assumption,
    )
    summary_strategies = []
    phase1_values = {}
    strategies_root = registry_path.parent
    for strategy in effective_strategies:
        api = StrategyAPI(strategy, store)
        available_symbols = api.symbols(strategy["required_timeframes"])
        if set(available_symbols) != set(instruments):
            missing = sorted(set(instruments) - set(available_symbols))
            summary_strategies.append({
                "strategy_id": strategy["strategy_id"],
                "status": "DATA_UNAVAILABLE",
                "available_instruments": available_symbols,
                "missing_instruments": missing,
                "timestamp_geometry_gate": None,
                "causality_audit": None,
                "frequency_gate": None,
                "splits": {},
                "promotion": {"status": "NOT_PROMOTED", "reason": "exact declared universe unavailable"},
            })
            continue
        frequency_split = next(row for row in config["splits"] if row["name"] == strategy["frequency_gate_split"])
        geometry = timestamp_geometry_result(strategy, store, frequency_split)
        if geometry["status"] == "FAIL":
            summary_strategies.append({
                "strategy_id": strategy["strategy_id"],
                "status": "TIMESTAMP_GEOMETRY_REJECTED",
                "available_instruments": available_symbols,
                "timestamp_geometry_gate": geometry,
                "causality_audit": None,
                "frequency_gate": None,
                "splits": {},
                "promotion": {"status": "NOT_PROMOTED", "reason": "timestamp-only geometry gate failed"},
            })
            continue
        generate = load_plugin(strategies_root, strategy)
        plugin_strategy = deep_freeze(strategy)
        raw_signals = generate(api, plugin_strategy)
        if not isinstance(raw_signals, list) or any(not isinstance(row, Signal) for row in raw_signals):
            raise BacktestError("plugin must return list[Signal]")
        if len(raw_signals) > MAX_SIGNALS_PER_STRATEGY:
            raise BacktestError("plugin signal resource limit exceeded")
        execution_times = {
            symbol: {row.timestamp for row in store.get((symbol, strategy["execution_timeframe"]), [])}
            for symbol in instruments
        }
        for signal in raw_signals:
            if signal.strategy_id != strategy["strategy_id"] or signal.execution_timeframe != strategy["execution_timeframe"]:
                raise BacktestError("plugin returned mismatched signal")
            if signal.entry_time - signal.signal_time != timedelta(hours=strategy["signal_to_entry_hours"]):
                raise BacktestError("plugin signal-to-entry lag mismatch")
            if signal.entry_time not in execution_times.get(signal.symbol, set()):
                raise BacktestError("plugin entry is not an exact execution bar")
        audit_boundaries = [
            parse_utc(split["end_exclusive"], "causality cutoff")
            for split in config["splits"]
        ]
        causality = causality_audit(generate, plugin_strategy, store, raw_signals, audit_boundaries)
        frequency_start = parse_utc(frequency_split["start_inclusive"], "frequency start")
        frequency_end = parse_utc(frequency_split["end_exclusive"], "frequency end")
        _, frequency_episodes, frequency_purged = episodes_for_interval(
            strategy, raw_signals, frequency_start, frequency_end
        )
        frequency_years = list(range(frequency_start.year, (frequency_end - timedelta(microseconds=1)).year + 1))
        frequency = frequency_result(frequency_episodes, strategy["frequency_gate"], frequency_years)
        frequency["split"] = strategy["frequency_gate_split"]
        frequency["boundary_purged_signal_count"] = frequency_purged
        split_summaries = {}
        primary_rows = []
        if frequency["status"] == "PASS":
            for split in config["splits"]:
                split_summary, outcomes = split_result(
                    strategy, raw_signals, split, store, api._midpoints, config, horizons
                )
                split_summaries[split["name"]] = split_summary
                primary_rows.extend((split["name"], row) for row in outcomes[primary])
        promotion = promotion_result(strategy, split_summaries, config, primary) if frequency["status"] == "PASS" else {
            "status": "NOT_PROMOTED", "reason": "frequency gate failed"
        }
        if data_qc["coverage_warning_symbol_month_count"]:
            promotion = {
                "status": "NOT_PROMOTED",
                "reason": "dataset monthly coverage warnings require data review",
            }
        if data_qc["source_timestamp_semantics"] == "BAR_OPEN_EMPIRICALLY_ALIGNED_PROVIDER_NOT_EXPLICIT":
            promotion = {
                "status": "NOT_PROMOTED",
                "reason": "provider does not explicitly document bar-open timestamp semantics",
            }
        status = "REUSED_DATA_RETURN_EVALUATED" if frequency["status"] == "PASS" else "FREQUENCY_REJECTED"
        summary_strategies.append({
            "strategy_id": strategy["strategy_id"],
            "status": status,
            "available_instruments": available_symbols,
            "timestamp_geometry_gate": geometry,
            "causality_audit": causality,
            "raw_signal_count": len(raw_signals),
            "raw_signal_identity_sha256": signal_identity(raw_signals),
            "frequency_gate": frequency,
            "splits": split_summaries,
            "promotion": promotion,
        })
        if frequency["status"] == "PASS":
            phase1_values[strategy["strategy_id"]] = phase1_payload(strategy, primary_rows, store, config, promotion)
    summary = {
        "schema_version": "unified-backtest-summary-v1.0.0",
        "status": "COMPLETE",
        "dataset": {
            "dataset_id": manifest["dataset_id"],
            "manifest_sha256": sha256_file(manifest_path),
            "instrument_count": len(instruments),
            "input_file_count": len(manifest["files"]),
        },
        "configuration": {
            "config_sha256": sha256_file(config_path),
            "registry_sha256": sha256_file(registry_path),
            "primary_horizon": primary,
            "diagnostic_horizons": [row for row in horizons if row != primary],
            "spread_included": True,
            "additional_commission_price": config["execution"]["additional_commission_price"],
            "slippage_price": config["execution"]["slippage_price"],
            "financing_included": config["execution"]["financing_included"],
            "familywise_method": config["promotion_gate"]["familywise_method"],
            "familywise_alpha": config["promotion_gate"]["familywise_alpha"],
            "prior_outcome_tested_candidate_count": config["promotion_gate"]["prior_outcome_tested_candidate_count"],
            "current_candidate_count": config["promotion_gate"]["current_candidate_count"],
            "per_candidate_alpha": config["promotion_gate"]["per_candidate_alpha"],
        },
        "data_qc": data_qc,
        "strategies": summary_strategies,
        "contains_market_prices": False,
        "contains_return_metrics": True,
        "contains_signal_frequency_results": True,
        "contains_individual_trade_rows": False,
        "phase1_contains_market_prices": bool(phase1_values),
        "phase1_contains_individual_trade_results": bool(phase1_values),
    }
    output_root = Path(args.output_root).resolve()
    prepare_output_root(output_root)
    summary_path = output_root / "BACKTEST_SUMMARY.json"
    summary_path.write_bytes(json_bytes(summary))
    phase_root = output_root / "phase1"
    if phase1_values:
        phase_root.mkdir()
        for strategy_id, value in sorted(phase1_values.items()):
            (phase_root / f"{strategy_id}.json").write_bytes(json_bytes(value))
    artifact_rows = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file()):
        relative = path.relative_to(output_root).as_posix()
        artifact_rows.append(f"{sha256_file(path)}  {relative}")
    (output_root / "artifact_manifest_sha256.txt").write_text("\n".join(artifact_rows) + "\n", encoding="utf-8")
    return summary


def parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--dataset-manifest", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--strategy-registry", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--strategy-id", action="append")
    parser.add_argument("--allow-empirical-timestamp-assumption", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        run(parse_args(argv))
    except (BacktestError, CoreError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("Unified backtest completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
