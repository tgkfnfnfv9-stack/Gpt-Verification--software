#!/usr/bin/env python3
"""Count-only screen for preregistered PS-204 on the existing FX8 subset."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path


CONFIRMATION = "RUN_EXPLORATORY_FXCM_PS204_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
STRATEGY_ID = "STRAT-P9-PS-204"
SYMBOLS = ("AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY", "GBPUSD", "USDJPY")
TIMEFRAMES = ("M15", "H1")
TIMEFRAME_DELTA = {"M15": timedelta(minutes=15), "H1": timedelta(hours=1)}
EXPECTED_SESSION_BARS = {"M15": 24, "H1": 6}
UTC = timezone.utc
HEX64 = re.compile(r"^[0-9a-f]{64}$")
OUTCOME_KEYS = {
    "return", "returns", "forward_return", "return_sign", "edge", "mfe", "mae",
    "win", "wins", "loss", "losses", "win_rate", "profit_factor", "drawdown",
    "profit", "pnl", "expectancy", "cumulative_r", "p_value", "pvalue",
    "confidence_interval", "equity_curve", "sharpe", "sortino", "outcome", "outcomes",
}
REPORT_KEYS = {
    "schema_version", "status", "track", "run_identity", "contract_sha256",
    "candidate_registry_sha256", "prior_count_run_audit_sha256",
    "canonical_mtf_report_sha256", "current_mtf_report_sha256",
    "current_mtf_matches_canonical_data_identity", "dataset", "session_diagnostics",
    "strategy_result", "exploratory_fx8_frequency_pass_candidates",
    "candidate_signal_counts_calculated", "exploratory_count_only_executed",
    "formal_count_only_authorized", "formal_phase9_authorization_effect",
    "return_calculated", "research_outcomes_calculated", "outcome_fields",
    "persistent_price_files_after_cleanup", "result_dependent_rule_change", "next_gate",
}


class Ps204CountError(RuntimeError):
    pass


UTILITY_PATH = Path(__file__).with_name("fxcm_rr_count_only.py")
UTILITY_SPEC = importlib.util.spec_from_file_location("fxcm_ps204_shared_utility", UTILITY_PATH)
if UTILITY_SPEC is None or UTILITY_SPEC.loader is None:
    raise RuntimeError("cannot load shared Count-only utility")
utility = importlib.util.module_from_spec(UTILITY_SPEC)
sys.modules[UTILITY_SPEC.name] = utility
UTILITY_SPEC.loader.exec_module(utility)
Bar = utility.Bar
Signal = utility.Signal


def sha256_file(path: Path) -> str:
    return utility.sha256_file(path)


def iso(value: datetime) -> str:
    return utility.iso(value)


def load_json(path: Path) -> dict:
    return utility.load_json(path)


def validate_contract(
    contract_path: Path,
    registry_path: Path,
    entry_gate_path: Path,
    prior_audit_path: Path,
    prior_result_path: Path,
    canonical_mtf_path: Path,
) -> dict:
    contract = load_json(contract_path)
    checks = (
        (contract.get("schema_version") == "phase9-exploratory-fxcm-ps204-count-only-v1.0.0", "schema"),
        (contract.get("status") == "FROZEN_AFTER_PRIOR_COUNT_RESULTS_BEFORE_FIRST_PS204_SIGNAL_COUNT", "status"),
        (contract.get("selection_integrity", {}).get("candidate_signal_count_previously_calculated") is False, "prior PS-204 count"),
        (contract.get("selection_integrity", {}).get("candidate_return_or_outcome_previously_calculated") is False, "prior PS-204 outcome"),
        (contract.get("selection_integrity", {}).get("prior_candidate_count_results_do_not_change_ps204_parameters") is True, "parameter integrity"),
        (contract.get("scope_amendment", {}).get("exploratory_fx8_subset_only") is True, "subset"),
        (contract.get("scope_amendment", {}).get("formal_phase9_promotion_or_rejection_effect") is False, "formal effect"),
        (contract.get("dataset", {}).get("symbols") == list(SYMBOLS), "symbols"),
        (contract.get("dataset", {}).get("registered_missing_symbols") == ["XAUUSD", "XAGUSD"], "missing registered symbols"),
        (contract.get("ps204", {}).get("strategy_id") == STRATEGY_ID, "candidate"),
        (contract.get("ps204", {}).get("timeframes") == list(TIMEFRAMES), "timeframes"),
        (contract.get("ps204", {}).get("pre_session_exact_nominal_slots_required") == EXPECTED_SESSION_BARS, "session slots"),
        (contract.get("common_rules", {}).get("forward_outcome_access") is False, "outcome access"),
        (contract.get("scientific_state_before_run", {}).get("ps204_signal_count_calculated") is False, "scientific count state"),
        (contract.get("scientific_state_before_run", {}).get("candidate_return_calculated") is False, "scientific return state"),
        (contract.get("scientific_state_before_run", {}).get("research_outcomes_calculated") is False, "scientific outcome state"),
    )
    for passed, label in checks:
        if not passed:
            raise Ps204CountError(f"frozen PS-204 contract mismatch: {label}")
    anchors = contract["anchors"]
    for label, path in (
        ("candidate_registry", registry_path),
        ("entry_gate", entry_gate_path),
        ("prior_single_pair_count_run_audit", prior_audit_path),
        ("prior_single_pair_count_result", prior_result_path),
        ("canonical_mtf_report", canonical_mtf_path),
        ("shared_count_utility", UTILITY_PATH),
    ):
        if anchors[label]["sha256"] != sha256_file(path):
            raise Ps204CountError(f"frozen anchor SHA mismatch: {label}")
    return contract


def validate_registry(registry_path: Path) -> None:
    registry = load_json(registry_path)
    rows = [row for row in registry.get("candidates", []) if row.get("strategy_id") == STRATEGY_ID]
    if len(rows) != 1:
        raise Ps204CountError("registered PS-204 candidate mismatch")
    row = rows[0]
    if row.get("targets") != [*SYMBOLS, "XAUUSD", "XAGUSD"]:
        raise Ps204CountError("registered PS-204 universe mismatch")
    if row.get("timeframes") != list(TIMEFRAMES):
        raise Ps204CountError("registered PS-204 timeframe mismatch")
    if row.get("sample_size_gate") != 500 or row.get("gate_profile") != "BROAD_MULTI_ASSET_2TF":
        raise Ps204CountError("registered PS-204 Gate mismatch")


def load_series(work_dir: Path) -> dict[tuple[str, str], list[Bar]]:
    direct = work_dir / "direct"
    derived = work_dir / "derived"
    if not direct.is_dir() or not derived.is_dir() or work_dir.is_symlink():
        raise Ps204CountError("invalid ephemeral MTF working tree")
    output = {}
    for symbol in SYMBOLS:
        output[(symbol, "M15")] = utility.load_mid_series(
            derived / f"{symbol}_M15_bid.csv", derived / f"{symbol}_M15_ask.csv"
        )
        output[(symbol, "H1")] = utility.load_mid_series(
            direct / f"{symbol}_H1_bid.csv", direct / f"{symbol}_H1_ask.csv"
        )
    return output


def true_range_mean_before(bars: list[Bar], index: int, period: int = 14) -> float | None:
    if index < period + 1:
        return None
    values = [utility.true_range(bars, position) for position in range(index - period, index)]
    result = sum(values) / period
    return result if result > 0 and math.isfinite(result) else None


def close_location(bar: Bar, direction: str) -> float:
    width = bar.high - bar.low
    if width <= 0:
        return 0.0
    return (bar.close - bar.low) / width if direction == "LONG" else (bar.high - bar.close) / width


def entry_exists(bars: list[Bar], index: int, timeframe: str) -> bool:
    if index + 1 >= len(bars):
        return False
    duration = TIMEFRAME_DELTA[timeframe]
    confirmation_close = bars[index].timestamp + duration
    return confirmation_close <= bars[index + 1].timestamp <= confirmation_close + 2 * duration


def make_signal(symbol: str, timeframe: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(
        STRATEGY_ID, symbol, timeframe, direction,
        bars[index].timestamp + TIMEFRAME_DELTA[timeframe], bars[index + 1].timestamp, 0,
    )


def expected_times(day: datetime, timeframe: str, start_hour: int, end_hour: int) -> list[datetime]:
    duration = TIMEFRAME_DELTA[timeframe]
    current = day + timedelta(hours=start_hour)
    end = day + timedelta(hours=end_hour)
    output = []
    while current < end:
        output.append(current)
        current += duration
    return output


def scan_ps204(symbol: str, timeframe: str, bars: list[Bar]) -> tuple[list[Signal], dict]:
    duration = TIMEFRAME_DELTA[timeframe]
    by_time = {bar.timestamp: index for index, bar in enumerate(bars)}
    days = sorted({bar.timestamp.date() for bar in bars})
    signals = []
    diagnostics = {
        "utc_dates_with_any_bar": len(days),
        "complete_pre_session_date_count": 0,
        "atr_available_at_0600_date_count": 0,
        "range_eligible_date_count": 0,
        "confirmed_false_break_count": 0,
    }
    for date_value in days:
        day = datetime.combine(date_value, time.min, tzinfo=UTC)
        session_times = expected_times(day, timeframe, 0, 6)
        if len(session_times) != EXPECTED_SESSION_BARS[timeframe] or any(timestamp not in by_time for timestamp in session_times):
            continue
        diagnostics["complete_pre_session_date_count"] += 1
        six = day + timedelta(hours=6)
        six_index = by_time.get(six)
        if six_index is None:
            continue
        atr = true_range_mean_before(bars, six_index)
        if atr is None:
            continue
        diagnostics["atr_available_at_0600_date_count"] += 1
        session = [bars[by_time[timestamp]] for timestamp in session_times]
        range_high = max(bar.high for bar in session)
        range_low = min(bar.low for bar in session)
        range_ratio = (range_high - range_low) / atr
        if not 0.75 <= range_ratio <= 2.50:
            continue
        diagnostics["range_eligible_date_count"] += 1
        consumed = {"UPSIDE": False, "DOWNSIDE": False}
        for break_time in expected_times(day, timeframe, 6, 10):
            break_index = by_time.get(break_time)
            if break_index is None:
                continue
            break_bar = bars[break_index]
            side = None
            if break_bar.high >= range_high + 0.15 * atr and break_bar.close >= range_high + 0.15 * atr:
                side = "UPSIDE"
                direction = "SHORT"
            elif break_bar.low <= range_low - 0.15 * atr and break_bar.close <= range_low - 0.15 * atr:
                side = "DOWNSIDE"
                direction = "LONG"
            if side is None or consumed[side]:
                continue
            for offset in (1, 2):
                reclaim_time = break_time + offset * duration
                reclaim_index = by_time.get(reclaim_time)
                if reclaim_index is None:
                    continue
                reclaim = bars[reclaim_index]
                inside = (
                    reclaim.close <= range_high - 0.10 * atr
                    if side == "UPSIDE" else
                    reclaim.close >= range_low + 0.10 * atr
                )
                if inside and close_location(reclaim, direction) >= 0.65 and entry_exists(bars, reclaim_index, timeframe):
                    signals.append(make_signal(symbol, timeframe, direction, bars, reclaim_index))
                    diagnostics["confirmed_false_break_count"] += 1
                    consumed[side] = True
                    break
    return signals, diagnostics


def primary_episodes(signals: list[Signal]) -> list[Signal]:
    priority = {"H1": 0, "M15": 1}
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
        for row in sorted(signals, key=lambda item: (item.signal_time, item.symbol, item.timeframe, item.direction))
    ]
    return hashlib.sha256("".join(rows).encode("ascii")).hexdigest()


def frequency_result(raw: list[Signal], contract: dict) -> dict:
    deduplicated = utility.collapse_overlaps(raw)
    episodes = primary_episodes(deduplicated)
    by_instrument = {symbol: 0 for symbol in SYMBOLS}
    by_timeframe = {timeframe: 0 for timeframe in TIMEFRAMES}
    by_direction = {"LONG": 0, "SHORT": 0}
    by_year = {"2017": 0, "2018": 0}
    for signal in episodes:
        by_instrument[signal.symbol] += 1
        by_timeframe[signal.timeframe] += 1
        by_direction[signal.direction] += 1
        year = str(signal.signal_time.year)
        if year not in by_year:
            raise Ps204CountError("episode outside frozen years")
        by_year[year] += 1
    total = len(episodes)
    active_dates = len({signal.signal_time.date() for signal in episodes})
    gate = contract["exploratory_fx8_frequency_gate"]
    shares = {key: value / total if total else 0.0 for key, value in by_timeframe.items()}
    instrument_breadth_pass = sum(value >= 30 for value in by_instrument.values()) >= gate["instruments_with_at_least_30_episodes_min"]
    instrument_concentration_pass = total > 0 and max(by_instrument.values()) / total <= gate["single_instrument_share_max_inclusive"]
    timeframe_coverage_pass = (
        all(value >= gate["each_timeframe_episodes_min"] for value in by_timeframe.values())
        and all(value >= gate["each_timeframe_share_min_inclusive"] for value in shares.values())
    )
    passed = (
        total >= gate["primary_episodes_min"]
        and active_dates >= gate["active_utc_dates_min"]
        and instrument_breadth_pass
        and instrument_concentration_pass
        and timeframe_coverage_pass
    )
    return {
        "strategy_id": STRATEGY_ID,
        "formal_profile": contract["ps204"]["formal_profile"],
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
        "fx8_instrument_breadth_pass": instrument_breadth_pass,
        "fx8_instrument_concentration_pass": instrument_concentration_pass,
        "fx8_timeframe_coverage_pass": timeframe_coverage_pass,
        "exploratory_fx8_frequency_pass": passed,
        "exploratory_decision": gate["if_pass"] if passed else gate["if_fail"],
        "formal_count_only_gate_passed": False,
        "formal_scope_ineligible_reasons": [
            "FX8_SUBSET_MISSING_REGISTERED_XAUUSD_AND_XAGUSD",
            "ONLY_2017_2018_NOT_FULL_FORMAL_DISCOVERY",
            "EXPLORATORY_M15_DERIVED_FROM_M1_NOT_FORMAL_DIRECT_M15",
        ],
        "formal_control_assignment_completed": False,
    }


def reject_outcomes(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in OUTCOME_KEYS:
                raise Ps204CountError(f"prohibited outcome field: {key}")
            reject_outcomes(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_outcomes(nested)


def validate_report(report: dict) -> None:
    if set(report) != REPORT_KEYS:
        raise Ps204CountError("PS-204 report exact key mismatch")
    for field in (
        "contract_sha256", "candidate_registry_sha256", "prior_count_run_audit_sha256",
        "canonical_mtf_report_sha256", "current_mtf_report_sha256",
    ):
        if not isinstance(report[field], str) or not HEX64.fullmatch(report[field]):
            raise Ps204CountError(f"invalid report SHA: {field}")
    row = report["strategy_result"]
    if row["strategy_id"] != STRATEGY_ID:
        raise Ps204CountError("strategy result mismatch")
    if row["raw_signal_count"] < row["overlap_deduplicated_signal_count"] or row["overlap_deduplicated_signal_count"] < row["primary_episode_count"]:
        raise Ps204CountError("signal count ordering mismatch")
    for field in ("counts_by_instrument", "counts_by_timeframe", "counts_by_direction", "counts_by_year"):
        if sum(row[field].values()) != row["primary_episode_count"]:
            raise Ps204CountError(f"episode group count mismatch: {field}")
    expected_pass = [STRATEGY_ID] if row["exploratory_fx8_frequency_pass"] else []
    if report["exploratory_fx8_frequency_pass_candidates"] != expected_pass:
        raise Ps204CountError("passing candidate list mismatch")
    if row["formal_count_only_gate_passed"] is not False or row["formal_control_assignment_completed"] is not False:
        raise Ps204CountError("formal Gate/control state mismatch")
    if report["candidate_signal_counts_calculated"] is not True or report["exploratory_count_only_executed"] is not True:
        raise Ps204CountError("Count-only completion mismatch")
    if report["formal_count_only_authorized"] is not False or report["formal_phase9_authorization_effect"] is not False:
        raise Ps204CountError("formal state mismatch")
    if report["return_calculated"] is not False or report["research_outcomes_calculated"] is not False or report["outcome_fields"] != []:
        raise Ps204CountError("outcome state mismatch")
    if report["persistent_price_files_after_cleanup"] != 0 or report["result_dependent_rule_change"] is not False:
        raise Ps204CountError("cleanup/rule-change state mismatch")
    reject_outcomes(report)


def write_new_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def validate_report_tree(report_dir: Path, include_manifest: bool) -> None:
    expected = {"EXPLORATORY_FXCM_PS204_COUNT_ONLY.json"}
    if include_manifest:
        expected.add("artifact_manifest_sha256.txt")
    actual = set()
    for path in report_dir.rglob("*"):
        if path.is_symlink():
            raise Ps204CountError("symlink in report")
        if path.is_file():
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise Ps204CountError("non-regular report file")
            actual.add(path.relative_to(report_dir).as_posix())
    if actual != expected:
        raise Ps204CountError("PS-204 report exact path mismatch")


def seal_manifest(report_dir: Path) -> None:
    payload = report_dir / "EXPLORATORY_FXCM_PS204_COUNT_ONLY.json"
    manifest = report_dir / "artifact_manifest_sha256.txt"
    with manifest.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{sha256_file(payload)}  {payload.name}\n")
    validate_report_tree(report_dir, True)


def run(
    contract_path: Path,
    registry_path: Path,
    entry_gate_path: Path,
    prior_audit_path: Path,
    prior_result_path: Path,
    current_mtf_path: Path,
    canonical_mtf_path: Path,
    work_dir: Path,
    report_dir: Path,
) -> dict:
    contract = validate_contract(
        contract_path, registry_path, entry_gate_path, prior_audit_path,
        prior_result_path, canonical_mtf_path,
    )
    validate_registry(registry_path)
    utility.validate_mtf_identity(current_mtf_path, canonical_mtf_path)
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("PS-204 report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    series = load_series(work_dir)
    raw = []
    diagnostics = {}
    for symbol in SYMBOLS:
        diagnostics[symbol] = {}
        for timeframe in TIMEFRAMES:
            signals, detail = scan_ps204(symbol, timeframe, series[(symbol, timeframe)])
            raw.extend(signals)
            diagnostics[symbol][timeframe] = detail
    result = frequency_result(raw, contract)
    passing = [STRATEGY_ID] if result["exploratory_fx8_frequency_pass"] else []
    report = {
        "schema_version": "phase9-exploratory-fxcm-ps204-count-only-result-v1.0.0",
        "status": "EXPLORATORY_FX8_PS204_COUNT_ONLY_COMPLETE_FORMAL_SCOPE_INELIGIBLE",
        "track": contract["track"],
        "run_identity": {
            "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"),
            "head_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        },
        "contract_sha256": sha256_file(contract_path),
        "candidate_registry_sha256": sha256_file(registry_path),
        "prior_count_run_audit_sha256": sha256_file(prior_audit_path),
        "canonical_mtf_report_sha256": sha256_file(canonical_mtf_path),
        "current_mtf_report_sha256": sha256_file(current_mtf_path),
        "current_mtf_matches_canonical_data_identity": True,
        "dataset": {
            "symbols": list(SYMBOLS),
            "registered_missing_symbols": contract["dataset"]["registered_missing_symbols"],
            "start_inclusive": contract["dataset"]["start_inclusive"],
            "end_exclusive": contract["dataset"]["end_exclusive"],
            "timeframes_available": list(TIMEFRAMES),
            "signal_feature_price": contract["dataset"]["signal_feature_price"],
            "cross_instrument_synchronization_required": False,
            "price_or_event_timestamp_in_artifact": False,
        },
        "session_diagnostics": diagnostics,
        "strategy_result": result,
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
        "next_gate": "SEPARATE_EXPLORATORY_RETURN_GATE_REQUIRED_FOR_PS204" if passing else "NO_EXPLORATORY_RETURN_GATE",
    }
    validate_report(report)
    write_new_json(report_dir / "EXPLORATORY_FXCM_PS204_COUNT_ONLY.json", report)
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
    parser.add_argument("--prior-count-run-audit", type=Path, required=True)
    parser.add_argument("--prior-count-result", type=Path, required=True)
    parser.add_argument("--current-mtf-report", type=Path, required=True)
    parser.add_argument("--canonical-mtf-report", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise Ps204CountError("exact exploratory PS-204 Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Ps204CountError("personal non-commercial FXCM EULA confirmation required")
    run(
        args.contract, args.candidate_registry, args.entry_gate,
        args.prior_count_run_audit, args.prior_count_result,
        args.current_mtf_report, args.canonical_mtf_report,
        args.work_dir, args.report_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
