#!/usr/bin/env python3
"""Count-only screen for four blind price-only FX8 MTF hypotheses."""

from __future__ import annotations

import argparse
import bisect
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
CANDIDATES = ("EXP-P9-MTF-301", "EXP-P9-MTF-302", "EXP-P9-MTF-303", "EXP-P9-MTF-304")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_COUNT_ONLY.json"
ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = Path(__file__).with_name("fxcm_single_pair_count_only.py")
MTF_RUNNER = Path(__file__).with_name("fxcm_multitimeframe_qc.py")
ENTRY_GATE = ROOT / "spec/fxcm_count_only_entry_gate.frozen.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = load_module("fxcm_blind_mtf_base", BASE_PATH)
Bar = base.Bar
Signal = base.Signal
SYMBOLS = base.SYMBOLS


class BlindCountError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def load_contract(path: Path) -> dict:
    value = base.load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-candidates-v1.0.0":
        raise BlindCountError("blind candidate schema mismatch")
    if value.get("status") != "FROZEN_BEFORE_FIRST_SIGNAL_COUNT_NO_OUTCOME_EVER_VIEWED":
        raise BlindCountError("blind candidate status mismatch")
    if tuple(value.get("candidates", {})) != CANDIDATES:
        raise BlindCountError("blind candidate order mismatch")
    if value["dataset"]["symbols"] != list(SYMBOLS):
        raise BlindCountError("FX8 symbol scope mismatch")
    if value["common_rules"]["forward_outcome_access"] is not False:
        raise BlindCountError("outcome access enabled")
    if value["candidates"]["EXP-P9-MTF-301"].get("break_selection") != "EARLIEST_DIRECTIONALLY_ELIGIBLE_BREAK_PER_UTC_DATE_ONLY":
        raise BlindCountError("EXP-P9-MTF-301 break selection mismatch")
    anchors = value["anchors"]
    for key, actual in (
        ("base_count_utility_sha256", BASE_PATH),
        ("mtf_qc_runner_sha256", MTF_RUNNER),
        ("count_entry_gate_sha256", ENTRY_GATE),
        ("canonical_mtf_report_sha256", CANONICAL_MTF),
    ):
        if anchors[key] != sha256_file(actual):
            raise BlindCountError(f"anchor SHA mismatch: {key}")
    return value


