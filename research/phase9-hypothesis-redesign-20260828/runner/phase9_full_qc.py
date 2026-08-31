#!/usr/bin/env python3
"""Outcome-free Phase 9 Full-QC primitives for synthetic preflight testing."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence


UTC = timezone.utc
PRICE_TOLERANCE = 1e-10
FROZEN_GROUPS = {
    "FX8": ("AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY", "GBPUSD", "USDJPY"),
    "METALS2": ("XAUUSD", "XAGUSD"),
    "ENERGY2": ("BRENTCMDUSD", "LIGHTCMDUSD"),
}


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("Bar timestamp must be timezone-aware UTC.")
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Bar values must be finite.")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("Bar prices must be positive.")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("Invalid OHLC geometry.")
        if self.volume < 0:
            raise ValueError("Bar volume must be nonnegative.")


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def timestamp_digest(values: Iterable[datetime]) -> str:
    payload = "".join(iso(item) + "\n" for item in sorted(values)).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def missing_segments(
    expected_scheduled: Sequence[datetime], observed: Sequence[datetime], step: timedelta
) -> dict:
    expected = sorted(expected_scheduled)
    if len(set(expected)) != len(expected):
        raise ValueError("Provider schedule contains duplicate timestamps.")
    observed_set = set(observed)
    if len(observed_set) != len(observed):
        raise ValueError("Observed schedule contains duplicate timestamps.")
    unknown = sorted(observed_set - set(expected))
    if unknown:
        raise ValueError(f"Observed bars outside provider schedule: {iso(unknown[0])}")
    missing = [value for value in expected if value not in observed_set]
    segments: list[dict] = []
    for value in missing:
        if segments and datetime.fromisoformat(
            segments[-1]["end_exclusive"].replace("Z", "+00:00")
        ) == value:
            segments[-1]["end_exclusive"] = iso(value + step)
            segments[-1]["slot_count"] += 1
        else:
            segments.append(
                {
                    "start": iso(value),
                    "end_exclusive": iso(value + step),
                    "slot_count": 1,
                    "classification": "SCHEDULED_BAR_MISSING",
                }
            )
    return {
        "expected_scheduled_slots": len(expected),
        "observed_slots": len(observed_set),
        "scheduled_missing_slots": len(missing),
        "missing_segments": segments,
        "classification_coverage": 1.0,
        "segments_truncated": False,
    }


def aggregate_bars(bars: Sequence[Bar], timestamp: datetime) -> Bar:
    if not bars:
        raise ValueError("Cannot aggregate an empty bucket.")
    ordered = sorted(bars, key=lambda item: item.timestamp)
    return Bar(
        timestamp=timestamp,
        open=ordered[0].open,
        high=max(item.high for item in ordered),
        low=min(item.low for item in ordered),
        close=ordered[-1].close,
        volume=sum(item.volume for item in ordered),
    )


def reconcile_m15_h1(m15: Sequence[Bar], h1: Bar) -> dict:
    expected = [h1.timestamp + timedelta(minutes=15 * index) for index in range(4)]
    by_time = {bar.timestamp: bar for bar in m15}
    if len(by_time) != len(m15):
        raise ValueError("Duplicate M15 timestamp in reconciliation bucket.")
    unknown = sorted(set(by_time) - set(expected))
    if unknown:
        raise ValueError(f"M15 timestamp outside H1 bucket: {iso(unknown[0])}")
    present = [by_time[value] for value in expected if value in by_time]
    if len(present) != 4:
        return {
            "bucket_open": iso(h1.timestamp),
            "status": "SOURCE_MISSING",
            "expected_m15_slots": 4,
            "present_m15_slots": len(present),
        }
    rebuilt = aggregate_bars(present, h1.timestamp)
    differences = {
        name: abs(getattr(rebuilt, name) - getattr(h1, name))
        for name in ("open", "high", "low", "close", "volume")
    }
    volume_tolerance = (len(present) + 1) * PRICE_TOLERANCE / 2
    mismatch = any(
        differences[name] > PRICE_TOLERANCE for name in ("open", "high", "low", "close")
    ) or differences["volume"] > volume_tolerance
    return {
        "bucket_open": iso(h1.timestamp),
        "status": "VALUE_MISMATCH" if mismatch else "ELIGIBLE_MATCH",
        "expected_m15_slots": 4,
        "present_m15_slots": 4,
        "differences": differences,
        "lineage_sha256": timestamp_digest(expected),
    }


def bucket_open(value: datetime, hours: int) -> datetime:
    if hours == 24:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value.replace(hour=(value.hour // hours) * hours, minute=0, second=0, microsecond=0)


def complete_bucket_audit(
    observed: Sequence[Bar], expected_scheduled: Sequence[datetime], hours: int
) -> dict:
    if hours not in (4, 24):
        raise ValueError("Only frozen H4 and D1 bucket sizes are allowed.")
    observed_by_time = {bar.timestamp: bar for bar in observed}
    if len(observed_by_time) != len(observed):
        raise ValueError("Duplicate H1 timestamp in derived audit.")
    unknown = sorted(set(observed_by_time) - set(expected_scheduled))
    if unknown:
        raise ValueError(f"H1 timestamp outside provider schedule: {iso(unknown[0])}")
    grouped: dict[datetime, list[datetime]] = {}
    for value in sorted(expected_scheduled):
        grouped.setdefault(bucket_open(value, hours), []).append(value)
    records: list[dict] = []
    derived: list[Bar] = []
    for start, expected in sorted(grouped.items()):
        present = [observed_by_time[value] for value in expected if value in observed_by_time]
        complete = len(present) == len(expected) and len(expected) > 0
        if complete:
            value = aggregate_bars(present, start)
            derived.append(value)
            status = "CREATED_COMPLETE"
        else:
            status = "DROPPED_SOURCE_MISSING"
        records.append(
            {
                "bucket_open": iso(start),
                "bucket_end_exclusive": iso(start + timedelta(hours=hours)),
                "expected_h1_slots": len(expected),
                "present_h1_slots": len(present),
                "status": status,
                "lineage_count": len(present),
                "lineage_sha256": timestamp_digest(bar.timestamp for bar in present),
            }
        )
    return {
        "timeframe": "H4" if hours == 4 else "D1",
        "records": records,
        "created_count": len(derived),
        "dropped_count": sum(row["status"] != "CREATED_COMPLETE" for row in records),
        "derived": derived,
    }


def cross_market_overlap(group: str, timestamps: dict[str, set[datetime]]) -> dict:
    members = FROZEN_GROUPS.get(group)
    if members is None or set(timestamps) != set(members):
        raise ValueError("Cross-market group members differ from the frozen universe.")
    union = set().union(*(timestamps[member] for member in members))
    intersection = set(timestamps[members[0]])
    for member in members[1:]:
        intersection &= timestamps[member]
    return {
        "group": group,
        "members": list(members),
        "union_count": len(union),
        "intersection_count": len(intersection),
        "per_member_count": {member: len(timestamps[member]) for member in members},
        "missing_member_occurrences": sum(
            1 for value in union for member in members if value not in timestamps[member]
        ),
        "intersection_timestamp_sha256": timestamp_digest(intersection),
    }


def validate_energy_inventory(value: dict) -> dict:
    required = {
        "source",
        "version",
        "sha256",
        "continuous_series_construction",
        "adjustment_method",
        "session_hours",
        "roll_events",
        "exclusion_rule_frozen_before_price_access",
        "price_inferred",
    }
    missing = sorted(required - set(value))
    valid = (
        not missing
        and value.get("price_inferred") is False
        and value.get("exclusion_rule_frozen_before_price_access") is True
        and isinstance(value.get("sha256"), str)
        and len(value.get("sha256", "")) == 64
        and all(character in "0123456789abcdef" for character in value.get("sha256", ""))
    )
    return {
        "candidate": "STRAT-P9-RR-204",
        "status": "METADATA_READY_OTHER_GATES_BLOCKED" if valid else "DATA_INSUFFICIENT",
        "energy_metadata_gate_passed": bool(valid),
        "count_only_allowed": False,
        "missing_fields": missing,
        "price_inferred": value.get("price_inferred"),
    }


def synthetic_report() -> dict:
    start = datetime(2014, 8, 28, 0, 0, tzinfo=UTC)
    expected_m15 = [start + timedelta(minutes=15 * index) for index in range(8)]
    observed_m15 = expected_m15[:3] + expected_m15[4:]
    missing = missing_segments(expected_m15, observed_m15, timedelta(minutes=15))
    bars = [
        Bar(value, 1 + index / 100, 1.02 + index / 100, 0.99 + index / 100, 1.01 + index / 100, 10)
        for index, value in enumerate(expected_m15[:4])
    ]
    h1 = aggregate_bars(bars, start)
    reconciliation = reconcile_m15_h1(bars, h1)
    expected_h1 = [start + timedelta(hours=index) for index in range(4)]
    h1_bars = [Bar(value, 1, 1.1, 0.9, 1.05, 10) for value in expected_h1]
    derived = complete_bucket_audit(h1_bars, expected_h1, 4)
    return {
        "schema_version": "phase9-synthetic-full-qc-report-v1.0",
        "status": "SYNTHETIC_PRIMITIVES_PASS_ACTUAL_DATA_NOT_EVALUATED",
        "synthetic_fixture_only": True,
        "missingness": missing,
        "m15_h1_reconciliation": reconciliation,
        "h4_created_count": derived["created_count"],
        "forward_fill_count": 0,
        "provider_calendar_actual_coverage_verified": False,
        "provider_no_synthetic_bars_verified": False,
        "actual_market_data_full_quality_gate_passed": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def atomic_json(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("QC report target must be new.")
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic-report", type=Path, required=True)
    args = parser.parse_args()
    report = synthetic_report()
    atomic_json(args.synthetic_report, report)
    print(json.dumps({"status": report["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
