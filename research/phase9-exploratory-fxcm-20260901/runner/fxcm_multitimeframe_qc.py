#!/usr/bin/env python3
"""Acquire FXCM FX8 m1/H1, derive M15/H4/D1, and emit price-free MTF QC."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import ssl
import stat
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import zip_longest
from pathlib import Path
from typing import Iterator


CONFIRMATION = "RUN_EXPLORATORY_FXCM_FX8_MTF_2017_2018_QC_ONLY_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
UTC = timezone.utc
START = datetime(2017, 1, 1, tzinfo=UTC)
END = datetime(2018, 12, 31, tzinfo=UTC)
SYMBOLS = ("AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY", "GBPUSD", "USDJPY")
DIRECT_PERIODICITIES = ("m1", "H1")
SIDES = ("bid", "ask")
FINAL_TIMEFRAMES = ("M15", "H1", "H4", "D1")
EXPECTED_HEADER = [
    "DateTime", "BidOpen", "BidHigh", "BidLow", "BidClose",
    "AskOpen", "AskHigh", "AskLow", "AskClose",
]
WORKING_HEADER = ["timestamp_utc", "open", "high", "low", "close"]
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_GZIP_BYTES = 32 * 1024 * 1024
MAX_TOTAL_GZIP_BYTES = 8 * 1024 * 1024 * 1024
MAX_SYMBOL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
DOWNLOAD_MAX_ATTEMPTS = 4
DOWNLOAD_RETRY_DELAYS_SECONDS = (1.0, 2.0, 4.0)
REQUEST_PAUSE_SECONDS = 0.05
PROHIBITED_FIELDS = {
    "signal", "signals", "signal_count", "signal_counts", "entry", "entries",
    "candidate_count", "setup_count", "trigger_count", "episode", "episodes",
    "control_count", "trade_count", "return", "returns", "return_sign", "edge", "mfe", "mae",
    "win", "wins", "loss", "losses", "win_rate", "profit_factor", "drawdown",
    "profit", "pnl", "expectancy", "cumulative_r", "p_value", "pvalue",
    "confidence_interval", "ci", "rank", "rankings", "outcome", "outcomes",
    "outcome_chart", "equity_curve", "sharpe", "sortino",
}
REPORT_KEYS = {
    "schema_version", "status", "track", "run_identity", "contract_sha256",
    "execution_contract_sha256", "prior_h1_inventory_sha256", "h1_source_identity_exact_match",
    "provider", "coverage", "source_download_count", "source_download_total_bytes",
    "source_downloads", "direct_series_inventory", "direct_series_inventory_sha256",
    "crossed_open_quote_total_count", "crossed_open_quote_inventory_sha256",
    "derivation_inventory", "derivation_inventory_sha256", "final_series_count",
    "final_series_inventory", "final_series_inventory_sha256", "bid_ask_reconciliation",
    "m1_derived_h1_vs_direct_h1", "mtf_qc_execution_completed",
    "exploratory_mtf_structural_qc_passed", "forward_fill_count",
    "price_interpolation_count", "persistent_price_files", "formal_phase9_price_files_acquired",
    "provider_schedule_inventory_claimed", "provider_schedule_version_status",
    "formal_phase9_authorization_effect", "acquisition_authorized", "count_only_authorized",
    "formal_full_quality_gate_passed", "candidate_signal_counts_calculated",
    "research_outcomes_calculated", "outcome_fields",
    "forbidden_market_period_request_attempted", "official_candledata_out_of_scope_not_requested",
    "tick_volume_available",
}


class FxcmMtfError(RuntimeError):
    pass


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise FxcmMtfError(f"unexpected redirect {code}")


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(text: str) -> datetime:
    for pattern in ("%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=UTC)
        except ValueError:
            pass
    raise FxcmMtfError("invalid FXCM timestamp") from None


def parse_decimal(text: str | None, field: str) -> Decimal:
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        raise FxcmMtfError(f"invalid numeric field: {field}") from None
    if not value.is_finite() or value <= 0:
        raise FxcmMtfError(f"non-finite or non-positive field: {field}")
    return value


def validate_bar(bar: Bar, label: str) -> None:
    if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
        raise FxcmMtfError(f"{label}: invalid OHLC geometry")


def load_contract(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    provider = value.get("provider", {})
    checks = (
        (value.get("schema_version") == "phase9-exploratory-fxcm-mtf-data-v1.0.0", "schema"),
        (value.get("status") == "FROZEN_DATA_REQUIREMENTS_ACQUISITION_NOT_STARTED", "status"),
        (value.get("track") == "EXPLORATORY_FX8_MULTI_TIMEFRAME_NOT_FORMAL_PHASE9", "track"),
        (value.get("formal_phase9_authorization_effect") is False, "Formal effect"),
        (provider.get("name") == "FXCM", "provider name"),
        (provider.get("dataset") == "MarketData CandleData", "dataset"),
        (provider.get("source_repository") == "https://github.com/fxcm/MarketData", "source repository"),
        (provider.get("base_url_template") == "https://candledata.fxcorporate.com/{periodicity}/{instrument}/{year}/{week}.csv.gz", "URL template"),
        (provider.get("published_direct_periodicities") == ["m1", "H1", "D1"], "published periods"),
        (provider.get("timestamp_timezone") == "UTC", "timezone"),
        (provider.get("timestamp_semantics") == "ROW_TIMESTAMP_ASSUMED_BAR_OPEN_NOT_PROVIDER_EXPLICIT", "timestamp semantics"),
        (value.get("provider", {}).get("requested_direct_periodicities") == ["m1", "H1"], "direct periods"),
        (value.get("provider", {}).get("price_sides") == ["BID", "ASK"], "sides"),
        (value.get("provider", {}).get("tick_volume_available") is False, "volume"),
        (value.get("coverage", {}).get("symbols") == list(SYMBOLS), "symbols"),
        (value.get("coverage", {}).get("start_inclusive") == iso(START), "start"),
        (value.get("coverage", {}).get("end_exclusive") == iso(END), "end"),
        (value.get("coverage", {}).get("years") == [2017, 2018], "years"),
        (value.get("coverage", {}).get("weeks_per_year") == 52, "weeks"),
        (value.get("coverage", {}).get("expected_direct_source_object_count") == 1664, "objects"),
        (value.get("final_timeframes") == list(FINAL_TIMEFRAMES), "final timeframes"),
        (value.get("series_inventory", {}).get("expected_final_series_count") == 64, "series count"),
        (value.get("derivation_rules", {}).get("M15", {}).get("required_complete_source_bars") == 15, "M15 bucket"),
        (value.get("derivation_rules", {}).get("H4", {}).get("required_complete_source_bars") == 4, "H4 bucket"),
        (value.get("derivation_rules", {}).get("D1", {}).get("required_complete_source_bars") == 24, "D1 bucket"),
        (value.get("derivation_rules", {}).get("forward_fill_allowed") is False, "fill"),
        (value.get("derivation_rules", {}).get("price_interpolation_allowed") is False, "interpolation"),
        (value.get("research_gates", {}).get("acquisition_run_may_calculate_signal_counts") is False, "signal gate"),
        (value.get("research_gates", {}).get("acquisition_run_may_calculate_returns_or_outcomes") is False, "outcome gate"),
        (value.get("research_gates", {}).get("outcome_fields") == [], "outcome fields"),
    )
    for passed, label in checks:
        if not passed:
            raise FxcmMtfError(f"frozen MTF contract mismatch: {label}")
    return value


def load_execution_contract(path: Path, requirements_path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    requirements = value.get("requirements", {})
    checks = (
        (value.get("schema_version") == "phase9-exploratory-fxcm-mtf-execution-v1.0.0", "schema"),
        (value.get("status") == "FROZEN_BEFORE_FIRST_MTF_PRICE_RUN", "status"),
        (value.get("track") == "EXPLORATORY_FX8_MULTI_TIMEFRAME_NOT_FORMAL_PHASE9", "track"),
        (requirements.get("git_blob_sha") == "66dd82822cedeefee01c2b30ad6b26febf8e8c66", "requirements blob"),
        (requirements.get("sha256") == sha256_file(requirements_path), "requirements SHA"),
        (value.get("source_scope", {}).get("expected_source_object_count") == 1664, "objects"),
        (value.get("source_scope", {}).get("redirects_allowed") is False, "redirects"),
        (value.get("prior_h1_identity", {}).get("exact_match_required") is True, "H1 identity"),
        (value.get("prior_h1_identity", {}).get("canonical_source_download_count") == 832, "H1 count"),
        (value.get("bucket_population", {}).get("rule") == "SOURCE_TOUCHED_FIXED_UTC_BUCKETS_ONLY", "bucket population"),
        (value.get("bucket_population", {}).get("provider_schedule_claimed") is False, "schedule claim"),
        (value.get("h1_reconciliation", {}).get("comparison") == "EXACT_DECIMAL_NUMERIC_OHLC_EQUALITY_AT_MATCHED_TIMESTAMP", "H1 comparison"),
        (value.get("h1_reconciliation", {}).get("tolerance") == "NONE", "H1 tolerance"),
        (value.get("completion", {}).get("structural_qc_pass_requires_h1_ohlc_mismatch_count") == 0, "H1 pass threshold"),
        (value.get("scientific_state", {}).get("count_only_authorized") is False, "Count-only"),
        (value.get("scientific_state", {}).get("candidate_signal_counts_calculated") is False, "signals"),
        (value.get("scientific_state", {}).get("research_outcomes_calculated") is False, "outcomes"),
        (value.get("scientific_state", {}).get("outcome_fields") == [], "outcome fields"),
    )
    for passed, label in checks:
        if not passed:
            raise FxcmMtfError(f"frozen MTF execution contract mismatch: {label}")
    return value


def validate_prior_h1_identity(downloads: list[dict], prior_path: Path, execution: dict) -> str:
    expected_sha = execution["prior_h1_identity"]["canonical_inventory_sha256"]
    if sha256_file(prior_path) != expected_sha:
        raise FxcmMtfError("prior canonical H1 inventory SHA mismatch")
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    fields = execution["prior_h1_identity"]["match_fields"]
    expected = [{field: row[field] for field in fields} for row in prior["source_downloads"]]
    actual = [{field: row[field] for field in fields} for row in downloads if row["periodicity"] == "H1"]
    if len(expected) != 832 or actual != expected:
        raise FxcmMtfError("direct H1 source identity differs from canonical prior run")
    if canonical_sha(expected) != execution["prior_h1_identity"]["canonical_source_identity_aggregate_sha256"]:
        raise FxcmMtfError("prior H1 source identity aggregate mismatch")
    return expected_sha


def download(url: str, destination: Path, opener) -> dict:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("download destination must be new")
    for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, headers={"User-Agent": "phase9-exploratory-fxcm-mtf-qc/1.0"})
        try:
            with opener.open(request, timeout=60) as response:
                if response.status != 200:
                    raise FxcmMtfError(f"unexpected status {response.status}")
                total = 0
                with destination.open("xb") as handle:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_GZIP_BYTES:
                            raise FxcmMtfError("source object exceeds byte limit")
                        handle.write(block)
            break
        except urllib.error.HTTPError as error:
            destination.unlink(missing_ok=True)
            raise FxcmMtfError(f"unexpected status {error.code}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError, ssl.SSLError):
            destination.unlink(missing_ok=True)
            if attempt == DOWNLOAD_MAX_ATTEMPTS:
                raise FxcmMtfError("transient download failure after bounded retries") from None
            time.sleep(DOWNLOAD_RETRY_DELAYS_SECONDS[attempt - 1])
    if destination.stat().st_size < 20:
        raise FxcmMtfError("source object too small")
    with destination.open("rb") as handle:
        if handle.read(2) != b"\x1f\x8b":
            raise FxcmMtfError("source object is not gzip")
    return {"url": url, "bytes": destination.stat().st_size, "sha256": sha256_file(destination)}


def write_bar(writer: csv.writer, bar: Bar) -> None:
    writer.writerow([iso(bar.timestamp), *(format(getattr(bar, field), "f") for field in ("open", "high", "low", "close"))])


def process_direct_series(
    symbol: str, periodicity: str, sources: list[Path], output_dir: Path
) -> dict:
    bid_path = output_dir / f"{symbol}_{periodicity}_bid.csv"
    ask_path = output_dir / f"{symbol}_{periodicity}_ask.csv"
    step = timedelta(minutes=1) if periodicity == "m1" else timedelta(hours=1)
    previous = None
    previous_usable = None
    first = None
    last = None
    observed = 0
    usable = 0
    gap_segments = 0
    missing_slots = 0
    usable_gap_segments = 0
    usable_missing_slots = 0
    crossed_count = 0
    crossed_digest = hashlib.sha256()
    observed_timestamp_digest = hashlib.sha256()
    usable_timestamp_digest = hashlib.sha256()
    uncompressed = 0
    source_rows = []
    with bid_path.open("x", encoding="utf-8", newline="") as bid_handle, ask_path.open("x", encoding="utf-8", newline="") as ask_handle:
        bid_writer = csv.writer(bid_handle, lineterminator="\n")
        ask_writer = csv.writer(ask_handle, lineterminator="\n")
        bid_writer.writerow(WORKING_HEADER)
        ask_writer.writerow(WORKING_HEADER)
        for source in sources:
            rows = 0
            source_sha = sha256_file(source)
            with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != EXPECTED_HEADER:
                    raise FxcmMtfError("unexpected FXCM CSV header")
                for row_ordinal, row in enumerate(reader, 1):
                    rows += 1
                    if set(row) != set(EXPECTED_HEADER) or any(value is None for value in row.values()):
                        raise FxcmMtfError("invalid FXCM CSV row shape")
                    uncompressed += sum(len(value) for value in row.values()) + len(row)
                    if uncompressed > MAX_SYMBOL_UNCOMPRESSED_BYTES:
                        raise FxcmMtfError("symbol uncompressed byte limit exceeded")
                    timestamp = parse_timestamp(row["DateTime"])
                    if not (START <= timestamp < END):
                        raise FxcmMtfError("forbidden timestamp")
                    if timestamp.second or timestamp.microsecond or (periodicity == "H1" and timestamp.minute):
                        raise FxcmMtfError("timestamp not aligned to direct periodicity")
                    if previous is not None:
                        delta_slots = int((timestamp - previous) / step)
                        if delta_slots <= 0:
                            raise FxcmMtfError("direct timestamps not strictly increasing")
                        if delta_slots > 1:
                            gap_segments += 1
                            missing_slots += delta_slots - 1
                    previous = timestamp
                    bid = Bar(timestamp, *(parse_decimal(row[f"Bid{name}"], f"Bid{name}") for name in ("Open", "High", "Low", "Close")))
                    ask = Bar(timestamp, *(parse_decimal(row[f"Ask{name}"], f"Ask{name}") for name in ("Open", "High", "Low", "Close")))
                    validate_bar(bid, "BID")
                    validate_bar(ask, "ASK")
                    stamp_line = iso(timestamp) + "\n"
                    observed_timestamp_digest.update(stamp_line.encode("ascii"))
                    observed += 1
                    first = first or timestamp
                    last = timestamp
                    if ask.open < bid.open:
                        crossed_count += 1
                        crossed_digest.update(
                            f"{symbol}\0{periodicity}\0{source.name}\0{source_sha}\0{row_ordinal}\n".encode("utf-8")
                        )
                        continue
                    if previous_usable is not None:
                        usable_delta_slots = int((timestamp - previous_usable) / step)
                        if usable_delta_slots <= 0:
                            raise FxcmMtfError("usable timestamps not strictly increasing")
                        if usable_delta_slots > 1:
                            usable_gap_segments += 1
                            usable_missing_slots += usable_delta_slots - 1
                    previous_usable = timestamp
                    usable_timestamp_digest.update(stamp_line.encode("ascii"))
                    write_bar(bid_writer, bid)
                    write_bar(ask_writer, ask)
                    usable += 1
            if rows == 0:
                raise FxcmMtfError("empty weekly source object")
            source_rows.append({"working_filename": source.name, "row_count": rows})
    if not observed or not usable:
        raise FxcmMtfError("empty direct series")
    return {
        "symbol": symbol,
        "periodicity": periodicity,
        "observed_bar_count": observed,
        "usable_bar_count": usable,
        "crossed_open_quote_count": crossed_count,
        "crossed_open_quote_event_sha256": crossed_digest.hexdigest(),
        "first_timestamp_utc": iso(first),
        "last_timestamp_utc": iso(last),
        "observed_timestamp_sha256": observed_timestamp_digest.hexdigest(),
        "usable_timestamp_sha256": usable_timestamp_digest.hexdigest(),
        "gap_segment_count": gap_segments,
        "missing_nominal_slot_count": missing_slots,
        "usable_gap_segment_count": usable_gap_segments,
        "usable_missing_nominal_slot_count": usable_missing_slots,
        "working_bid_sha256": sha256_file(bid_path),
        "working_ask_sha256": sha256_file(ask_path),
        "source_file_rows": source_rows,
    }


def iter_working(path: Path) -> Iterator[Bar]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != WORKING_HEADER:
            raise FxcmMtfError("working CSV header mismatch")
        previous = None
        for row in reader:
            try:
                timestamp = datetime.strptime(row["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            except (TypeError, ValueError):
                raise FxcmMtfError("working timestamp malformed") from None
            bar = Bar(timestamp, *(parse_decimal(row[field], field) for field in ("open", "high", "low", "close")))
            validate_bar(bar, "working")
            if previous is not None and timestamp <= previous:
                raise FxcmMtfError("working timestamps not strictly increasing")
            previous = timestamp
            yield bar


def bucket_open(value: datetime, timeframe: str) -> datetime:
    if timeframe == "M15":
        return value.replace(minute=(value.minute // 15) * 15, second=0, microsecond=0)
    if timeframe == "H1":
        return value.replace(minute=0, second=0, microsecond=0)
    if timeframe == "H4":
        return value.replace(hour=(value.hour // 4) * 4, minute=0, second=0, microsecond=0)
    if timeframe == "D1":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    raise FxcmMtfError("unsupported derived timeframe")


def expected_bucket_times(open_time: datetime, timeframe: str) -> list[datetime]:
    if timeframe == "M15":
        return [open_time + timedelta(minutes=index) for index in range(15)]
    if timeframe == "H1":
        return [open_time + timedelta(minutes=index) for index in range(60)]
    if timeframe == "H4":
        return [open_time + timedelta(hours=index) for index in range(4)]
    if timeframe == "D1":
        return [open_time + timedelta(hours=index) for index in range(24)]
    raise FxcmMtfError("unsupported derived timeframe")


def aggregate_complete(source: Path, destination: Path, timeframe: str) -> dict:
    candidate_buckets = 0
    complete_buckets = 0
    dropped_buckets = 0
    dropped_event_digest = hashlib.sha256()
    with destination.open("x", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(WORKING_HEADER)
        current_open = None
        rows: list[Bar] = []

        def flush() -> None:
            nonlocal candidate_buckets, complete_buckets, dropped_buckets, rows, current_open
            if current_open is None:
                return
            candidate_buckets += 1
            if [bar.timestamp for bar in rows] != expected_bucket_times(current_open, timeframe):
                dropped_buckets += 1
                dropped_event_digest.update(f"{iso(current_open)}\0{len(rows)}\n".encode("ascii"))
            else:
                aggregated = Bar(
                    current_open, rows[0].open, max(bar.high for bar in rows),
                    min(bar.low for bar in rows), rows[-1].close,
                )
                write_bar(writer, aggregated)
                complete_buckets += 1

        for bar in iter_working(source):
            next_open = bucket_open(bar.timestamp, timeframe)
            if current_open is not None and next_open != current_open:
                flush()
                rows = []
            current_open = next_open
            rows.append(bar)
        flush()
    if not complete_buckets:
        raise FxcmMtfError(f"no complete {timeframe} bucket")
    return {
        "source_working_filename": source.name,
        "output_working_filename": destination.name,
        "output_timeframe": timeframe,
        "candidate_bucket_count": candidate_buckets,
        "complete_bucket_count": complete_buckets,
        "dropped_incomplete_bucket_count": dropped_buckets,
        "dropped_bucket_event_sha256": dropped_event_digest.hexdigest(),
        "forward_fill_count": 0,
        "price_interpolation_count": 0,
        "output_working_sha256": sha256_file(destination),
    }


def scan_final_series(path: Path, symbol: str, timeframe: str, side: str, source: str) -> dict:
    step = {"M15": timedelta(minutes=15), "H1": timedelta(hours=1), "H4": timedelta(hours=4), "D1": timedelta(days=1)}[timeframe]
    count = 0
    first = None
    last = None
    previous = None
    gap_segments = 0
    missing_slots = 0
    timestamp_digest = hashlib.sha256()
    for bar in iter_working(path):
        if bar.timestamp != bucket_open(bar.timestamp, timeframe):
            raise FxcmMtfError("final series timestamp alignment mismatch")
        if previous is not None:
            slots = int((bar.timestamp - previous) / step)
            if slots > 1:
                gap_segments += 1
                missing_slots += slots - 1
        previous = bar.timestamp
        first = first or bar.timestamp
        last = bar.timestamp
        timestamp_digest.update((iso(bar.timestamp) + "\n").encode("ascii"))
        count += 1
    if not count:
        raise FxcmMtfError("empty final series")
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "side": side,
        "source": source,
        "working_filename": path.name,
        "bar_count": count,
        "first_timestamp_utc": iso(first),
        "last_timestamp_utc": iso(last),
        "timestamp_sha256": timestamp_digest.hexdigest(),
        "working_file_sha256": sha256_file(path),
        "gap_segment_count": gap_segments,
        "missing_nominal_slot_count": missing_slots,
    }


def reconcile_pair(bid_path: Path, ask_path: Path, symbol: str, timeframe: str) -> dict:
    count = 0
    for bid, ask in zip_longest(iter_working(bid_path), iter_working(ask_path)):
        if bid is None or ask is None or bid.timestamp != ask.timestamp:
            raise FxcmMtfError("BID/ASK timestamp exact-match QC failed")
        if ask.open < bid.open:
            raise FxcmMtfError("crossed open survived quarantine")
        count += 1
    return {"symbol": symbol, "timeframe": timeframe, "matched_timestamp_count": count, "exact_match": True}


def reconcile_h1(derived_path: Path, direct_path: Path, symbol: str, side: str) -> dict:
    derived = iter(iter_working(derived_path))
    direct = iter(iter_working(direct_path))
    left = next(derived, None)
    right = next(direct, None)
    matched = 0
    exact = 0
    mismatch = 0
    derived_only = 0
    direct_only = 0
    mismatch_digest = hashlib.sha256()
    while left is not None or right is not None:
        if right is None or (left is not None and left.timestamp < right.timestamp):
            derived_only += 1
            left = next(derived, None)
        elif left is None or right.timestamp < left.timestamp:
            direct_only += 1
            right = next(direct, None)
        else:
            matched += 1
            left_values = (left.open, left.high, left.low, left.close)
            right_values = (right.open, right.high, right.low, right.close)
            if left_values == right_values:
                exact += 1
            else:
                mismatch += 1
                left_hash = hashlib.sha256("|".join(format(value, "f") for value in left_values).encode("ascii")).hexdigest()
                right_hash = hashlib.sha256("|".join(format(value, "f") for value in right_values).encode("ascii")).hexdigest()
                mismatch_digest.update(f"{iso(left.timestamp)}\0{left_hash}\0{right_hash}\n".encode("ascii"))
            left = next(derived, None)
            right = next(direct, None)
    return {
        "symbol": symbol,
        "side": side,
        "matched_timestamp_count": matched,
        "exact_ohlc_match_count": exact,
        "ohlc_mismatch_count": mismatch,
        "m1_derived_only_count": derived_only,
        "direct_h1_only_count": direct_only,
        "ohlc_mismatch_event_sha256": mismatch_digest.hexdigest(),
        "role": "QC_ONLY_DIRECT_H1_REMAINS_CANONICAL",
    }


def reject_prohibited(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in PROHIBITED_FIELDS:
                raise FxcmMtfError(f"prohibited research field: {key}")
            reject_prohibited(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_prohibited(nested)


def validate_report(report: dict) -> None:
    if set(report) != REPORT_KEYS:
        raise FxcmMtfError("MTF report exact key mismatch")
    for field in ("contract_sha256", "execution_contract_sha256", "prior_h1_inventory_sha256"):
        if not isinstance(report[field], str) or not HEX64.fullmatch(report[field]):
            raise FxcmMtfError(f"invalid report SHA-256: {field}")
    if report["source_download_count"] != 1664 or len(report["source_downloads"]) != 1664:
        raise FxcmMtfError("source download inventory count mismatch")
    direct_ids = {(row["symbol"], row["periodicity"]) for row in report["direct_series_inventory"]}
    if direct_ids != {(symbol, periodicity) for symbol in SYMBOLS for periodicity in DIRECT_PERIODICITIES}:
        raise FxcmMtfError("direct series exact set mismatch")
    derivation_ids = {(row["symbol"], row["output_timeframe"], row["side"]) for row in report["derivation_inventory"]}
    if derivation_ids != {(symbol, timeframe, side) for symbol in SYMBOLS for timeframe in FINAL_TIMEFRAMES for side in SIDES}:
        raise FxcmMtfError("derivation audit exact set mismatch")
    if report["final_series_count"] != 64 or len(report["final_series_inventory"]) != 64:
        raise FxcmMtfError("final 64-series inventory mismatch")
    identities = {(row["symbol"], row["timeframe"], row["side"]) for row in report["final_series_inventory"]}
    expected = {(symbol, timeframe, side) for symbol in SYMBOLS for timeframe in FINAL_TIMEFRAMES for side in SIDES}
    if identities != expected:
        raise FxcmMtfError("final series exact set mismatch")
    boolean_false_fields = (
        "provider_schedule_inventory_claimed", "formal_full_quality_gate_passed",
        "formal_phase9_authorization_effect", "acquisition_authorized", "count_only_authorized",
        "candidate_signal_counts_calculated", "research_outcomes_calculated",
        "forbidden_market_period_request_attempted", "tick_volume_available",
    )
    if any(report[field] is not False for field in boolean_false_fields):
        raise FxcmMtfError("frozen false report gate mismatch")
    for field in ("persistent_price_files", "formal_phase9_price_files_acquired"):
        if type(report[field]) is not int or report[field] != 0:
            raise FxcmMtfError("persistent/formal price file count must be integer zero")
    if report["h1_source_identity_exact_match"] is not True:
        raise FxcmMtfError("H1 source identity must exactly match the prior canonical run")
    if len(report["bid_ask_reconciliation"]) != 32 or len(report["m1_derived_h1_vs_direct_h1"]) != 16:
        raise FxcmMtfError("reconciliation inventory count mismatch")
    if report["outcome_fields"] != [] or report["forward_fill_count"] != 0 or report["price_interpolation_count"] != 0:
        raise FxcmMtfError("prohibited calculation/fill state")
    if report["mtf_qc_execution_completed"] is not True:
        raise FxcmMtfError("MTF QC execution completion flag mismatch")
    mismatches = sum(row["ohlc_mismatch_count"] for row in report["m1_derived_h1_vs_direct_h1"])
    if report["exploratory_mtf_structural_qc_passed"] is not (mismatches == 0):
        raise FxcmMtfError("MTF structural QC pass flag mismatch")
    if report["provider_schedule_version_status"] != "UNPROVEN_NOT_EVALUATED":
        raise FxcmMtfError("provider schedule status must remain unproven")
    reject_prohibited(report)


def write_new_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def validate_report_tree(report_dir: Path, manifest: bool) -> None:
    expected = {"EXPLORATORY_FXCM_MTF_QC.json"}
    if manifest:
        expected.add("artifact_manifest_sha256.txt")
    actual = set()
    for path in report_dir.rglob("*"):
        if path.is_symlink():
            raise FxcmMtfError("symlink in report")
        if path.is_file():
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise FxcmMtfError("non-regular report file")
            actual.add(path.relative_to(report_dir).as_posix())
    if actual != expected:
        raise FxcmMtfError("report exact path mismatch")


def seal_manifest(report_dir: Path) -> None:
    payload = report_dir / "EXPLORATORY_FXCM_MTF_QC.json"
    manifest = report_dir / "artifact_manifest_sha256.txt"
    with manifest.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{sha256_file(payload)}  {payload.name}\n")
    validate_report_tree(report_dir, True)


def run(
    contract_path: Path, execution_contract_path: Path, prior_h1_inventory_path: Path,
    work_dir: Path, report_dir: Path,
) -> dict:
    contract = load_contract(contract_path)
    execution = load_execution_contract(execution_contract_path, contract_path)
    if work_dir.exists() or report_dir.exists():
        raise FileExistsError("work/report directories must be new")
    raw_dir = work_dir / "raw"
    direct_dir = work_dir / "direct"
    derived_dir = work_dir / "derived"
    qc_dir = work_dir / "qc"
    for path in (raw_dir, direct_dir, derived_dir, qc_dir, report_dir):
        path.mkdir(parents=True, mode=0o700)
    opener = urllib.request.build_opener(RejectRedirects())
    downloads = []
    source_paths: dict[tuple[str, str], list[Path]] = {
        (symbol, periodicity): [] for symbol in SYMBOLS for periodicity in DIRECT_PERIODICITIES
    }
    total_bytes = 0
    for periodicity in DIRECT_PERIODICITIES:
        for symbol in SYMBOLS:
            period_dir = raw_dir / periodicity / symbol
            period_dir.mkdir(parents=True)
            for year in contract["coverage"]["years"]:
                for week in range(1, contract["coverage"]["weeks_per_year"] + 1):
                    url = contract["provider"]["base_url_template"].format(
                        periodicity=periodicity, instrument=symbol, year=year, week=week
                    )
                    destination = period_dir / f"{symbol}_{periodicity}_{year}_{week:02d}.csv.gz"
                    entry = download(url, destination, opener)
                    total_bytes += entry["bytes"]
                    if total_bytes > MAX_TOTAL_GZIP_BYTES:
                        raise FxcmMtfError("total compressed download limit exceeded")
                    downloads.append({
                        "symbol": symbol, "periodicity": periodicity, "year": year, "week": week,
                        "working_filename": destination.name, **entry,
                    })
                    source_paths[(symbol, periodicity)].append(destination)
                    time.sleep(REQUEST_PAUSE_SECONDS)
    if len(downloads) != 1664:
        raise FxcmMtfError("direct source object count mismatch")
    expected_urls = [
        contract["provider"]["base_url_template"].format(
            periodicity=periodicity, instrument=symbol, year=year, week=week
        )
        for periodicity in DIRECT_PERIODICITIES for symbol in SYMBOLS
        for year in contract["coverage"]["years"]
        for week in range(1, contract["coverage"]["weeks_per_year"] + 1)
    ]
    actual_urls = [row["url"] for row in downloads]
    if actual_urls != expected_urls or len(actual_urls) != len(set(actual_urls)):
        raise FxcmMtfError("direct source URL exact set/order mismatch")
    prior_h1_sha = validate_prior_h1_identity(downloads, prior_h1_inventory_path, execution)

    direct_inventory = [
        process_direct_series(symbol, periodicity, source_paths[(symbol, periodicity)], direct_dir)
        for symbol in SYMBOLS for periodicity in DIRECT_PERIODICITIES
    ]
    derivations = []
    for symbol in SYMBOLS:
        for side in SIDES:
            m1_source = direct_dir / f"{symbol}_m1_{side}.csv"
            h1_source = direct_dir / f"{symbol}_H1_{side}.csv"
            for timeframe, source, destination in (
                ("M15", m1_source, derived_dir / f"{symbol}_M15_{side}.csv"),
                ("H1", m1_source, qc_dir / f"{symbol}_m1_derived_H1_{side}.csv"),
                ("H4", h1_source, derived_dir / f"{symbol}_H4_{side}.csv"),
                ("D1", h1_source, derived_dir / f"{symbol}_D1_{side}.csv"),
            ):
                result = aggregate_complete(source, destination, timeframe)
                result.update({"symbol": symbol, "side": side})
                derivations.append(result)

    final_inventory = []
    bid_ask = []
    for symbol in SYMBOLS:
        for timeframe in FINAL_TIMEFRAMES:
            base_dir = direct_dir if timeframe == "H1" else derived_dir
            source_label = "DIRECT_H1" if timeframe == "H1" else ("DIRECT_M1" if timeframe == "M15" else "DIRECT_H1")
            bid_path = base_dir / f"{symbol}_{timeframe}_bid.csv"
            ask_path = base_dir / f"{symbol}_{timeframe}_ask.csv"
            for side, path in (("bid", bid_path), ("ask", ask_path)):
                final_inventory.append(scan_final_series(path, symbol, timeframe, side, source_label))
            bid_ask.append(reconcile_pair(bid_path, ask_path, symbol, timeframe))

    h1_reconciliation = [
        reconcile_h1(
            qc_dir / f"{symbol}_m1_derived_H1_{side}.csv",
            direct_dir / f"{symbol}_H1_{side}.csv",
            symbol, side,
        )
        for symbol in SYMBOLS for side in SIDES
    ]
    h1_mismatch_total = sum(row["ohlc_mismatch_count"] for row in h1_reconciliation)
    structural_pass = h1_mismatch_total == 0
    crossed_total = sum(row["crossed_open_quote_count"] for row in direct_inventory)
    report = {
        "schema_version": "phase9-exploratory-fxcm-mtf-qc-v1.0.0",
        "status": (
            "MTF_64_SERIES_STRUCTURAL_QC_PASS_WITH_QUARANTINE_AND_INCOMPLETE_BUCKET_DROPS"
            if structural_pass else
            "MTF_64_SERIES_EXECUTION_COMPLETE_H1_RECONCILIATION_MISMATCH_BLOCKED"
        ),
        "track": contract["track"],
        "run_identity": {
            "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"),
            "head_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        },
        "contract_sha256": sha256_file(contract_path),
        "execution_contract_sha256": sha256_file(execution_contract_path),
        "prior_h1_inventory_sha256": prior_h1_sha,
        "h1_source_identity_exact_match": True,
        "provider": contract["provider"],
        "coverage": contract["coverage"],
        "source_download_count": len(downloads),
        "source_download_total_bytes": total_bytes,
        "source_downloads": downloads,
        "direct_series_inventory": direct_inventory,
        "direct_series_inventory_sha256": canonical_sha(direct_inventory),
        "crossed_open_quote_total_count": crossed_total,
        "crossed_open_quote_inventory_sha256": canonical_sha([
            {key: row[key] for key in ("symbol", "periodicity", "crossed_open_quote_count", "crossed_open_quote_event_sha256")}
            for row in direct_inventory
        ]),
        "derivation_inventory": derivations,
        "derivation_inventory_sha256": canonical_sha(derivations),
        "final_series_count": len(final_inventory),
        "final_series_inventory": final_inventory,
        "final_series_inventory_sha256": canonical_sha(final_inventory),
        "bid_ask_reconciliation": bid_ask,
        "m1_derived_h1_vs_direct_h1": h1_reconciliation,
        "mtf_qc_execution_completed": True,
        "exploratory_mtf_structural_qc_passed": structural_pass,
        "forward_fill_count": 0,
        "price_interpolation_count": 0,
        "persistent_price_files": 0,
        "formal_phase9_price_files_acquired": 0,
        "provider_schedule_inventory_claimed": False,
        "provider_schedule_version_status": "UNPROVEN_NOT_EVALUATED",
        "formal_phase9_authorization_effect": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "formal_full_quality_gate_passed": False,
        "candidate_signal_counts_calculated": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "forbidden_market_period_request_attempted": False,
        "official_candledata_out_of_scope_not_requested": [
            "XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD"
        ],
        "tick_volume_available": False,
    }
    validate_report(report)
    write_new_json(report_dir / "EXPLORATORY_FXCM_MTF_QC.json", report)
    validate_report_tree(report_dir, False)
    seal_manifest(report_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--execution-contract", type=Path, required=True)
    parser.add_argument("--prior-h1-inventory", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise FxcmMtfError("exact MTF QC confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise FxcmMtfError("personal non-commercial FXCM EULA confirmation required")
    run(
        args.contract, args.execution_contract, args.prior_h1_inventory,
        args.work_dir, args.report_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
