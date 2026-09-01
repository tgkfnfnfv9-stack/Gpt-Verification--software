#!/usr/bin/env python3
"""Acquire official FXCM H1 FX8 bars and emit price-free integrity metadata."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import stat
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


CONFIRMATION = "RUN_EXPLORATORY_FXCM_FX8_H1_2017_2018_QC_ONLY"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
UTC = timezone.utc
EXPECTED_HEADER = [
    "DateTime", "BidOpen", "BidHigh", "BidLow", "BidClose",
    "AskOpen", "AskHigh", "AskLow", "AskClose",
]
MAX_GZIP_BYTES = 20 * 1024 * 1024
MAX_TOTAL_GZIP_BYTES = 4 * 1024 * 1024 * 1024
MAX_SYMBOL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
REQUEST_PAUSE_SECONDS = 0.1
PROHIBITED_FIELDS = {
    "return", "returns", "edge", "mfe", "mae", "win", "win_rate",
    "profit_factor", "drawdown", "cumulative_r", "p_value",
    "confidence_interval", "rank",
}
EXPECTED_PROVIDER = {
    "name": "FXCM",
    "dataset": "MarketData CandleData",
    "source_repository": "https://github.com/fxcm/MarketData",
    "source_repository_head": "924393dd545fab187527d95ef8b1178284b274b6",
    "base_url": "https://candledata.fxcorporate.com/H1",
    "timestamp_timezone": "UTC",
    "timestamp_semantics": "ROW_TIMESTAMP_ASSUMED_BAR_OPEN_NOT_PROVIDER_EXPLICIT",
    "price_sides": ["BID", "ASK"],
    "automation_permission_evidence": "OFFICIAL_README_PUBLISHES_URL_TEMPLATE_AND_PYTHON_LOOP",
}
EXPECTED_USAGE = {
    "personal_noncommercial_use_only": True,
    "eula_url": "https://www.fxcm.com/uk/forms/eula/",
    "explicit_user_confirmation_required_at_dispatch": True,
}


class FxcmError(RuntimeError):
    pass


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise FxcmError(f"unexpected redirect {code} to {newurl}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    expected_symbols = ["AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY", "GBPUSD", "USDJPY"]
    checks = (
        (value.get("contract_version") == "phase9-exploratory-fxcm-v1.0.0", "contract version"),
        (value.get("track") == "EXPLORATORY_FX8_H1_NOT_FORMAL_PHASE9", "track"),
        (value.get("status") == "FROZEN_BEFORE_PRICE_ACCESS", "contract status"),
        (value.get("provider") == EXPECTED_PROVIDER, "provider identity"),
        (value.get("usage_constraints") == EXPECTED_USAGE, "usage constraints"),
        (value.get("formal_authorization_effect") is False, "Formal authorization"),
        (value.get("outcome_calculation_allowed") is False, "outcome flag"),
        (value.get("raw_or_price_artifact_allowed") is False, "raw artifact flag"),
        (value.get("provider_schedule_claim_allowed") is False, "schedule claim flag"),
        (value.get("candidate_signal_count_allowed") is False, "signal count flag"),
        (value.get("years") == [2017, 2018], "years"),
        (value.get("weeks_per_year") == 52, "week count"),
        (value.get("symbols") == expected_symbols, "symbols"),
        (value.get("timeframe") == "H1", "timeframe"),
        (value.get("expected_download_count") == 832, "download count"),
        (value.get("expected_observed_timestamp_file_count") == 8, "observed timestamp count"),
        (value.get("expected_working_price_file_count") == 16, "price file count"),
        (value.get("period") == {"start_inclusive": "2017-01-01T00:00:00Z", "end_exclusive": "2018-12-31T00:00:00Z"}, "period"),
    )
    for passed, name in checks:
        if not passed:
            raise FxcmError(f"frozen contract mismatch: {name}")
    return value


def write_new_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def download(url: str, destination: Path, opener) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "phase9-exploratory-fxcm-qc/1.0"})
    with opener.open(request, timeout=60) as response:
        if response.status != 200:
            raise FxcmError(f"unexpected status {response.status}: {url}")
        total = 0
        with destination.open("xb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_GZIP_BYTES:
                    raise FxcmError(f"source file exceeds limit: {url}")
                handle.write(chunk)
    if destination.stat().st_size < 20:
        raise FxcmError(f"source file too small: {url}")
    with destination.open("rb") as handle:
        if handle.read(2) != b"\x1f\x8b":
            raise FxcmError(f"source is not gzip: {url}")
    return {"url": url, "bytes": destination.stat().st_size, "sha256": sha256_file(destination)}


def parse_timestamp(text: str) -> datetime:
    for pattern in ("%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise FxcmError(f"invalid FXCM timestamp: {text!r}")


def validate_side(values: list[float], label: str) -> None:
    open_, high, low, close = values
    if not all(math.isfinite(value) and value > 0 for value in values):
        raise FxcmError(f"{label}: non-finite or non-positive price")
    if high < max(open_, close, low) or low > min(open_, close, high):
        raise FxcmError(f"{label}: invalid OHLC geometry")


def process_symbol(symbol: str, sources: list[Path], work_prices: Path, observed_dir: Path) -> dict:
    bid_path = work_prices / f"{symbol}_H1_bid.csv"
    ask_path = work_prices / f"{symbol}_H1_ask.csv"
    observed_path = observed_dir / f"{symbol}_H1.timestamps.txt"
    previous = None
    first = None
    last = None
    count = 0
    gaps = 0
    missing_slots = 0
    uncompressed = 0
    source_file_rows = []
    with bid_path.open("x", encoding="utf-8", newline="") as bid_handle, ask_path.open("x", encoding="utf-8", newline="") as ask_handle, observed_path.open("x", encoding="utf-8", newline="\n") as observed:
        bid_writer = csv.writer(bid_handle, lineterminator="\n")
        ask_writer = csv.writer(ask_handle, lineterminator="\n")
        header = ["timestamp_utc", "open", "high", "low", "close"]
        bid_writer.writerow(header)
        ask_writer.writerow(header)
        for source in sources:
            rows_in_source = 0
            with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != EXPECTED_HEADER:
                    raise FxcmError(f"unexpected CSV header in {source.name}: {reader.fieldnames!r}")
                for line_number, row in enumerate(reader, 2):
                    rows_in_source += 1
                    uncompressed += sum(len(value) for value in row.values()) + len(row)
                    if uncompressed > MAX_SYMBOL_UNCOMPRESSED_BYTES:
                        raise FxcmError(f"uncompressed data exceeds limit for {symbol}")
                    timestamp = parse_timestamp(row["DateTime"])
                    if not (datetime(2017, 1, 1, tzinfo=UTC) <= timestamp < datetime(2018, 12, 31, tzinfo=UTC)):
                        raise FxcmError(f"{source.name}:{line_number}: forbidden timestamp")
                    if timestamp.minute or timestamp.second or timestamp.microsecond:
                        raise FxcmError(f"{source.name}:{line_number}: not H1 BAR_OPEN")
                    if previous is not None:
                        delta = int((timestamp - previous).total_seconds()) // 3600
                        if delta <= 0:
                            raise FxcmError(f"{source.name}:{line_number}: non-increasing timestamp")
                        if delta > 1:
                            gaps += 1
                            missing_slots += delta - 1
                    previous = timestamp
                    bid = [float(row[key]) for key in ("BidOpen", "BidHigh", "BidLow", "BidClose")]
                    ask = [float(row[key]) for key in ("AskOpen", "AskHigh", "AskLow", "AskClose")]
                    validate_side(bid, "BID")
                    validate_side(ask, "ASK")
                    if ask[0] < bid[0]:
                        raise FxcmError(f"{source.name}:{line_number}: crossed open")
                    stamp = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
                    bid_writer.writerow([stamp, *row_values(row, "Bid")])
                    ask_writer.writerow([stamp, *row_values(row, "Ask")])
                    observed.write(stamp + "\n")
                    first = first or stamp
                    last = stamp
                    count += 1
            if rows_in_source == 0:
                raise FxcmError(f"empty weekly source file: {source.name}")
            source_file_rows.append({"working_filename": source.name, "row_count": rows_in_source})
    if count == 0:
        raise FxcmError(f"empty source series: {symbol}")
    return {
        "symbol": symbol,
        "timeframe": "H1",
        "timestamp_semantics": "UTC_BAR_OPEN",
        "observed_timestamps_working_filename": observed_path.name,
        "observed_timestamps_sha256": sha256_file(observed_path),
        "bid_working_sha256": sha256_file(bid_path),
        "ask_working_sha256": sha256_file(ask_path),
        "bar_count": count,
        "first_timestamp_utc": first,
        "last_timestamp_utc": last,
        "gap_segment_count": gaps,
        "missing_hour_slot_count": missing_slots,
        "source_file_rows": source_file_rows,
    }


def row_values(row: dict[str, str], side: str) -> list[str]:
    return [row[f"{side}{name}"] for name in ("Open", "High", "Low", "Close")]


def reject_outcomes(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in PROHIBITED_FIELDS:
                raise FxcmError(f"prohibited outcome field: {key}")
            reject_outcomes(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_outcomes(nested)


def inventory_aggregate_sha(inventories: list[dict]) -> str:
    digest = hashlib.sha256()
    for item in sorted(inventories, key=lambda value: value["observed_timestamps_working_filename"]):
        line = (
            f'{item["observed_timestamps_working_filename"]}\0{item["observed_timestamps_sha256"]}'
            f'\0{item["bar_count"]}\0{item["first_timestamp_utc"]}\0{item["last_timestamp_utc"]}\n'
        )
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def expected_report_paths(contract: dict, manifest: bool) -> set[str]:
    paths = {"EXPLORATORY_FXCM_INVENTORY.json"}
    if manifest:
        paths.add("artifact_manifest_sha256.txt")
    return paths


def validate_report_tree(report_dir: Path, contract: dict, manifest: bool) -> None:
    actual = set()
    for path in report_dir.rglob("*"):
        if path.is_symlink():
            raise FxcmError("symlink in report")
        if path.is_file():
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise FxcmError("non-regular report file")
            actual.add(path.relative_to(report_dir).as_posix())
    if actual != expected_report_paths(contract, manifest):
        raise FxcmError("report exact path mismatch")


def run(contract_path: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = load_contract(contract_path)
    if work_dir.exists() or report_dir.exists():
        raise FileExistsError("work/report directories must be new")
    raw = work_dir / "raw"
    prices = work_dir / "prices"
    observed = work_dir / "observed_timestamps"
    raw.mkdir(parents=True)
    prices.mkdir()
    observed.mkdir()
    report_dir.mkdir(parents=True)
    opener = urllib.request.build_opener(RejectRedirects())
    downloads = []
    source_paths: dict[str, list[Path]] = {symbol: [] for symbol in contract["symbols"]}
    total_bytes = 0
    for symbol in contract["symbols"]:
        for year in contract["years"]:
            for week in range(1, contract["weeks_per_year"] + 1):
                url = f'{contract["provider"]["base_url"]}/{symbol}/{year}/{week}.csv.gz'
                destination = raw / f"{symbol}_{year}_{week:02d}.csv.gz"
                entry = download(url, destination, opener)
                total_bytes += entry["bytes"]
                if total_bytes > MAX_TOTAL_GZIP_BYTES:
                    raise FxcmError("total compressed download limit exceeded")
                downloads.append({"symbol": symbol, "year": year, "week": week, **entry})
                source_paths[symbol].append(destination)
                time.sleep(REQUEST_PAUSE_SECONDS)
    if len(downloads) != contract["expected_download_count"]:
        raise FxcmError("download count mismatch")
    inventories = [process_symbol(symbol, source_paths[symbol], prices, observed) for symbol in contract["symbols"]]
    period_end = datetime(2018, 12, 31, tzinfo=UTC)
    for item in inventories:
        last = datetime.strptime(item["last_timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        item["trailing_hours_to_contract_end"] = int((period_end - last).total_seconds()) // 3600
    report = {
        "schema_version": "phase9-exploratory-fxcm-inventory-v1.0.0",
        "status": "EXPLORATORY_FX8_H1_ACQUISITION_INTEGRITY_PASS_GAPS_UNADJUDICATED",
        "track": contract["track"],
        "run_identity": {"run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"), "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"), "head_sha": os.getenv("GITHUB_SHA", "LOCAL")},
        "contract_sha256": sha256_file(contract_path),
        "provider": contract["provider"],
        "source_downloads": downloads,
        "source_download_count": len(downloads),
        "source_download_total_bytes": total_bytes,
        "observed_bar_inventory": inventories,
        "observed_bar_inventory_aggregate_sha256": inventory_aggregate_sha(inventories),
        "exploratory_acquisition_executed": True,
        "exploratory_price_working_files_created": 16,
        "persistent_price_files": 0,
        "formal_phase9_price_files_acquired": 0,
        "provider_schedule_inventory_claimed": False,
        "provider_schedule_gate_passed": False,
        "full_quality_gate_passed": False,
        "candidate_signal_counts_calculated": False,
        "formal_count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "forbidden_market_period_request_attempted": False,
        "remaining_missing_symbols": ["XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD"],
        "remaining_missing_timeframes": ["M15"],
    }
    reject_outcomes(report)
    write_new_json(report_dir / "EXPLORATORY_FXCM_INVENTORY.json", report)
    validate_report_tree(report_dir, contract, False)
    return report


def seal_manifest(report_dir: Path, contract: dict) -> None:
    manifest = report_dir / "artifact_manifest_sha256.txt"
    with manifest.open("x", encoding="utf-8", newline="\n") as handle:
        for path in sorted(item for item in report_dir.rglob("*") if item.is_file()):
            handle.write(f"{sha256_file(path)}  {path.relative_to(report_dir).as_posix()}\n")
    validate_report_tree(report_dir, contract, True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise FxcmError("exact confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise FxcmError("explicit personal non-commercial FXCM EULA confirmation required")
    contract = load_contract(args.contract)
    run(args.contract, args.work_dir, args.report_dir)
    seal_manifest(args.report_dir, contract)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