def signal(strategy_id: str, symbol: str, timeframe: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(
        strategy_id, symbol, timeframe, direction,
        bars[index].timestamp + base.TIMEFRAME_DELTA[timeframe],
        bars[index + 1].timestamp, 0,
    )


def states_h4_bias(bars: list[Bar], slope_atr_min: float) -> tuple[list[datetime], list[str | None]]:
    values = base.ema([row.close for row in bars], 20)
    times = [row.timestamp + timedelta(hours=4) for row in bars]
    states: list[str | None] = [None] * len(bars)
    for index in range(20, len(bars)):
        atr = base.atr_before(bars, index)
        if atr is None:
            continue
        slope = values[index] - values[index - 5]
        if slope >= slope_atr_min * atr:
            states[index] = "LONG"
        elif slope <= -slope_atr_min * atr:
            states[index] = "SHORT"
    return times, states


def latest(times: list[datetime], states: list[str | None], when: datetime) -> str | None:
    index = bisect.bisect_right(times, when) - 1
    return states[index] if index >= 0 else None


def scan_301(symbol: str, m15: list[Bar], h4: list[Bar], rules: dict) -> list[Signal]:
    h4_times, h4_states = states_h4_bias(h4, rules["h4_slope_atr_min"])
    by_day: dict[object, list[int]] = defaultdict(list)
    for index, row in enumerate(m15):
        by_day[row.timestamp.date()].append(index)
    output = []
    for indices in by_day.values():
        range_indices = [i for i in indices if m15[i].timestamp.hour in rules["range_slots_utc"]]
        if len(range_indices) != 24:
            continue
        range_high = max(m15[i].high for i in range_indices)
        range_low = min(m15[i].low for i in range_indices)
        for break_index in indices:
            hour = m15[break_index].timestamp.hour
            if not rules["break_window_utc_start_inclusive"] <= hour < rules["break_window_utc_end_exclusive"]:
                continue
            atr = base.atr_before(m15, break_index)
            if atr is None or base.body_ratio(m15[break_index]) < rules["break_body_ratio_min"]:
                continue
            direction = latest(
                h4_times, h4_states,
                m15[break_index].timestamp + timedelta(minutes=15),
            )
            if direction == "LONG" and m15[break_index].close >= range_high + rules["break_distance_atr_min"] * atr:
                boundary = range_high
            elif direction == "SHORT" and m15[break_index].close <= range_low - rules["break_distance_atr_min"] * atr:
                boundary = range_low
            else:
                continue
            for index in range(break_index + 1, min(break_index + 1 + rules["retest_bars_max"], len(m15) - 1)):
                if m15[index].timestamp.date() != m15[break_index].timestamp.date():
                    break
                row = m15[index]
                if direction == "LONG":
                    touched = row.low <= boundary + rules["retest_boundary_distance_atr_max"] * atr
                    confirmed = row.close > boundary and base.close_location(row, "LONG") >= rules["retest_close_location_min"]
                else:
                    touched = row.high >= boundary - rules["retest_boundary_distance_atr_max"] * atr
                    confirmed = row.close < boundary and base.close_location(row, "SHORT") >= rules["retest_close_location_min"]
                if touched and confirmed and base.entry_exists(m15, index, "M15"):
                    output.append(signal("EXP-P9-MTF-301", symbol, "M15", direction, m15, index))
                    break
            break
    return output


def scan_302(symbol: str, h4: list[Bar], h1: list[Bar], rules: dict) -> list[Signal]:
    h1_times = [row.timestamp for row in h1]
    output = []
    for event_index in range(rules["boundary_lookback"], len(h4)):
        atr = base.atr_before(h4, event_index)
        if atr is None:
            continue
        prior = h4[event_index - rules["boundary_lookback"]:event_index]
        high_boundary = max(row.high for row in prior)
        low_boundary = min(row.low for row in prior)
        row = h4[event_index]
        width = base.bar_range(row)
        if width <= 0:
            continue
        upper_wick = (row.high - max(row.open, row.close)) / width
        lower_wick = (min(row.open, row.close) - row.low) / width
        if row.high >= high_boundary + rules["sweep_distance_atr_min"] * atr and row.close <= high_boundary and upper_wick >= rules["terminal_wick_ratio_min"]:
            direction = "SHORT"
        elif row.low <= low_boundary - rules["sweep_distance_atr_min"] * atr and row.close >= low_boundary and lower_wick >= rules["terminal_wick_ratio_min"]:
            direction = "LONG"
        else:
            continue
        start = row.timestamp + timedelta(hours=4)
        first = bisect.bisect_left(h1_times, start)
        midpoint = (row.high + row.low) / 2.0
        for index in range(first, min(first + rules["h1_confirmation_bars_max"], len(h1) - 1)):
            confirm = h1[index]
            no_new = (
                confirm.high <= row.high + rules["new_extreme_atr_max"] * atr
                if direction == "SHORT" else
                confirm.low >= row.low - rules["new_extreme_atr_max"] * atr
            )
            crossed = confirm.close < midpoint if direction == "SHORT" else confirm.close > midpoint
            if no_new and crossed and base.body_ratio(confirm) >= rules["confirmation_body_ratio_min"] and base.entry_exists(h1, index, "H1"):
                output.append(signal("EXP-P9-MTF-302", symbol, "H1", direction, h1, index))
                break
    return output


def scan_303(symbol: str, d1: list[Bar], h4: list[Bar], rules: dict) -> list[Signal]:
    h4_times = [row.timestamp for row in h4]
    output = []
    for event_index in range(15, len(d1)):
        atr = base.atr_before(d1, event_index)
        current, previous = d1[event_index], d1[event_index - 1]
        if atr is None or current.high > previous.high or current.low < previous.low:
            continue
        if base.bar_range(current) > rules["inside_range_atr_max"] * atr:
            continue
        start = current.timestamp + timedelta(days=1)
        first = bisect.bisect_left(h4_times, start)
        for index in range(first, min(first + rules["h4_bars_after_d1_max"], len(h4) - 1)):
            h4_atr = base.atr_before(h4, index)
            row = h4[index]
            if h4_atr is None or base.bar_range(row) < rules["break_range_h4_atr_min"] * h4_atr or base.body_ratio(row) < rules["break_body_ratio_min"]:
                continue
            if row.close >= current.high + rules["break_distance_h4_atr_min"] * h4_atr:
                direction = "LONG"
            elif row.close <= current.low - rules["break_distance_h4_atr_min"] * h4_atr:
                direction = "SHORT"
            else:
                continue
            if base.entry_exists(h4, index, "H4"):
                output.append(signal("EXP-P9-MTF-303", symbol, "H4", direction, h4, index))
                break
    return output


def d1_direction(bars: list[Bar], rules: dict) -> tuple[list[datetime], list[str | None]]:
    times = [row.timestamp + timedelta(days=1) for row in bars]
    states: list[str | None] = [None] * len(bars)
    lookback = rules["d1_change_bars"]
    for index in range(lookback + 1, len(bars)):
        atr = base.atr_before(bars, index)
        if atr is None:
            continue
        change = bars[index].close - bars[index - lookback].close
        if change >= rules["d1_change_atr_min"] * atr:
            states[index] = "LONG"
        elif change <= -rules["d1_change_atr_min"] * atr:
            states[index] = "SHORT"
    return times, states


def h4_direction(bars: list[Bar], rules: dict) -> tuple[list[datetime], list[str | None]]:
    ema20 = base.ema([row.close for row in bars], rules["h4_ema_periods"][0])
    ema50 = base.ema([row.close for row in bars], rules["h4_ema_periods"][1])
    times = [row.timestamp + timedelta(hours=4) for row in bars]
    states: list[str | None] = [None] * len(bars)
    for index in range(rules["h4_ema_periods"][1] - 1, len(bars)):
        if ema20[index] > ema50[index]:
            states[index] = "LONG"
        elif ema20[index] < ema50[index]:
            states[index] = "SHORT"
    return times, states


def scan_304(symbol: str, h1: list[Bar], h4: list[Bar], d1: list[Bar], rules: dict) -> list[Signal]:
    d1_times, d1_states = d1_direction(d1, rules)
    h4_times, h4_states = h4_direction(h4, rules)
    output = []
    lookback = rules["h1_boundary_lookback"]
    for index in range(max(15, lookback), len(h1) - 1):
        when = h1[index].timestamp + timedelta(hours=1)
        d1_state = latest(d1_times, d1_states, when)
        h4_state = latest(h4_times, h4_states, when)
        if d1_state is None or d1_state != h4_state:
            continue
        atr = base.atr_before(h1, index)
        row = h1[index]
        if atr is None or not rules["h1_range_atr_min"] <= base.bar_range(row) / atr <= rules["h1_range_atr_max"]:
            continue
        if base.body_ratio(row) < rules["h1_body_ratio_min"]:
            continue
        prior = h1[index - lookback:index]
        if d1_state == "LONG" and row.close >= max(x.high for x in prior) + rules["h1_break_distance_atr_min"] * atr:
            direction = "LONG"
        elif d1_state == "SHORT" and row.close <= min(x.low for x in prior) - rules["h1_break_distance_atr_min"] * atr:
            direction = "SHORT"
        else:
            continue
        if base.entry_exists(h1, index, "H1"):
            output.append(signal("EXP-P9-MTF-304", symbol, "H1", direction, h1, index))
    return output


def event_hash(rows: list[Signal]) -> str:
    values = [
        f"{x.strategy_id}\0{x.symbol}\0{x.timeframe}\0{x.direction}\0{base.iso(x.signal_time)}\0{base.iso(x.entry_time)}\n"
        for x in sorted(rows, key=lambda x: (x.signal_time, x.strategy_id, x.symbol, x.direction))
    ]
    return hashlib.sha256("".join(values).encode("ascii")).hexdigest()


def frequency_result(strategy_id: str, raw: list[Signal], contract: dict) -> dict:
    dedup = base.utility.collapse_overlaps(raw)
    episodes = base.primary_episodes(dedup)
    by_instrument = {symbol: 0 for symbol in SYMBOLS}
    by_direction = {"LONG": 0, "SHORT": 0}
    by_year = {"2017": 0, "2018": 0}
    for row in episodes:
        by_instrument[row.symbol] += 1
        by_direction[row.direction] += 1
        by_year[str(row.signal_time.year)] += 1
    total = len(episodes)
    active_dates = len({row.signal_time.date() for row in episodes})
    gate = contract["candidates"][strategy_id]["frequency_gate"]
    instrument_key = next(key for key in gate if key.startswith("instruments_min_"))
    threshold = int(instrument_key.rsplit("_", 1)[1])
    instrument_pass = sum(value >= threshold for value in by_instrument.values()) >= gate[instrument_key]
    concentration = total > 0 and max(by_instrument.values()) / total <= gate["max_instrument_share"]
    year_shares = {key: value / total if total else 0.0 for key, value in by_year.items()}
    year_pass = all(value >= gate["each_year_share_min"] for value in year_shares.values())
    passed = total >= gate["episodes_min"] and active_dates >= gate["active_dates_min"] and instrument_pass and concentration and year_pass
    return {
        "strategy_id": strategy_id,
        "raw_signal_count": len(raw),
        "overlap_deduplicated_signal_count": len(dedup),
        "primary_episode_count": total,
        "active_utc_date_count": active_dates,
        "counts_by_instrument": by_instrument,
        "counts_by_direction": by_direction,
        "counts_by_year": by_year,
        "year_shares": year_shares,
        "raw_signal_identity_sha256": event_hash(raw),
        "deduplicated_signal_identity_sha256": event_hash(dedup),
        "primary_episode_identity_sha256": event_hash(episodes),
        "instrument_breadth_pass": instrument_pass,
        "instrument_concentration_pass": concentration,
        "year_coverage_pass": year_pass,
        "exploratory_frequency_pass": passed,
        "formal_phase9_effect": False,
    }


def validate_report(value: dict) -> None:
    if [row["strategy_id"] for row in value["strategy_results"]] != list(CANDIDATES):
        raise BlindCountError("candidate result order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_frequency_pass"]]
    if value["frequency_pass_candidates"] != expected:
        raise BlindCountError("passing candidate list mismatch")
    for row in value["strategy_results"]:
        if not row["raw_signal_count"] >= row["overlap_deduplicated_signal_count"] >= row["primary_episode_count"] >= 0:
            raise BlindCountError("count ordering mismatch")
        if sum(row["counts_by_instrument"].values()) != row["primary_episode_count"]:
            raise BlindCountError("instrument count mismatch")
        if sum(row["counts_by_direction"].values()) != row["primary_episode_count"]:
            raise BlindCountError("direction count mismatch")
        if sum(row["counts_by_year"].values()) != row["primary_episode_count"]:
            raise BlindCountError("year count mismatch")
    if value["return_calculated"] or value["research_outcomes_calculated"] or value["outcome_fields"]:
        raise BlindCountError("outcome boundary violated")
    if value["formal_count_only_authorized"] or value["formal_phase9_authorization_effect"]:
        raise BlindCountError("formal authorization changed")
    if value["persistent_price_files_after_cleanup"] != 0:
        raise BlindCountError("price persistence mismatch")
    base.reject_outcomes(value)


