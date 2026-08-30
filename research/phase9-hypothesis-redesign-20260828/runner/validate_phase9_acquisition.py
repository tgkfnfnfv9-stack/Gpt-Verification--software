#!/usr/bin/env python3
"""Validate Phase 9 raw files without calculating any research outcome."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "data_manifest"
START = datetime(2013, 1, 1, tzinfo=timezone.utc)
END_EXCLUSIVE = datetime(2019, 8, 28, tzinfo=timezone.utc)
H1_END_EXCLUSIVE = datetime(2019, 8, 1, tzinfo=timezone.utc)
WARMUP_END_EXCLUSIVE = datetime(2014, 8, 28, tzinfo=timezone.utc)
STEPS = {"M15": 15 * 60, "H1": 60 * 60}
EXPECTED_HEADER = ["timestamp", "open", "high", "low", "close", "volume"]
MAX_GAP_SAMPLES_PER_PAIR = 1000


def norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def pick(fields: list[str], candidates: list[str]) -> str:
    mapped = {norm(field): field for field in fields}
    for candidate in candidates:
        if norm(candidate) in mapped:
            return mapped[norm(candidate)]
    for normalized, field in mapped.items():
        if any(normalized.endswith(norm(candidate)) for candidate in candidates):
            return field
    raise KeyError(f"Missing CSV column: {candidates}")


def parse_dt(value: str) -> datetime:
    text = str(value).strip().strip('"').replace("Z", "+00:00")
    try:
        numeric = float(text)
        if numeric > 1e12:
            return datetime.fromtimestamp(numeric / 1000, tz=timezone.utc)
        if numeric > 1e9:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        raise ValueError("Invalid timestamp value.") from None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reader_and_keys(handle):
    reader = csv.DictReader(handle)
    fields = reader.fieldnames or []
    if fields != EXPECTED_HEADER:
        raise ValueError("CSV header differs from the exact canonical OHLCV schema.")
    keys = {"time": "timestamp", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"}
    return reader, keys


def parse_row(
    row: dict, keys: dict, path: Path, row_number: int, end_exclusive: datetime
) -> tuple[datetime, float, float]:
    try:
        dt = parse_dt(row[keys["time"]])
    except (KeyError, ValueError):
        raise ValueError(f"Invalid timestamp in {path.name} at CSV row {row_number}.") from None
    if not START <= dt < end_exclusive:
        raise ValueError(f"Timestamp outside frozen interval in {path.name}: {dt.isoformat()}")
    values = {}
    for name, key in keys.items():
        if name == "time":
            continue
        try:
            values[name] = float(row[key])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"Invalid numeric field {name} in {path.name} at CSV row {row_number}."
            ) from None
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError(f"Non-finite value in {path.name} at {dt.isoformat()}")
    if min(values["open"], values["high"], values["low"], values["close"]) <= 0:
        raise ValueError(f"Non-positive price in {path.name} at {dt.isoformat()}")
    if values["high"] < max(values["open"], values["close"]):
        raise ValueError(f"Invalid high in {path.name} at {dt.isoformat()}")
    if values["low"] > min(values["open"], values["close"]):
        raise ValueError(f"Invalid low in {path.name} at {dt.isoformat()}")
    if values["volume"] < 0:
        raise ValueError(f"Negative tick volume in {path.name} at {dt.isoformat()}")
    return dt, values["open"], values["volume"]


def validate_pair(data_dir: Path, symbol: str, timeframe: str) -> tuple[list[dict], list[dict]]:
    bid_path = data_dir / f"{symbol}_{timeframe}_bid.csv"
    ask_path = data_dir / f"{symbol}_{timeframe}_ask.csv"
    gaps: list[dict] = []
    gap_count = 0
    volume_mismatch_count = 0
    count = 0
    warmup_rows = 0
    discovery_rows = 0
    first = None
    last = None
    previous = None
    step = STEPS[timeframe]
    end_exclusive = END_EXCLUSIVE if timeframe == "M15" else H1_END_EXCLUSIVE

    with bid_path.open(encoding="utf-8-sig", newline="") as bid_handle, ask_path.open(
        encoding="utf-8-sig", newline=""
    ) as ask_handle:
        bid_reader, bid_keys = reader_and_keys(bid_handle)
        ask_reader, ask_keys = reader_and_keys(ask_handle)
        for row_number, (bid_row, ask_row) in enumerate(
            zip_longest(bid_reader, ask_reader), start=2
        ):
            if bid_row is None or ask_row is None:
                raise ValueError(f"BID/ASK row count mismatch for {symbol} {timeframe}")
            bid_dt, bid_open, bid_volume = parse_row(
                bid_row, bid_keys, bid_path, row_number, end_exclusive
            )
            ask_dt, ask_open, ask_volume = parse_row(
                ask_row, ask_keys, ask_path, row_number, end_exclusive
            )
            if bid_dt != ask_dt:
                raise ValueError(f"BID/ASK timestamp mismatch for {symbol} {timeframe}")
            if ask_open < bid_open:
                raise ValueError(f"ASK open below BID open for {symbol} {timeframe} at {bid_dt.isoformat()}")
            if ask_volume != bid_volume:
                volume_mismatch_count += 1
            if timeframe == "M15" and (bid_dt.minute % 15 or bid_dt.second or bid_dt.microsecond):
                raise ValueError(f"M15 timestamp is not aligned: {bid_dt.isoformat()}")
            if timeframe == "H1" and (bid_dt.minute or bid_dt.second or bid_dt.microsecond):
                raise ValueError(f"H1 timestamp is not aligned: {bid_dt.isoformat()}")
            if previous is not None:
                delta = int((bid_dt - previous).total_seconds())
                if delta <= 0:
                    raise ValueError(f"Timestamps are not strictly increasing for {symbol} {timeframe}")
                if delta > step:
                    gap_count += 1
                    if len(gaps) < MAX_GAP_SAMPLES_PER_PAIR:
                        gaps.append(
                            {
                                "symbol": symbol,
                                "timeframe": timeframe,
                                "after": previous.isoformat().replace("+00:00", "Z"),
                                "before": bid_dt.isoformat().replace("+00:00", "Z"),
                                "seconds": delta,
                            }
                        )
            previous = bid_dt
            first = first or bid_dt
            last = bid_dt
            count += 1
            if bid_dt < WARMUP_END_EXCLUSIVE:
                warmup_rows += 1
            else:
                discovery_rows += 1
    if count == 0:
        raise ValueError(f"Empty series for {symbol} {timeframe}")
    common = {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows": count,
        "warmup_rows": warmup_rows,
        "discovery_rows": discovery_rows,
        "first": first.isoformat().replace("+00:00", "Z"),
        "last": last.isoformat().replace("+00:00", "Z"),
        "gap_count": gap_count,
        "gap_samples_truncated": gap_count > len(gaps),
        "bid_ask_volume_mismatch_count": volume_mismatch_count,
        "canonical_tick_volume_side": "BID",
    }
    series = []
    for side, path in (("bid", bid_path), ("ask", ask_path)):
        series.append(
            {
                **common,
                "side": side,
                "relative_path": path.name,
                "sha256": sha256(path),
            }
        )
    return series, gaps


def expected_files() -> tuple[list[str], list[str]]:
    mapping = json.loads((MANIFEST_DIR / "instrument_mapping.json").read_text(encoding="utf-8"))
    symbols = [row["research_symbol"] for row in mapping["instruments"] if row["acquisition_enabled"]]
    names = [
        f"{symbol}_{timeframe}_{side}.csv"
        for symbol in symbols
        for timeframe in ("M15", "H1")
        for side in ("bid", "ask")
    ]
    if len(symbols) != 12 or len(names) != 48:
        raise ValueError("Frozen mapping must generate exactly 48 source files.")
    return symbols, names


def atomic_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate(data_dir: Path, output_dir: Path) -> dict:
    symbols, names = expected_files()
    if not data_dir.is_dir():
        raise ValueError("Raw data directory does not exist or is not a directory.")
    entries = list(data_dir.iterdir())
    unsafe = sorted(
        path.name
        for path in entries
        if path.is_symlink() or not path.is_file() or path.suffix != ".csv"
    )
    if unsafe:
        raise ValueError(f"Unexpected raw-directory entries: {unsafe}")
    actual = sorted(path.name for path in entries)
    if actual != sorted(names):
        missing = sorted(set(names) - set(actual))
        extra = sorted(set(actual) - set(names))
        raise ValueError(f"Raw file set mismatch. missing={missing}, extra={extra}")
    all_series: list[dict] = []
    all_gaps: list[dict] = []
    for symbol in symbols:
        for timeframe in ("M15", "H1"):
            series, gaps = validate_pair(data_dir, symbol, timeframe)
            all_series.extend(series)
            all_gaps.extend(gaps)
    if len(all_series) != 48:
        raise ValueError("Validated series count is not 48.")
    output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": "phase9-acquisition-manifest-v1.0",
        "status": "ACQUIRED_BOUNDARY_VALIDATED_FULL_QC_PENDING",
        "git_sha": os.environ.get("GITHUB_SHA"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_image_os": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "start_inclusive": START.isoformat().replace("+00:00", "Z"),
        "end_exclusive": END_EXCLUSIVE.isoformat().replace("+00:00", "Z"),
        "end_exclusive_by_timeframe": {
            "M15": END_EXCLUSIVE.isoformat().replace("+00:00", "Z"),
            "H1": H1_END_EXCLUSIVE.isoformat().replace("+00:00", "Z"),
        },
        "h1_tail_exclusion_frozen": True,
        "series_count": len(all_series),
        "boundary_validation_passed": True,
        "full_quality_gate_passed": False,
        "count_only_authorized": False,
        "outcome_access_authorized": False,
        "research_outcomes_calculated": False,
        "warmup_signal_generation_allowed": False,
        "raw_data_in_artifact": False,
        "series": all_series,
    }
    atomic_json(output_dir / "acquisition_manifest.json", manifest)
    atomic_json(output_dir / "gaps.json", all_gaps)
    (output_dir / "data_sha256.txt").write_text(
        "".join(
            f'{row["sha256"]}  {row["relative_path"]}\n'
            for row in sorted(all_series, key=lambda item: item["relative_path"])
        ),
        encoding="utf-8",
    )
    (output_dir / "data_row_counts.txt").write_text(
        "".join(
            f'{row["rows"]}  {row["relative_path"]}\n'
            for row in sorted(all_series, key=lambda item: item["relative_path"])
        ),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Phase 9 raw market data without outcomes.")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    validate(args.data_dir.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
