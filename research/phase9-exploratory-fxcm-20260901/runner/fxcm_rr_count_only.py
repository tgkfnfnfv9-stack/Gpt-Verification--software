#!/usr/bin/env python3
"""Count-only frequency screen for preregistered RR-201 and RR-202.

This runner consumes only the ephemeral, already-QC'd FXCM working bars.  It
calculates entry-time features, signal flags, deduplicated episodes, coverage,
and control-pool availability.  It never calculates a post-entry price change,
research outcome, or performance statistic.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median


CONFIRMATION = "RUN_EXPLORATORY_FXCM_RR201_RR202_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
UTC = timezone.utc
SYMBOLS = ("AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY", "GBPUSD", "USDJPY")
CURRENCIES = ("AUD", "EUR", "GBP", "JPY", "USD")
TIMEFRAME_DELTA = {"H1": timedelta(hours=1), "H4": timedelta(hours=4), "D1": timedelta(days=1)}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
WORKING_HEADER = ["timestamp_utc", "open", "high", "low", "close"]
OUTCOME_KEYS = {
    "return", "returns", "forward_return", "return_sign", "edge", "mfe", "mae",
    "win", "wins", "loss", "losses", "win_rate", "profit_factor", "drawdown",
    "profit", "pnl", "expectancy", "cumulative_r", "p_value", "pvalue",
    "confidence_interval", "equity_curve", "sharpe", "sortino", "outcome", "outcomes",
}
REPORT_KEYS = {
    "schema_version", "status", "track", "run_identity", "contract_sha256",
    "entry_gate_sha256", "candidate_registry_sha256", "canonical_mtf_report_sha256",
    "current_mtf_report_sha256", "current_mtf_matches_canonical_data_identity",
    "dataset", "strategy_results", "candidate_signal_counts_calculated",
    "exploratory_count_only_executed", "formal_count_only_authorized",
    "formal_phase9_authorization_effect", "return_calculated",
    "research_outcomes_calculated", "outcome_fields", "persistent_price_files_after_cleanup",
    "result_dependent_rule_change", "next_gate",
}


class CountOnlyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Signal:
    strategy_id: str
    symbol: str
    timeframe: str
    direction: str
    signal_time: datetime
    entry_time: datetime
    control_candidate_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_time(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (TypeError, ValueError):
        raise CountOnlyError("invalid working timestamp") from None


def iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def positive_decimal(value: str, field: str) -> Decimal:
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise CountOnlyError(f"invalid working numeric field: {field}") from None
    if not number.is_finite() or number <= 0:
        raise CountOnlyError(f"non-positive working numeric field: {field}")
    return number


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise CountOnlyError(f"cannot load JSON: {path.name}") from None
    if not isinstance(value, dict):
        raise CountOnlyError(f"JSON root must be object: {path.name}")
    return value


def validate_contract(contract_path: Path, entry_gate_path: Path, registry_path: Path, canonical_mtf_path: Path) -> dict:
    contract = load_json(contract_path)
    checks = (
        (contract.get("schema_version") == "phase9-exploratory-fxcm-rr-count-only-v1.0.0", "schema"),
        (contract.get("status") == "FROZEN_AFTER_ROUTE_SELECTION_BEFORE_FIRST_SIGNAL_COUNT", "status"),
        (contract.get("route_decision", {}).get("selected_route") == 1, "route"),
        (contract.get("route_decision", {}).get("formal_phase9_promotion_effect") is False, "formal promotion"),
        (contract.get("dataset", {}).get("symbols") == list(SYMBOLS), "symbols"),
        (contract.get("dataset", {}).get("currencies") == list(CURRENCIES), "currencies"),
        (contract.get("rr201", {}).get("strategy_id") == "STRAT-P9-RR-201", "RR-201"),
        (contract.get("rr202", {}).get("strategy_id") == "STRAT-P9-RR-202", "RR-202"),
        (contract.get("coverage_reporting", {}).get("formal_block_gate_possible") is False, "block gate"),
        (contract.get("scientific_state_before_run", {}).get("candidate_signal_counts_calculated") is False, "prior counts"),
        (contract.get("scientific_state_before_run", {}).get("return_calculated") is False, "prior performance"),
        (contract.get("scientific_state_before_run", {}).get("research_outcomes_calculated") is False, "prior outcomes"),
        (contract.get("scientific_state_before_run", {}).get("outcome_fields") == [], "outcome fields"),
    )
    for passed, label in checks:
        if not passed:
            raise CountOnlyError(f"frozen Count-only contract mismatch: {label}")
    anchors = contract["anchors"]
    for label, path in (
        ("entry_gate", entry_gate_path),
        ("candidate_registry", registry_path),
        ("canonical_mtf_report", canonical_mtf_path),
    ):
        if anchors[label]["sha256"] != sha256_file(path):
            raise CountOnlyError(f"frozen anchor SHA mismatch: {label}")
    return contract


def validate_registry(registry_path: Path, contract: dict) -> None:
    registry = load_json(registry_path)
    selected = {row["strategy_id"]: row for row in registry.get("candidates", []) if row.get("strategy_id") in {"STRAT-P9-RR-201", "STRAT-P9-RR-202"}}
    if set(selected) != {"STRAT-P9-RR-201", "STRAT-P9-RR-202"}:
        raise CountOnlyError("registered RR candidate set mismatch")
    if selected["STRAT-P9-RR-201"].get("targets") != list(SYMBOLS) or selected["STRAT-P9-RR-201"].get("timeframes") != ["H4"]:
        raise CountOnlyError("registered RR-201 scope mismatch")
    if selected["STRAT-P9-RR-202"].get("targets") != list(SYMBOLS) or selected["STRAT-P9-RR-202"].get("timeframes") != ["H1", "H4"]:
        raise CountOnlyError("registered RR-202 scope mismatch")
    if selected["STRAT-P9-RR-201"].get("sample_size_gate") != contract["rr201"]["formal_n_primary_min"]:
        raise CountOnlyError("registered RR-201 sample Gate mismatch")
    if selected["STRAT-P9-RR-202"].get("sample_size_gate") != contract["rr202"]["formal_n_primary_min"]:
        raise CountOnlyError("registered RR-202 sample Gate mismatch")


def validate_mtf_identity(current_path: Path, canonical_path: Path) -> None:
    current = load_json(current_path)
    canonical = load_json(canonical_path)
    for report, label in ((current, "current"), (canonical, "canonical")):
        if report.get("final_series_count") != 64 or report.get("mtf_qc_execution_completed") is not True:
            raise CountOnlyError(f"{label} MTF report is not execution-complete")
        if report.get("h1_source_identity_exact_match") is not True:
            raise CountOnlyError(f"{label} direct H1 identity mismatch")
        if report.get("candidate_signal_counts_calculated") is not False:
            raise CountOnlyError(f"{label} MTF report contains signal counts")
        if report.get("research_outcomes_calculated") is not False or report.get("outcome_fields") != []:
            raise CountOnlyError(f"{label} MTF report contains outcomes")
    left = {key: value for key, value in current.items() if key != "run_identity"}
    right = {key: value for key, value in canonical.items() if key != "run_identity"}
    if left != right:
        raise CountOnlyError("current MTF data identity differs from canonical Run 33508634314")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != WORKING_HEADER:
            raise CountOnlyError("working CSV header mismatch")
        return list(reader)


def load_mid_series(bid_path: Path, ask_path: Path) -> list[Bar]:
    bid_rows = read_rows(bid_path)
    ask_rows = read_rows(ask_path)
    if len(bid_rows) != len(ask_rows) or not bid_rows:
        raise CountOnlyError("BID/ASK working row count mismatch")
    output = []
    previous = None
    for bid, ask in zip(bid_rows, ask_rows):
        if bid["timestamp_utc"] != ask["timestamp_utc"]:
            raise CountOnlyError("BID/ASK working timestamp mismatch")
        timestamp = parse_time(bid["timestamp_utc"])
        if previous is not None and timestamp <= previous:
            raise CountOnlyError("mid timestamps not strictly increasing")
        previous = timestamp
        bid_values = [positive_decimal(bid[field], field) for field in ("open", "high", "low", "close")]
        ask_values = [positive_decimal(ask[field], field) for field in ("open", "high", "low", "close")]
        if ask_values[0] < bid_values[0]:
            raise CountOnlyError("crossed open in Count-only input")
        values = [float((left + right) / Decimal(2)) for left, right in zip(bid_values, ask_values)]
        bar = Bar(timestamp, *values)
        if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
            raise CountOnlyError("invalid mid OHLC geometry")
        output.append(bar)
    return output


def load_required_series(work_dir: Path) -> dict[tuple[str, str], list[Bar]]:
    direct = work_dir / "direct"
    derived = work_dir / "derived"
    if not direct.is_dir() or not derived.is_dir() or work_dir.is_symlink():
        raise CountOnlyError("invalid ephemeral MTF working tree")
    output = {}
    for symbol in SYMBOLS:
        for timeframe in ("H1", "H4", "D1"):
            root = direct if timeframe == "H1" else derived
            output[(symbol, timeframe)] = load_mid_series(
                root / f"{symbol}_{timeframe}_bid.csv",
                root / f"{symbol}_{timeframe}_ask.csv",
            )
    return output


def synchronize(series: dict[tuple[str, str], list[Bar]], timeframe: str) -> tuple[list[datetime], dict[str, list[Bar]], dict]:
    maps = {symbol: {bar.timestamp: bar for bar in series[(symbol, timeframe)]} for symbol in SYMBOLS}
    sets = [set(value) for value in maps.values()]
    shared = sorted(set.intersection(*sets))
    union = set.union(*sets)
    if not shared or not union:
        raise CountOnlyError(f"empty synchronized {timeframe} series")
    synced = {symbol: [maps[symbol][timestamp] for timestamp in shared] for symbol in SYMBOLS}
    return shared, synced, {
        "timeframe": timeframe,
        "union_timestamp_count": len(union),
        "all_eight_shared_timestamp_count": len(shared),
        "all_eight_synchronization_ratio": len(shared) / len(union),
    }


def solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            return None
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [left - factor * right for left, right in zip(augmented[row], augmented[column])]
    return [augmented[index][-1] for index in range(size)]


def currency_strength(pair_changes: dict[str, float]) -> dict[str, float] | None:
    count = len(CURRENCIES)
    normal = [[0.0 for _ in range(count)] for _ in range(count)]
    right = [0.0 for _ in range(count)]
    index = {currency: position for position, currency in enumerate(CURRENCIES)}
    for symbol, change in pair_changes.items():
        row = [0.0] * count
        row[index[symbol[:3]]] = 1.0
        row[index[symbol[3:]]] = -1.0
        for left in range(count):
            right[left] += row[left] * change
            for column in range(count):
                normal[left][column] += row[left] * row[column]
    kkt = [row + [1.0] for row in normal] + [[1.0] * count + [0.0]]
    solution = solve_linear(kkt, right + [0.0])
    if solution is None:
        return None
    scores = {currency: solution[position] for position, currency in enumerate(CURRENCIES)}
    if not all(math.isfinite(value) for value in scores.values()) or abs(sum(scores.values())) > 1e-8:
        return None
    return scores


def pair_gap(scores: dict[str, float], symbol: str) -> float:
    return scores[symbol[:3]] - scores[symbol[3:]]


def true_range(bars: list[Bar], index: int) -> float:
    previous_close = bars[index - 1].close
    current = bars[index]
    return max(current.high - current.low, abs(current.high - previous_close), abs(current.low - previous_close))


def atr14_before(bars: list[Bar], index: int) -> float | None:
    if index < 15:
        return None
    values = [true_range(bars, position) for position in range(index - 14, index)]
    value = sum(values) / 14
    return value if math.isfinite(value) and value > 0 else None


def h4_trigger(bars: list[Bar], index: int, direction: str) -> bool:
    atr = atr14_before(bars, index)
    if atr is None or index < 8:
        return False
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
    if not 2 <= count <= 6:
        return False
    pullback_start = index - count - 1
    pullback = bars[index - count:index]
    if pullback_start < 0:
        return False
    if direction == "LONG":
        depth = bars[pullback_start].close - min(bar.low for bar in pullback)
        confirmation = bars[index].close > max(bar.high for bar in bars[index - 3:index])
    else:
        depth = max(bar.high for bar in pullback) - bars[pullback_start].close
        confirmation = bars[index].close < min(bar.low for bar in bars[index - 3:index])
    return 0.5 <= depth / atr <= 1.5 and confirmation


def entry_exists(timestamps: list[datetime], index: int, timeframe: str) -> bool:
    if index + 1 >= len(timestamps):
        return False
    duration = TIMEFRAME_DELTA[timeframe]
    confirmation_close = timestamps[index] + duration
    return confirmation_close <= timestamps[index + 1] <= confirmation_close + 2 * duration


def rr201_signals(series: dict[tuple[str, str], list[Bar]], contract: dict) -> tuple[list[Signal], list[dict]]:
    d1_times, d1, d1_sync = synchronize(series, "D1")
    h4_times, h4, h4_sync = synchronize(series, "H4")
    rank_history: list[set[str] | None] = [None] * len(d1_times)
    states: list[dict | None] = [None] * len(d1_times)
    for index in range(60, len(d1_times)):
        changes = {}
        scores = {}
        for window in (20, 60):
            changes[window] = {
                symbol: math.log(d1[symbol][index].close / d1[symbol][index - window].close)
                for symbol in SYMBOLS
            }
            scores[window] = currency_strength(changes[window])
        if scores[20] is None or scores[60] is None:
            continue
        gap20 = {symbol: pair_gap(scores[20], symbol) for symbol in SYMBOLS}
        gap60 = {symbol: pair_gap(scores[60], symbol) for symbol in SYMBOLS}
        ranked = sorted(SYMBOLS, key=lambda symbol: (-abs(gap60[symbol]), symbol))
        top = set(ranked[:2])
        rank_history[index] = top
        if index < 65 or any(rank_history[position] is None for position in range(index - 5, index)):
            continue
        eligible = {}
        for symbol in SYMBOLS:
            same_sign = gap20[symbol] * gap60[symbol] > 0
            stable = sum(symbol in rank_history[position] for position in range(index - 5, index)) >= 3
            if symbol in top and same_sign and stable:
                eligible[symbol] = "LONG" if gap60[symbol] > 0 else "SHORT"
        states[index] = {
            "available": d1_times[index] + timedelta(days=1),
            "eligible": eligible,
            "gap20": gap20,
            "gap60": gap60,
            "ranked": ranked,
        }
    available_states = [state for state in states if state is not None]
    available_times = [state["available"] for state in available_states]
    signals = []
    for index, timestamp in enumerate(h4_times):
        confirmation_time = timestamp + timedelta(hours=4)
        state_index = bisect.bisect_right(available_times, confirmation_time) - 1
        if state_index < 0 or not entry_exists(h4_times, index, "H4"):
            continue
        state = available_states[state_index]
        qualifiers = []
        for symbol, direction in state["eligible"].items():
            if h4_trigger(h4[symbol], index, direction):
                qualifiers.append(symbol)
        if not qualifiers:
            continue
        chosen = sorted(qualifiers, key=lambda symbol: (-abs(state["gap60"][symbol]), symbol))[0]
        direction = state["eligible"][chosen]
        control_candidates = 0
        for symbol in state["ranked"][2:6]:
            if state["gap20"][symbol] * state["gap60"][symbol] <= 0:
                continue
            control_direction = "LONG" if state["gap60"][symbol] > 0 else "SHORT"
            if control_direction == direction and h4_trigger(h4[symbol], index, direction):
                control_candidates += 1
        signals.append(Signal("STRAT-P9-RR-201", chosen, "H4", direction, confirmation_time, h4_times[index + 1], control_candidates))
    return signals, [d1_sync, h4_sync]


def population_z(current: float, history: list[float]) -> float | None:
    if not history or not all(math.isfinite(value) for value in history) or not math.isfinite(current):
        return None
    mean = sum(history) / len(history)
    variance = sum((value - mean) ** 2 for value in history) / len(history)
    if variance <= 0 or not math.isfinite(variance):
        return None
    return (current - mean) / math.sqrt(variance)


def rr202_timeframe_signals(series: dict[tuple[str, str], list[Bar]], timeframe: str) -> tuple[list[Signal], dict]:
    timestamps, bars, sync = synchronize(series, timeframe)
    size = len(timestamps)
    changes: dict[str, list[float | None]] = {symbol: [None] * size for symbol in SYMBOLS}
    residuals: dict[str, list[float | None]] = {symbol: [None] * size for symbol in SYMBOLS}
    residual_z: dict[str, list[float | None]] = {symbol: [None] * size for symbol in SYMBOLS}
    peer_median_z: dict[str, list[float | None]] = {symbol: [None] * size for symbol in SYMBOLS}
    for index in range(12, size):
        current_changes = {
            symbol: math.log(bars[symbol][index].close / bars[symbol][index - 12].close)
            for symbol in SYMBOLS
        }
        for symbol, value in current_changes.items():
            changes[symbol][index] = value
        for target in SYMBOLS:
            fitted = currency_strength({symbol: value for symbol, value in current_changes.items() if symbol != target})
            if fitted is not None:
                residuals[target][index] = current_changes[target] - pair_gap(fitted, target)
    for index in range(252, size):
        for target in SYMBOLS:
            residual = residuals[target][index]
            residual_history = residuals[target][index - 240:index]
            if residual is None or any(value is None for value in residual_history):
                continue
            residual_z[target][index] = population_z(residual, [float(value) for value in residual_history])
            peer_values = []
            for peer in SYMBOLS:
                if peer == target:
                    continue
                current = changes[peer][index]
                history = changes[peer][index - 240:index]
                if current is None or any(value is None for value in history):
                    peer_values = []
                    break
                value = population_z(current, [float(item) for item in history])
                if value is None:
                    peer_values = []
                    break
                peer_values.append(abs(value))
            if len(peer_values) == 7:
                peer_median_z[target][index] = median(peer_values)
    duration = TIMEFRAME_DELTA[timeframe]
    control_times: dict[tuple[str, str, int, int], list[datetime]] = {}
    for target in SYMBOLS:
        for index, value in enumerate(residual_z[target]):
            if value is None or not 1.0 <= abs(value) <= 1.5:
                continue
            direction = "LONG" if value < 0 else "SHORT"
            signal_time = timestamps[index] + duration
            key = (target, direction, signal_time.year, signal_time.hour // 4)
            control_times.setdefault(key, []).append(signal_time)
    signals = []
    for index in range(252, size - 1):
        for target in SYMBOLS:
            event_z = residual_z[target][index]
            peer_value = peer_median_z[target][index]
            if event_z is None or peer_value is None or abs(event_z) < 2.0 or peer_value > 1.0:
                continue
            direction = "LONG" if event_z < 0 else "SHORT"
            confirmed_index = None
            for candidate in (index + 1, index + 2):
                if candidate >= size:
                    break
                candidate_z = residual_z[target][candidate]
                if candidate_z is None or abs(event_z) - abs(candidate_z) < 0.25:
                    continue
                bar = bars[target][candidate]
                price_confirms = bar.close > bar.open if direction == "LONG" else bar.close < bar.open
                if price_confirms:
                    confirmed_index = candidate
                    break
            if confirmed_index is None or not entry_exists(timestamps, confirmed_index, timeframe):
                continue
            signal_time = timestamps[confirmed_index] + duration
            key = (target, direction, signal_time.year, signal_time.hour // 4)
            pool = control_times.get(key, [])
            low = bisect.bisect_left(pool, signal_time - timedelta(days=90))
            high = bisect.bisect_right(pool, signal_time - timedelta(hours=12))
            signals.append(Signal(
                "STRAT-P9-RR-202", target, timeframe, direction,
                signal_time, timestamps[confirmed_index + 1], max(0, high - low),
            ))
    return signals, sync


def collapse_overlaps(signals: list[Signal]) -> list[Signal]:
    output = []
    last_entry: dict[tuple[str, str, str], datetime] = {}
    for signal in sorted(signals, key=lambda row: (row.entry_time, row.strategy_id, row.symbol, row.direction, row.timeframe)):
        key = (signal.strategy_id, signal.symbol, signal.direction)
        previous = last_entry.get(key)
        if previous is not None and signal.entry_time < previous + timedelta(hours=12):
            continue
        output.append(signal)
        last_entry[key] = signal.entry_time
    return output


def primary_episodes(signals: list[Signal]) -> list[Signal]:
    selected: dict[tuple[str, object, str], Signal] = {}
    priority = {"H4": 0, "H1": 1}
    for signal in signals:
        key = (signal.strategy_id, signal.signal_time.date(), signal.direction)
        current = selected.get(key)
        order = (signal.signal_time, priority[signal.timeframe], signal.symbol)
        if current is None or order < (current.signal_time, priority[current.timeframe], current.symbol):
            selected[key] = signal
    return sorted(selected.values(), key=lambda row: (row.signal_time, row.direction, row.timeframe, row.symbol))


def event_hash(signals: list[Signal]) -> str:
    rows = [
        f"{row.strategy_id}\0{row.symbol}\0{row.timeframe}\0{row.direction}\0{iso(row.signal_time)}\0{iso(row.entry_time)}\n"
        for row in sorted(signals, key=lambda item: (item.signal_time, item.strategy_id, item.symbol, item.timeframe, item.direction))
    ]
    return hashlib.sha256("".join(rows).encode("ascii")).hexdigest()


def formal_block(value: datetime, blocks: list[dict]) -> str | None:
    for block in blocks:
        if parse_time(block["start_inclusive"]) <= value < parse_time(block["end_exclusive"]):
            return block["id"]
    return None


def strategy_result(strategy_id: str, raw: list[Signal], synchronization: list[dict], contract: dict) -> dict:
    deduplicated = collapse_overlaps(raw)
    episodes = primary_episodes(deduplicated)
    section = contract["rr201"] if strategy_id.endswith("201") else contract["rr202"]
    blocks = contract["coverage_reporting"]["formal_discovery_blocks"]
    by_instrument = {symbol: 0 for symbol in SYMBOLS}
    by_timeframe = {timeframe: 0 for timeframe in section.get("timeframes", [section.get("timeframe")]) if timeframe}
    by_direction = {"LONG": 0, "SHORT": 0}
    by_block = {block["id"]: 0 for block in blocks}
    for episode in episodes:
        by_instrument[episode.symbol] += 1
        by_timeframe[episode.timeframe] += 1
        by_direction[episode.direction] += 1
        block = formal_block(episode.signal_time, blocks)
        if block is not None:
            by_block[block] += 1
    active_dates = len({episode.signal_time.date() for episode in episodes})
    sync_min = min(row["all_eight_synchronization_ratio"] for row in synchronization)
    feasible = (
        len(episodes) >= section["formal_n_primary_min"]
        and active_dates >= section["formal_active_utc_dates_min"]
        and sync_min >= 0.95
    )
    control_minimum = 1 if strategy_id.endswith("201") else section["control_availability_diagnostic"]["minimum_candidates"]
    return {
        "strategy_id": strategy_id,
        "formal_profile": section["formal_profile"],
        "raw_signal_count": len(raw),
        "overlap_deduplicated_signal_count": len(deduplicated),
        "primary_episode_count": len(episodes),
        "active_utc_date_count": active_dates,
        "counts_by_instrument": by_instrument,
        "counts_by_timeframe": by_timeframe,
        "counts_by_direction": by_direction,
        "counts_by_formal_12_month_block": by_block,
        "raw_signal_identity_sha256": event_hash(raw),
        "deduplicated_signal_identity_sha256": event_hash(deduplicated),
        "primary_episode_identity_sha256": event_hash(episodes),
        "control_diagnostic": {
            "minimum_candidate_pool": control_minimum,
            "raw_signals_with_minimum_pool": sum(row.control_candidate_count >= control_minimum for row in raw),
            "raw_signals_without_minimum_pool": sum(row.control_candidate_count < control_minimum for row in raw),
            "formal_control_assignment_completed": False,
        },
        "synchronization": synchronization,
        "minimum_all_eight_synchronization_ratio": sync_min,
        "exploratory_frequency_feasible": feasible,
        "exploratory_decision": (
            contract["exploratory_decision_rule"]["if_feasible"]
            if feasible else contract["exploratory_decision_rule"]["if_not_feasible"]
        ),
        "formal_count_only_gate_passed": False,
        "formal_scope_ineligible_reasons": [
            "ONLY_2017_2018_OBSERVED_MAXIMUM_THREE_OF_FIVE_FORMAL_BLOCKS_TOUCHED",
            "FORMAL_WARMUP_AND_FULL_DISCOVERY_INTERVAL_NOT_PRESENT",
            "EXPLORATORY_PROVIDER_SCHEDULE_VERSION_UNPROVEN",
        ],
    }


def reject_outcome_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in OUTCOME_KEYS:
                raise CountOnlyError(f"prohibited outcome field: {key}")
            reject_outcome_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_outcome_fields(nested)


def validate_report(report: dict) -> None:
    if set(report) != REPORT_KEYS:
        raise CountOnlyError("Count-only report exact key mismatch")
    for field in (
        "contract_sha256", "entry_gate_sha256", "candidate_registry_sha256",
        "canonical_mtf_report_sha256", "current_mtf_report_sha256",
    ):
        if not isinstance(report[field], str) or not HEX64.fullmatch(report[field]):
            raise CountOnlyError(f"invalid report SHA: {field}")
    if report["candidate_signal_counts_calculated"] is not True or report["exploratory_count_only_executed"] is not True:
        raise CountOnlyError("Count-only completion flags mismatch")
    if report["formal_count_only_authorized"] is not False or report["formal_phase9_authorization_effect"] is not False:
        raise CountOnlyError("formal authorization must remain false")
    if report["return_calculated"] is not False or report["research_outcomes_calculated"] is not False or report["outcome_fields"] != []:
        raise CountOnlyError("outcome state mismatch")
    if report["persistent_price_files_after_cleanup"] != 0 or report["result_dependent_rule_change"] is not False:
        raise CountOnlyError("cleanup/rule-change state mismatch")
    if [row["strategy_id"] for row in report["strategy_results"]] != ["STRAT-P9-RR-201", "STRAT-P9-RR-202"]:
        raise CountOnlyError("strategy result set/order mismatch")
    for result in report["strategy_results"]:
        if result["formal_count_only_gate_passed"] is not False:
            raise CountOnlyError("formal Count-only pass is prohibited on exploratory data")
        if sum(result["counts_by_instrument"].values()) != result["primary_episode_count"]:
            raise CountOnlyError("instrument episode count mismatch")
        if sum(result["counts_by_timeframe"].values()) != result["primary_episode_count"]:
            raise CountOnlyError("timeframe episode count mismatch")
        if sum(result["counts_by_direction"].values()) != result["primary_episode_count"]:
            raise CountOnlyError("direction episode count mismatch")
    reject_outcome_fields(report)


def write_new_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def validate_report_tree(report_dir: Path, include_manifest: bool) -> None:
    expected = {"EXPLORATORY_FXCM_RR_COUNT_ONLY.json"}
    if include_manifest:
        expected.add("artifact_manifest_sha256.txt")
    actual = set()
    for path in report_dir.rglob("*"):
        if path.is_symlink():
            raise CountOnlyError("symlink in Count-only report")
        if path.is_file():
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise CountOnlyError("non-regular Count-only report file")
            actual.add(path.relative_to(report_dir).as_posix())
    if actual != expected:
        raise CountOnlyError("Count-only report exact path mismatch")


def seal_manifest(report_dir: Path) -> None:
    payload = report_dir / "EXPLORATORY_FXCM_RR_COUNT_ONLY.json"
    manifest = report_dir / "artifact_manifest_sha256.txt"
    with manifest.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{sha256_file(payload)}  {payload.name}\n")
    validate_report_tree(report_dir, True)


def run(
    contract_path: Path, entry_gate_path: Path, registry_path: Path,
    current_mtf_path: Path, canonical_mtf_path: Path, work_dir: Path, report_dir: Path,
) -> dict:
    contract = validate_contract(contract_path, entry_gate_path, registry_path, canonical_mtf_path)
    validate_registry(registry_path, contract)
    validate_mtf_identity(current_mtf_path, canonical_mtf_path)
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("Count-only report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    series = load_required_series(work_dir)
    rr201_raw, rr201_sync = rr201_signals(series, contract)
    rr202_h1_raw, rr202_h1_sync = rr202_timeframe_signals(series, "H1")
    rr202_h4_raw, rr202_h4_sync = rr202_timeframe_signals(series, "H4")
    results = [
        strategy_result("STRAT-P9-RR-201", rr201_raw, rr201_sync, contract),
        strategy_result("STRAT-P9-RR-202", rr202_h1_raw + rr202_h4_raw, [rr202_h1_sync, rr202_h4_sync], contract),
    ]
    report = {
        "schema_version": "phase9-exploratory-fxcm-rr-count-only-result-v1.0.0",
        "status": "EXPLORATORY_COUNT_ONLY_COMPLETE_FORMAL_SCOPE_INELIGIBLE",
        "track": contract["track"],
        "run_identity": {
            "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"),
            "head_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        },
        "contract_sha256": sha256_file(contract_path),
        "entry_gate_sha256": sha256_file(entry_gate_path),
        "candidate_registry_sha256": sha256_file(registry_path),
        "canonical_mtf_report_sha256": sha256_file(canonical_mtf_path),
        "current_mtf_report_sha256": sha256_file(current_mtf_path),
        "current_mtf_matches_canonical_data_identity": True,
        "dataset": {
            "symbols": list(SYMBOLS),
            "start_inclusive": contract["dataset"]["start_inclusive"],
            "end_exclusive": contract["dataset"]["end_exclusive"],
            "timeframes_used": ["H1", "H4", "D1"],
            "signal_feature_price": contract["dataset"]["signal_feature_price"],
            "price_or_event_timestamp_in_artifact": False,
        },
        "strategy_results": results,
        "candidate_signal_counts_calculated": True,
        "exploratory_count_only_executed": True,
        "formal_count_only_authorized": False,
        "formal_phase9_authorization_effect": False,
        "return_calculated": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "persistent_price_files_after_cleanup": 0,
        "result_dependent_rule_change": False,
        "next_gate": "STOP_IF_BOTH_EXPLORATORY_FREQUENCY_FLAGS_FALSE_OTHERWISE_FORMAL_SCOPE_DATA_REQUIRED_BEFORE_ANY_OUTCOME",
    }
    validate_report(report)
    write_new_json(report_dir / "EXPLORATORY_FXCM_RR_COUNT_ONLY.json", report)
    validate_report_tree(report_dir, False)
    seal_manifest(report_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--entry-gate", type=Path, required=True)
    parser.add_argument("--candidate-registry", type=Path, required=True)
    parser.add_argument("--current-mtf-report", type=Path, required=True)
    parser.add_argument("--canonical-mtf-report", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise CountOnlyError("exact exploratory Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise CountOnlyError("personal non-commercial FXCM EULA confirmation required")
    run(
        args.contract, args.entry_gate, args.candidate_registry,
        args.current_mtf_report, args.canonical_mtf_report, args.work_dir, args.report_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