def write_artifact(report_dir: Path, report: dict) -> None:
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    payload = report_dir / OUTPUT
    base.write_new_json(payload, report)
    manifest = report_dir / "artifact_manifest_sha256.txt"
    manifest.write_text(f"{sha256_file(payload)}  {OUTPUT}\n", encoding="utf-8")
    members = {path.name for path in report_dir.iterdir()}
    if members != {OUTPUT, "artifact_manifest_sha256.txt"}:
        raise BlindCountError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BlindCountError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = load_contract(contract_path)
    base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    series = base.load_all_series(work_dir)
    raw: dict[str, list[Signal]] = {candidate: [] for candidate in CANDIDATES}
    for symbol in SYMBOLS:
        raw["EXP-P9-MTF-301"].extend(scan_301(symbol, series[(symbol, "M15")], series[(symbol, "H4")], contract["candidates"]["EXP-P9-MTF-301"]))
        raw["EXP-P9-MTF-302"].extend(scan_302(symbol, series[(symbol, "H4")], series[(symbol, "H1")], contract["candidates"]["EXP-P9-MTF-302"]))
        raw["EXP-P9-MTF-303"].extend(scan_303(symbol, series[(symbol, "D1")], series[(symbol, "H4")], contract["candidates"]["EXP-P9-MTF-303"]))
        raw["EXP-P9-MTF-304"].extend(scan_304(symbol, series[(symbol, "H1")], series[(symbol, "H4")], series[(symbol, "D1")], contract["candidates"]["EXP-P9-MTF-304"]))
    results = [frequency_result(candidate, raw[candidate], contract) for candidate in CANDIDATES]
    passing = [row["strategy_id"] for row in results if row["exploratory_frequency_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-count-only-result-v1.0.0",
        "status": "BLIND_MTF_COUNT_ONLY_COMPLETE_NO_OUTCOME",
        "run_identity": {"run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"), "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"), "head_sha": os.getenv("GITHUB_SHA", "LOCAL")},
        "contract_sha256": sha256_file(contract_path),
        "canonical_mtf_report_sha256": sha256_file(CANONICAL_MTF),
        "current_mtf_report_sha256": sha256_file(current_mtf),
        "dataset": {"symbols": list(SYMBOLS), "start_inclusive": contract["dataset"]["start_inclusive"], "end_exclusive": contract["dataset"]["end_exclusive"], "timeframes": contract["dataset"]["available_timeframes"], "price_or_event_timestamp_in_artifact": False},
        "strategy_results": results,
        "frequency_pass_candidates": passing,
        "candidate_signal_counts_calculated": True,
        "formal_count_only_authorized": False,
        "formal_phase9_authorization_effect": False,
        "return_calculated": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "persistent_price_files_after_cleanup": 0,
        "result_dependent_rule_change": False,
        "next_gate": "SEPARATE_RETURN_OOS_GATE_FOR_FREQUENCY_PASSERS_ONLY" if passing else "NO_RETURN_GATE",
    }
    validate_report(report)
    write_artifact(report_dir, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--current-mtf-report", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise BlindCountError("exact blind MTF Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise BlindCountError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
