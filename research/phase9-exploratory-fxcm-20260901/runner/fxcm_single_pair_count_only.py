#!/usr/bin/env python3
"""Count-only screen for four single-instrument Phase 9 hypotheses on FX8."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median


CONFIRMATION = "RUN_EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
SYMBOLS = ("AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY", "GBPUSD", "USDJPY")
SIGNAL_TIMEFRAMES = ("M15", "H1", "H4")
TIMEFRAME_DELTA = {
    "M15": timedelta(minutes=15), "H1": timedelta(hours=1),
    "H4": timedelta(hours=4), "D1": timedelta(days=1),
}
CANDIDATES = ("STRAT-P9-PS-202", "STRAT-P9-PS-203", "STRAT-P9-PS-205", "STRAT-P9-LV-202")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OUTCOME_KEYS = {
    "return", "returns", "forward_return", "return_sign", "edge", "mfe", "mae",
    "win", "wins", "loss", "losses", "win_rate", "profit_factor", "drawdown",
    "profit", "pnl", "expectancy", "cumulative_r", "p_value", "pvalue",
    "confidence_interval", "equity_curve", "sharpe", "sortino", "outcome", "outcomes",
}
REPORT_KEYS = {
    "schema_version", "status", "track", "run_identity", "contract_sha256",
    "candidate_registry_sha256", "canonical_mtf_report_sha256", "current_mtf_report_sha256",
    "current_mtf_matches_canonical_data_identity", "dataset", "strategy_results",
    "exploratory_fx8_frequency_pass_candidates", "candidate_signal_counts_calculated",
    "exploratory_count_only_executed", "formal_count_only_authorized",
    "formal_phase9_authorization_effect", "return_calculated", "research_outcomes_calculated",
    "outcome_fields", "persistent_price_files_after_cleanup", "result_dependent_rule_change",
    "next_gate",
}


class SinglePairCountError(RuntimeError):
    pass


UTILITY_PATH = Path(__file__).with_name("fxcm_rr_count_only.py")
UTILITY_SPEC = importlib.util.spec_from_file_location("fxcm_count_shared_utility", UTILITY_PATH)
if UTILITY_SPEC is None or UTILITY_SPEC.loader is None:
    raise RuntimeError("cannot load shared Count-only utility")
utility = importlib.util.module_from_spec(UTILITY_SPEC)
sys.modules[UTILITY_SPEC.name] = utility
UTILITY_SPEC.loader.exec_module(utility)
Bar = utility.Bar
Signal = utility.Signal


def sha256_file(path: Path) -> str:
    return utility.sha256_file(path)


def parse_time(value: str) -> datetime:
    return utility.parse_time(value)


def iso(value: datetime) -> str:
    return utility.iso(value)


def load_json(path: Path) -> dict:
    return utility.load_json(path)


def validate_contract(
    contract_path: Path, registry_path: Path, entry_gate_path: Path,
    rr_audit_path: Path, canonical_mtf_path: Path,
) -> dict:
    contract = load_json(contract_path)
    checks = (
        (contract.get("schema_version") == "phase9-exploratory-fxcm-single-pair-count-only-v1.0.0", "schema"),
        (contract.get("status") == "FROZEN_AFTER_RR_COUNT_RESULT_BEFORE_FIRST_SINGLE_PAIR_SIGNAL_COUNT", "status"),
        (contract.get("scope_amendment", {}).get("exploratory_fx8_subset_only") is True, "subset"),
        (contract.get("scope_amendment", {}).get("formal_phase9_promotion_or_rejection_effect") is False, "formal effect"),
        (contract.get("dataset", {}).get("symbols") == list(SYMBOLS), "symbols"),
        (contract.get("dataset", {}).get("cross_instrument_synchronization_required") is False, "synchronization"),
        (tuple(contract.get("candidates", {})) == CANDIDATES, "candidate order"),
        (contract.get("common_rules", {}).get("forward_outcome_access") is False, "outcome access"),
        (contract.get("scientific_state_before_run", {}).get("candidate_signal_counts_calculated") is False, "prior counts"),
        (contract.get("scientific_state_before_run", {}).get("return_calculated") is False, "prior performance"),
        (contract.get("scientific_state_before_run", {}).get("research_outcomes_calculated") is False, "prior outcomes"),
    )
    for passed, label in checks:
        if not passed:
            raise SinglePairCountError(f"frozen single-pair contract mismatch: {label}")
    anchors = contract["anchors"]
    for label, path in (
        ("candidate_registry", registry_path), ("entry_gate", entry_gate_path),
        ("rr_count_run_audit", rr_audit_path), ("canonical_mtf_report", canonical_mtf_path),
        ("shared_count_utility", UTILITY_PATH),
    ):
        if anchors[label]["sha256"] != sha256_file(path):
            raise SinglePairCountError(f"frozen anchor SHA mismatch: {label}")
    return contract


def validate_registry(registry_path: Path) -> None:
    registry = load_json(registry_path)
    selected = [row for row in registry.get("candidates", []) if row.get("strategy_id") in CANDIDATES]
    by_id = {row["strategy_id"]: row for row in selected}
    if set(by_id) != set(CANDIDATES):
        raise SinglePairCountError("registered single-pair candidate set mismatch")
    expected = {
        "STRAT-P9-PS-202": ["M15", "H1", "H4"],
        "STRAT-P9-PS-203": ["M15", "H1", "H4"],
        "STRAT-P9-PS-205": ["H1", "H4"],
        "STRAT-P9-LV-202": ["M15", "H1", "H4"],
    }
    for strategy_id, timeframes in expected.items():
        row = by_id[strategy_id]
        if row.get("targets") != "ALL_UNIVERSE" or row.get("timeframes") != timeframes or row.get("sample_size_gate") != 500:
            raise SinglePairCountError(f"registered scope mismatch: {strategy_id}")


def load_all_series(work_dir: Path) -> dict[tuple[str, str], list[Bar]]:
    output = utility.load_required_series(work_dir)
    derived = work_dir / "derived"
    for symbol in SYMBOLS:
        output[(symbol, "M15")] = utility.load_mid_series(
            derived / f"{symbol}_M15_bid.csv", derived / f"{symbol}_M15_ask.csv"
        )
    return output


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1.0 - alpha) * output[-1])
    return output


def bar_range(bar: Bar) -> float:
    return bar.high - bar.low


def body_ratio(bar: Bar) -> float:
    width = bar_range(bar)
    return abs(bar.close - bar.open) / width if width > 0 else 0.0


def close_location(bar: Bar, direction: str) -> float:
    width = bar_range(bar)
    if width <= 0:
        return 0.0
    return (bar.close - bar.low) / width if direction == "LONG" else (bar.high - bar.close) / width


def atr_before(bars: list[Bar], index: int, period: int = 14) -> float | None:
    if index < period + 1:
        return None
    values = [utility.true_range(bars, position) for position in range(index - period, index)]
    result = sum(values) / period
    return result if result > 0 and math.isfinite(result) else None


def atr_inclusive(bars: list[Bar], index: int, period: int) -> float | None:
    if index < period:
        return None
    values = [utility.true_range(bars, position) for position in range(index - period + 1, index + 1)]
    result = sum(values) / period
    return result if result > 0 and math.isfinite(result) else None


def entry_exists(bars: list[Bar], index: int, timeframe: str) -> bool:
    if index + 1 >= len(bars):
        return False
    duration = TIMEFRAME_DELTA[timeframe]
    confirmation_close = bars[index].timestamp + duration
    return confirmation_close <= bars[index + 1].timestamp <= confirmation_close + 2 * duration


def event_signal(strategy_id: str, symbol: str, timeframe: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(
        strategy_id, symbol, timeframe, direction,
        bars[index].timestamp + TIMEFRAME_DELTA[timeframe], bars[index + 1].timestamp, 0,
    )


def linear_percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise SinglePairCountError("empty percentile input")
    ordered = sorted(values)
    position = percentile / 100.0 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def pullback_count(bars: list[Bar], index: int, direction: str) -> int:
    count = 0
    position = index - 1
    while position > 0:
        against = bars[position].close < bars[position - 1].close if direction == "LONG" else bars[position].close > bars[position - 1].close
        if not against:
            break
        count += 1
        position -= 1
        if count >= 7:
            break
    return count


def pullback_depth(bars: list[Bar], index: int, count: int, direction: str) -> float:
    start_close = bars[index - count - 1].close
    pullback = bars[index - count:index]
    return start_close - min(row.low for row in pullback) if direction == "LONG" else max(row.high for row in pullback) - start_close


def scan_ps202(symbol: str, timeframe: str, bars: list[Bar]) -> list[Signal]:
    signals = []
    for break_index in range(20, len(bars) - 2):
        atr = atr_before(bars, break_index)
        if atr is None:
            continue
        prior = bars[break_index - 20:break_index]
        high_boundary = max(row.high for row in prior)
        low_boundary = min(row.low for row in prior)
        break_bar = bars[break_index]
        break_direction = None
        if break_bar.close >= high_boundary + 0.15 * atr and close_location(break_bar, "LONG") >= 0.75:
            break_direction = "LONG"
        elif break_bar.close <= low_boundary - 0.15 * atr and close_location(break_bar, "SHORT") >= 0.75:
            break_direction = "SHORT"
        if break_direction is None:
            continue
        signal_direction = "SHORT" if break_direction == "LONG" else "LONG"
        for reclaim_index in (break_index + 1, break_index + 2):
            reclaim_atr = atr_before(bars, reclaim_index)
            if reclaim_atr is None:
                continue
            reclaim = bars[reclaim_index]
            inside = (
                reclaim.close <= high_boundary - 0.10 * reclaim_atr
                if break_direction == "LONG" else
                reclaim.close >= low_boundary + 0.10 * reclaim_atr
            )
            if (
                inside and body_ratio(reclaim) >= 0.40
                and close_location(reclaim, signal_direction) >= 0.60
                and entry_exists(bars, reclaim_index, timeframe)
            ):
                signals.append(event_signal("STRAT-P9-PS-202", symbol, timeframe, signal_direction, bars, reclaim_index))
                break
    return signals


def regime_states(bars: list[Bar], timeframe: str) -> tuple[list[datetime], list[str | None]]:
    closes = [bar.close for bar in bars]
    ema20 = ema(closes, 20)
    ema60 = ema(closes, 60)
    availability = [bar.timestamp + TIMEFRAME_DELTA[timeframe] for bar in bars]
    states: list[str | None] = [None] * len(bars)
    for index in range(59, len(bars)):
        atr = atr_before(bars, index)
        if atr is None:
            continue
        slope = ema20[index] - ema20[index - 5]
        if ema20[index] > ema60[index] and slope >= 0.25 * atr:
            states[index] = "LONG"
        elif ema20[index] < ema60[index] and slope <= -0.25 * atr:
            states[index] = "SHORT"
    return availability, states


def latest_state(availability: list[datetime], states: list[str | None], at_time: datetime) -> str | None:
    index = bisect.bisect_right(availability, at_time) - 1
    return states[index] if index >= 0 else None


def scan_ps203(symbol: str, timeframe: str, bars: list[Bar], higher: list[Bar], higher_timeframe: str) -> list[Signal]:
    higher_times, higher_states = regime_states(higher, higher_timeframe)
    closes = [bar.close for bar in bars]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    signals = []
    for index in range(52, len(bars) - 1):
        confirmation_time = bars[index].timestamp + TIMEFRAME_DELTA[timeframe]
        direction = latest_state(higher_times, higher_states, confirmation_time)
        if direction is None:
            continue
        count = pullback_count(bars, index, direction)
        atr = atr_before(bars, index)
        if atr is None or not 2 <= count <= 6:
            continue
        depth = pullback_depth(bars, index, count, direction)
        if not 0.50 <= depth / atr <= 1.75:
            continue
        indices = range(index - count, index)
        if direction == "LONG":
            touched = any(bars[position].low <= ema20[position] for position in indices)
            guarded = all(bars[position].close >= ema50[position] for position in indices)
            confirmed = bars[index].close > max(row.high for row in bars[index - 2:index])
        else:
            touched = any(bars[position].high >= ema20[position] for position in indices)
            guarded = all(bars[position].close <= ema50[position] for position in indices)
            confirmed = bars[index].close < min(row.low for row in bars[index - 2:index])
        if touched and guarded and confirmed and body_ratio(bars[index]) >= 0.50 and entry_exists(bars, index, timeframe):
            signals.append(event_signal("STRAT-P9-PS-203", symbol, timeframe, direction, bars, index))
    return signals


def d1_trend_states(bars: list[Bar]) -> tuple[list[datetime], list[str | None]]:
    availability = [bar.timestamp + timedelta(days=1) for bar in bars]
    states: list[str | None] = [None] * len(bars)
    for index in range(60, len(bars)):
        change20 = bars[index].close - bars[index - 20].close
        change60 = bars[index].close - bars[index - 60].close
        atr20 = atr_inclusive(bars, index, 20)
        if atr20 is None or change20 * change60 <= 0 or abs(change60) / atr20 < 2.50:
            continue
        states[index] = "LONG" if change60 > 0 else "SHORT"
    return availability, states


def scan_ps205(symbol: str, timeframe: str, bars: list[Bar], d1_bars: list[Bar]) -> list[Signal]:
    d1_times, states = d1_trend_states(d1_bars)
    signals = []
    for index in range(16, len(bars) - 1):
        direction = latest_state(d1_times, states, bars[index].timestamp + TIMEFRAME_DELTA[timeframe])
        if direction is None:
            continue
        count = pullback_count(bars, index, direction)
        atr = atr_before(bars, index)
        if atr is None or not 2 <= count <= 6:
            continue
        depth = pullback_depth(bars, index, count, direction)
        if not 0.50 <= depth / atr <= 1.50:
            continue
        confirmed = (
            bars[index].close > max(row.high for row in bars[index - 3:index])
            if direction == "LONG" else
            bars[index].close < min(row.low for row in bars[index - 3:index])
        )
        if confirmed and body_ratio(bars[index]) >= 0.50 and entry_exists(bars, index, timeframe):
            signals.append(event_signal("STRAT-P9-PS-205", symbol, timeframe, direction, bars, index))
    return signals


def scan_lv202(symbol: str, timeframe: str, bars: list[Bar]) -> list[Signal]:
    signals = []
    active_until: datetime | None = None
    true_ranges = [None] + [utility.true_range(bars, index) for index in range(1, len(bars))]
    for break_index in range(253, len(bars) - 3):
        break_open_time = bars[break_index].timestamp
        if active_until is not None and break_open_time < active_until:
            continue
        atr = atr_before(bars, break_index)
        if atr is None:
            continue
        recent = [float(value) for value in true_ranges[break_index - 12:break_index]]
        history = [float(value) for value in true_ranges[break_index - 252:break_index - 12]]
        if median(recent) > linear_percentile(history, 20):
            continue
        prior = bars[break_index - 20:break_index]
        high_boundary = max(row.high for row in prior)
        low_boundary = min(row.low for row in prior)
        break_bar = bars[break_index]
        direction = None
        if (
            break_bar.close >= high_boundary + 0.10 * atr
            and bar_range(break_bar) >= 1.25 * atr and body_ratio(break_bar) >= 0.55
        ):
            direction = "LONG"
            boundary = high_boundary
        elif (
            break_bar.close <= low_boundary - 0.10 * atr
            and bar_range(break_bar) >= 1.25 * atr and body_ratio(break_bar) >= 0.55
        ):
            direction = "SHORT"
            boundary = low_boundary
        if direction is None:
            continue
        setup_end = bars[break_index + 3].timestamp + TIMEFRAME_DELTA[timeframe]
        active_until = setup_end
        touched = False
        for index in range(break_index + 1, break_index + 4):
            current = bars[index]
            if direction == "LONG":
                if current.close < boundary - 0.20 * atr:
                    break
                touched = touched or current.low <= boundary + 0.20 * atr
                confirmed = touched and current.close > boundary and close_location(current, "LONG") >= 0.65
            else:
                if current.close > boundary + 0.20 * atr:
                    break
                touched = touched or current.high >= boundary - 0.20 * atr
                confirmed = touched and current.close < boundary and close_location(current, "SHORT") >= 0.65
            if confirmed and entry_exists(bars, index, timeframe):
                signal = event_signal("STRAT-P9-LV-202", symbol, timeframe, direction, bars, index)
                signals.append(signal)
                active_until = signal.entry_time + timedelta(hours=12)
                break
    return signals


def primary_episodes(signals: list[Signal]) -> list[Signal]:
    priority = {"H4": 0, "H1": 1, "M15": 2}
    selected: dict[tuple[str, object, str], Signal] = {}
    for signal in signals:
        key = (signal.strategy_id, signal.signal_time.date(), signal.direction)
        current = selected.get(key)
        order = (signal.signal_time, priority[signal.timeframe], signal.symbol)
        if current is None or order < (current.signal_time, priority[current.timeframe], current.symbol):
            selected[key] = signal
    return sorted(selected.values(), key=lambda row: (row.signal_time, row.direction, priority[row.timeframe], row.symbol))


def event_hash(signals: list[Signal]) -> str:
    rows = [
        f"{row.strategy_id}\0{row.symbol}\0{row.timeframe}\0{row.direction}\0{iso(row.signal_time)}\0{iso(row.entry_time)}\n"
        for row in sorted(signals, key=lambda item: (item.signal_time, item.strategy_id, item.symbol, item.timeframe, item.direction))
    ]
    return hashlib.sha256("".join(rows).encode("ascii")).hexdigest()


def frequency_result(strategy_id: str, raw: list[Signal], contract: dict) -> dict:
    deduplicated = utility.collapse_overlaps(raw)
    episodes = primary_episodes(deduplicated)
    candidate = contract["candidates"][strategy_id]
    by_instrument = {symbol: 0 for symbol in SYMBOLS}
    by_timeframe = {timeframe: 0 for timeframe in candidate["timeframes"]}
    by_direction = {"LONG": 0, "SHORT": 0}
    by_year = {"2017": 0, "2018": 0}
    for signal in episodes:
        by_instrument[signal.symbol] += 1
        by_timeframe[signal.timeframe] += 1
        by_direction[signal.direction] += 1
        by_year[str(signal.signal_time.year)] += 1
    total = len(episodes)
    gate = contract["exploratory_fx8_frequency_gate"]
    common = gate["common"]
    instrument_pass = sum(value >= 30 for value in by_instrument.values()) >= common["instruments_with_at_least_30_episodes_min"]
    concentration_pass = total > 0 and max(by_instrument.values()) / total <= common["single_instrument_share_max_inclusive"]
    active_dates = len({signal.signal_time.date() for signal in episodes})
    common_pass = total >= common["primary_episodes_min"] and active_dates >= common["active_utc_dates_min"] and instrument_pass and concentration_pass
    shares = {key: value / total if total else 0.0 for key, value in by_timeframe.items()}
    if len(by_timeframe) == 3:
        rule = gate["three_timeframe"]
        timeframe_pass = (
            all(value >= rule["each_timeframe_episodes_min"] for value in by_timeframe.values())
            and all(value >= rule["each_timeframe_share_min_inclusive"] for value in shares.values())
            and max(shares.values(), default=0.0) <= rule["single_timeframe_share_max_inclusive"]
        )
    else:
        rule = gate["two_timeframe"]
        timeframe_pass = (
            all(value >= rule["each_timeframe_episodes_min"] for value in by_timeframe.values())
            and all(value >= rule["each_timeframe_share_min_inclusive"] for value in shares.values())
        )
    passed = common_pass and timeframe_pass
    return {
        "strategy_id": strategy_id,
        "formal_profile": candidate["formal_profile"],
        "raw_signal_count": len(raw),
        "overlap_deduplicated_signal_count": len(deduplicated),
        "primary_episode_count": total,
        "active_utc_date_count": active_dates,
        "counts_by_instrument": by_instrument,
        "counts_by_timeframe": by_timeframe,
        "timeframe_shares": shares,
        "counts_by_direction": by_direction,
        "counts_by_year": by_year,
        "raw_signal_identity_sha256": event_hash(raw),
        "deduplicated_signal_identity_sha256": event_hash(deduplicated),
        "primary_episode_identity_sha256": event_hash(episodes),
        "fx8_instrument_breadth_pass": instrument_pass,
        "fx8_instrument_concentration_pass": concentration_pass,
        "fx8_timeframe_coverage_pass": timeframe_pass,
        "exploratory_fx8_frequency_pass": passed,
        "exploratory_decision": gate["if_pass"] if passed else gate["if_fail"],
        "formal_count_only_gate_passed": False,
        "formal_scope_ineligible_reasons": [
            "FX8_SUBSET_OF_REGISTERED_12_MARKET_UNIVERSE",
            "ONLY_2017_2018_NOT_FULL_FORMAL_DISCOVERY",
            "EXPLORATORY_M15_DERIVED_FROM_M1_NOT_FORMAL_DIRECT_M15",
        ],
        "formal_control_assignment_completed": False,
    }


def reject_outcomes(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in OUTCOME_KEYS:
                raise SinglePairCountError(f"prohibited outcome field: {key}")
            reject_outcomes(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_outcomes(nested)


def validate_report(report: dict) -> None:
    if set(report) != REPORT_KEYS:
        raise SinglePairCountError("single-pair report exact key mismatch")
    for field in (
        "contract_sha256", "candidate_registry_sha256", "canonical_mtf_report_sha256", "current_mtf_report_sha256"
    ):
        if not isinstance(report[field], str) or not HEX64.fullmatch(report[field]):
            raise SinglePairCountError(f"invalid report SHA: {field}")
    if [row["strategy_id"] for row in report["strategy_results"]] != list(CANDIDATES):
        raise SinglePairCountError("strategy result order mismatch")
    for row in report["strategy_results"]:
        if row["raw_signal_count"] < row["overlap_deduplicated_signal_count"] or row["overlap_deduplicated_signal_count"] < row["primary_episode_count"]:
            raise SinglePairCountError("signal count ordering mismatch")
        for field in ("counts_by_instrument", "counts_by_timeframe", "counts_by_direction", "counts_by_year"):
            if sum(row[field].values()) != row["primary_episode_count"]:
                raise SinglePairCountError(f"episode group count mismatch: {field}")
        if row["formal_count_only_gate_passed"] is not False or row["formal_control_assignment_completed"] is not False:
            raise SinglePairCountError("formal Gate/control state mismatch")
    expected_pass = [row["strategy_id"] for row in report["strategy_results"] if row["exploratory_fx8_frequency_pass"]]
    if report["exploratory_fx8_frequency_pass_candidates"] != expected_pass:
        raise SinglePairCountError("passing candidate list mismatch")
    if report["candidate_signal_counts_calculated"] is not True or report["exploratory_count_only_executed"] is not True:
        raise SinglePairCountError("Count-only completion mismatch")
    if report["formal_count_only_authorized"] is not False or report["formal_phase9_authorization_effect"] is not False:
        raise SinglePairCountError("formal state mismatch")
    if report["return_calculated"] is not False or report["research_outcomes_calculated"] is not False or report["outcome_fields"] != []:
        raise SinglePairCountError("outcome state mismatch")
    if report["persistent_price_files_after_cleanup"] != 0 or report["result_dependent_rule_change"] is not False:
        raise SinglePairCountError("cleanup/rule-change state mismatch")
    reject_outcomes(report)


def write_new_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def validate_report_tree(report_dir: Path, include_manifest: bool) -> None:
    expected = {"EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY.json"}
    if include_manifest:
        expected.add("artifact_manifest_sha256.txt")
    actual = set()
    for path in report_dir.rglob("*"):
        if path.is_symlink():
            raise SinglePairCountError("symlink in report")
        if path.is_file():
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise SinglePairCountError("non-regular report file")
            actual.add(path.relative_to(report_dir).as_posix())
    if actual != expected:
        raise SinglePairCountError("single-pair report exact path mismatch")


def seal_manifest(report_dir: Path) -> None:
    payload = report_dir / "EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY.json"
    manifest = report_dir / "artifact_manifest_sha256.txt"
    with manifest.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{sha256_file(payload)}  {payload.name}\n")
    validate_report_tree(report_dir, True)


def run(
    contract_path: Path, registry_path: Path, entry_gate_path: Path, rr_audit_path: Path,
    current_mtf_path: Path, canonical_mtf_path: Path, work_dir: Path, report_dir: Path,
) -> dict:
    contract = validate_contract(contract_path, registry_path, entry_gate_path, rr_audit_path, canonical_mtf_path)
    validate_registry(registry_path)
    utility.validate_mtf_identity(current_mtf_path, canonical_mtf_path)
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("single-pair report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    series = load_all_series(work_dir)
    raw: dict[str, list[Signal]] = {strategy_id: [] for strategy_id in CANDIDATES}
    for symbol in SYMBOLS:
        for timeframe in SIGNAL_TIMEFRAMES:
            bars = series[(symbol, timeframe)]
            raw["STRAT-P9-PS-202"].extend(scan_ps202(symbol, timeframe, bars))
            higher_timeframe = "H4" if timeframe == "M15" else "D1"
            raw["STRAT-P9-PS-203"].extend(scan_ps203(symbol, timeframe, bars, series[(symbol, higher_timeframe)], higher_timeframe))
            raw["STRAT-P9-LV-202"].extend(scan_lv202(symbol, timeframe, bars))
        for timeframe in ("H1", "H4"):
            raw["STRAT-P9-PS-205"].extend(scan_ps205(symbol, timeframe, series[(symbol, timeframe)], series[(symbol, "D1")]))
    results = [frequency_result(strategy_id, raw[strategy_id], contract) for strategy_id in CANDIDATES]
    passing = [row["strategy_id"] for row in results if row["exploratory_fx8_frequency_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-single-pair-count-only-result-v1.0.0",
        "status": "EXPLORATORY_FX8_SINGLE_PAIR_COUNT_ONLY_COMPLETE_FORMAL_SCOPE_INELIGIBLE",
        "track": contract["track"],
        "run_identity": {
            "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"),
            "head_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        },
        "contract_sha256": sha256_file(contract_path),
        "candidate_registry_sha256": sha256_file(registry_path),
        "canonical_mtf_report_sha256": sha256_file(canonical_mtf_path),
        "current_mtf_report_sha256": sha256_file(current_mtf_path),
        "current_mtf_matches_canonical_data_identity": True,
        "dataset": {
            "symbols": list(SYMBOLS),
            "start_inclusive": contract["dataset"]["start_inclusive"],
            "end_exclusive": contract["dataset"]["end_exclusive"],
            "timeframes_available": contract["dataset"]["timeframes"],
            "signal_feature_price": contract["dataset"]["signal_feature_price"],
            "cross_instrument_synchronization_required": False,
            "price_or_event_timestamp_in_artifact": False,
        },
        "strategy_results": results,
        "exploratory_fx8_frequency_pass_candidates": passing,
        "candidate_signal_counts_calculated": True,
        "exploratory_count_only_executed": True,
        "formal_count_only_authorized": False,
        "formal_phase9_authorization_effect": False,
        "return_calculated": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "persistent_price_files_after_cleanup": 0,
        "result_dependent_rule_change": False,
        "next_gate": "SEPARATE_EXPLORATORY_RETURN_GATE_REQUIRED_FOR_LISTED_PASS_CANDIDATES" if passing else "NO_EXPLORATORY_RETURN_GATE",
    }
    validate_report(report)
    write_new_json(report_dir / "EXPLORATORY_FXCM_SINGLE_PAIR_COUNT_ONLY.json", report)
    validate_report_tree(report_dir, False)
    seal_manifest(report_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--candidate-registry", type=Path, required=True)
    parser.add_argument("--entry-gate", type=Path, required=True)
    parser.add_argument("--rr-count-run-audit", type=Path, required=True)
    parser.add_argument("--current-mtf-report", type=Path, required=True)
    parser.add_argument("--canonical-mtf-report", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise SinglePairCountError("exact exploratory single-pair Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise SinglePairCountError("personal non-commercial FXCM EULA confirmation required")
    run(
        args.contract, args.candidate_registry, args.entry_gate, args.rr_count_run_audit,
        args.current_mtf_report, args.canonical_mtf_report, args.work_dir, args.report_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
