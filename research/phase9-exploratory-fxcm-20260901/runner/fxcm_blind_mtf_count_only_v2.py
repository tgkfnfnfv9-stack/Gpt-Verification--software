#!/usr/bin/env python3
"""Count-only screen for the second independent blind FX8 MTF batch."""

from __future__ import annotations

import argparse
import bisect
from collections import defaultdict
from datetime import datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH2_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
CANDIDATES = ("EXP-P9-MTF-305", "EXP-P9-MTF-306", "EXP-P9-MTF-307", "EXP-P9-MTF-308")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH2_COUNT_ONLY.json"
ROOT = Path(__file__).resolve().parents[1]
V1_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only.py")
MTF_RUNNER = Path(__file__).with_name("fxcm_multitimeframe_qc.py")
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
V1_RETURN_RESULT = ROOT / "results/run-33582968006/EXPLORATORY_FXCM_BLIND_MTF_RETURN_OOS.json"
V1_RETURN_AUDIT = ROOT / "results/run-33582968006/BLIND_MTF_RETURN_OOS_INDEPENDENT_AUDIT.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v1 = load_module("fxcm_blind_mtf_batch2_base", V1_RUNNER)
base = v1.base
Bar = base.Bar
Signal = base.Signal
SYMBOLS = base.SYMBOLS


class Batch2CountError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def load_contract(path: Path) -> dict:
    value = base.load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-candidates-v2.0.0":
        raise Batch2CountError("batch2 schema mismatch")
    if value.get("status") != "FROZEN_AFTER_V1_REJECTIONS_BEFORE_FIRST_V2_SIGNAL_COUNT":
        raise Batch2CountError("batch2 freeze status mismatch")
    if tuple(value.get("candidates", {})) != CANDIDATES:
        raise Batch2CountError("batch2 candidate order mismatch")
    integrity = value["selection_integrity"]
    if integrity["v1_threshold_direction_symbol_or_exit_rescue_allowed"] is not False:
        raise Batch2CountError("v1 rescue enabled")
    if integrity["v2_candidate_return_or_outcome_viewed"] is not False:
        raise Batch2CountError("batch2 outcome already viewed")
    if value["common_rules"]["forward_outcome_access"] is not False:
        raise Batch2CountError("batch2 outcome access enabled")
    expected = {
        "base_count_utility_sha256": (v1.BASE_PATH, "2991575f471c19de35d04ae21d276cc25d52d9fb705587a8259f70d43639cdad"),
        "mtf_qc_runner_sha256": (MTF_RUNNER, "09da37be5955dcf142752d70dc21542f21e5ea71835c7f1073e68f52585971cd"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
        "v1_return_result_sha256": (V1_RETURN_RESULT, "4bb5005c7a3487a179c2ba30af6dac70443537d929628081baf9992dd6e1170e"),
        "v1_return_independent_audit_sha256": (V1_RETURN_AUDIT, "29a04b2934374fe26e3bb3b8f08f26cac480cb869bc1864a67f015c3cc0b0478"),
    }
    for key, (anchor_path, frozen) in expected.items():
        if value["anchors"].get(key) != frozen or sha256_file(anchor_path) != frozen:
            raise Batch2CountError(f"anchor mismatch: {key}")
    return value


def signal(strategy_id: str, symbol: str, timeframe: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(
        strategy_id, symbol, timeframe, direction,
        bars[index].timestamp + base.TIMEFRAME_DELTA[timeframe],
        bars[index + 1].timestamp, 0,
    )


def latest(times: list[datetime], states: list[str | None], when: datetime) -> str | None:
    index = bisect.bisect_right(times, when) - 1
    return states[index] if index >= 0 else None


def scan_305(symbol: str, h1: list[Bar], h4: list[Bar], d1: list[Bar], rules: dict) -> list[Signal]:
    d1_times, d1_states = v1.d1_direction(d1, rules)
    h1_times = [row.timestamp for row in h1]
    output = []
    lookback = rules["h4_narrow_range_lookback"]
    for event_index in range(max(15, lookback - 1), len(h4)):
        event = h4[event_index]
        atr = base.atr_before(h4, event_index)
        if atr is None or base.bar_range(event) > rules["h4_range_atr_max"] * atr:
            continue
        prior_ranges = [base.bar_range(row) for row in h4[event_index - lookback + 1:event_index]]
        if not prior_ranges or base.bar_range(event) > min(prior_ranges):
            continue
        available = event.timestamp + timedelta(hours=4)
        direction = latest(d1_times, d1_states, available)
        if direction is None:
            continue
        first = bisect.bisect_left(h1_times, available)
        for index in range(first, min(first + rules["h1_confirmation_bars_max"], len(h1) - 1)):
            h1_atr = base.atr_before(h1, index)
            row = h1[index]
            if h1_atr is None or base.bar_range(row) < rules["h1_range_atr_min"] * h1_atr:
                continue
            if base.body_ratio(row) < rules["h1_body_ratio_min"]:
                continue
            broken = (
                row.close >= event.high + rules["h1_break_distance_atr_min"] * h1_atr
                if direction == "LONG" else
                row.close <= event.low - rules["h1_break_distance_atr_min"] * h1_atr
            )
            if broken and base.entry_exists(h1, index, "H1"):
                output.append(signal("EXP-P9-MTF-305", symbol, "H1", direction, h1, index))
                break
    return output


def d1_ema_values(bars: list[Bar], rules: dict) -> tuple[list[float], list[float]]:
    closes = [row.close for row in bars]
    return base.ema(closes, rules["d1_ema_periods"][0]), base.ema(closes, rules["d1_ema_periods"][1])


def scan_306(symbol: str, d1: list[Bar], h4: list[Bar], rules: dict) -> list[Signal]:
    ema20, ema50 = d1_ema_values(d1, rules)
    h4_times = [row.timestamp for row in h4]
    output = []
    pull = rules["pullback_bars"]
    for event_index in range(rules["d1_ema_periods"][1] + pull, len(d1)):
        trend_index = event_index - pull
        direction = "LONG" if ema20[trend_index] > ema50[trend_index] else "SHORT" if ema20[trend_index] < ema50[trend_index] else None
        if direction is None:
            continue
        window = d1[trend_index:event_index + 1]
        closes = [row.close for row in window]
        against = (
            all(left >= right for left, right in zip(closes, closes[1:]))
            if direction == "LONG" else
            all(left <= right for left, right in zip(closes, closes[1:]))
        )
        atr = base.atr_before(d1, event_index)
        if not against or atr is None:
            continue
        depth = abs(closes[-1] - closes[0]) / atr
        if not rules["pullback_depth_atr_min"] <= depth <= rules["pullback_depth_atr_max"]:
            continue
        start = d1[event_index].timestamp + timedelta(days=1)
        first = bisect.bisect_left(h4_times, start)
        for index in range(first, min(first + rules["h4_confirmation_bars_max"], len(h4) - 1)):
            if index < rules["h4_boundary_lookback"]:
                continue
            h4_atr = base.atr_before(h4, index)
            row = h4[index]
            if h4_atr is None or base.body_ratio(row) < rules["h4_body_ratio_min"]:
                continue
            prior = h4[index - rules["h4_boundary_lookback"]:index]
            broken = (
                row.close >= max(item.high for item in prior) + rules["h4_break_distance_atr_min"] * h4_atr
                if direction == "LONG" else
                row.close <= min(item.low for item in prior) - rules["h4_break_distance_atr_min"] * h4_atr
            )
            if broken and base.entry_exists(h4, index, "H4"):
                output.append(signal("EXP-P9-MTF-306", symbol, "H4", direction, h4, index))
                break
    return output


def wick_ratio(row: Bar, direction: str) -> float:
    width = base.bar_range(row)
    if width <= 0:
        return 0.0
    if direction == "SHORT":
        return (row.high - max(row.open, row.close)) / width
    return (min(row.open, row.close) - row.low) / width


def rejection(row: Bar, boundary: float, atr: float, direction: str, rules: dict) -> bool:
    distance = rules["boundary_distance_atr_max"] * atr
    if direction == "SHORT":
        near = abs(row.high - boundary) <= distance and row.close <= boundary
    else:
        near = abs(row.low - boundary) <= distance and row.close >= boundary
    return near and wick_ratio(row, direction) >= rules["terminal_wick_ratio_min"]


def scan_307(symbol: str, h4: list[Bar], h1: list[Bar], rules: dict) -> list[Signal]:
    h1_times = [row.timestamp for row in h1]
    output = []
    for second in range(rules["boundary_lookback"] + 1, len(h4)):
        second_atr = base.atr_before(h4, second)
        if second_atr is None:
            continue
        found = None
        first_start = max(rules["boundary_lookback"], second - rules["second_rejection_bars_max"])
        for first in range(first_start, second):
            first_atr = base.atr_before(h4, first)
            if first_atr is None:
                continue
            prior = h4[first - rules["boundary_lookback"]:first]
            high_boundary = max(row.high for row in prior)
            low_boundary = min(row.low for row in prior)
            if rejection(h4[first], high_boundary, first_atr, "SHORT", rules) and rejection(h4[second], high_boundary, second_atr, "SHORT", rules):
                found = (first, "SHORT", min(row.low for row in h4[first:second + 1]))
                break
            if rejection(h4[first], low_boundary, first_atr, "LONG", rules) and rejection(h4[second], low_boundary, second_atr, "LONG", rules):
                found = (first, "LONG", max(row.high for row in h4[first:second + 1]))
                break
        if found is None:
            continue
        _, direction, neckline = found
        start = h4[second].timestamp + timedelta(hours=4)
        first_h1 = bisect.bisect_left(h1_times, start)
        for index in range(first_h1, min(first_h1 + rules["h1_confirmation_bars_max"], len(h1) - 1)):
            atr = base.atr_before(h1, index)
            row = h1[index]
            if atr is None or base.body_ratio(row) < rules["h1_body_ratio_min"]:
                continue
            broken = (
                row.close <= neckline - rules["h1_break_distance_atr_min"] * atr
                if direction == "SHORT" else
                row.close >= neckline + rules["h1_break_distance_atr_min"] * atr
            )
            if broken and base.entry_exists(h1, index, "H1"):
                output.append(signal("EXP-P9-MTF-307", symbol, "H1", direction, h1, index))
                break
    return output


def scan_308(symbol: str, m15: list[Bar], h1: list[Bar], h4: list[Bar], rules: dict) -> list[Signal]:
    h4_times, h4_states = v1.h4_direction(h4, rules)
    m15_times = [row.timestamp for row in m15]
    output = []
    for shock_index in range(15, len(h1)):
        shock = h1[shock_index]
        atr = base.atr_before(h1, shock_index)
        available = shock.timestamp + timedelta(hours=1)
        direction = latest(h4_times, h4_states, available)
        if atr is None or direction is None:
            continue
        if base.bar_range(shock) < rules["h1_shock_range_atr_min"] * atr or base.body_ratio(shock) < rules["h1_shock_body_ratio_min"]:
            continue
        if (direction == "LONG" and shock.close <= shock.open) or (direction == "SHORT" and shock.close >= shock.open):
            continue
        first = bisect.bisect_left(m15_times, available)
        max_index = min(first + rules["m15_confirmation_bars_max"], len(m15) - 1)
        for index in range(first + rules["m15_pullback_bars_min"], max_index):
            pullback = m15[first:index]
            if len(pullback) < rules["m15_pullback_bars_min"]:
                continue
            depth_limit = rules["m15_pullback_depth_shock_range_max"] * base.bar_range(shock)
            if direction == "LONG":
                shallow = min(row.low for row in pullback) >= shock.close - depth_limit
                pulled = pullback[-1].close < shock.close
                resumed = m15[index].close > max(row.high for row in m15[index - rules["m15_resume_boundary_lookback"]:index])
            else:
                shallow = max(row.high for row in pullback) <= shock.close + depth_limit
                pulled = pullback[-1].close > shock.close
                resumed = m15[index].close < min(row.low for row in m15[index - rules["m15_resume_boundary_lookback"]:index])
            if shallow and pulled and resumed and base.body_ratio(m15[index]) >= rules["m15_resume_body_ratio_min"] and base.entry_exists(m15, index, "M15"):
                output.append(signal("EXP-P9-MTF-308", symbol, "M15", direction, m15, index))
                break
    return output


def frequency_result(strategy_id: str, raw: list[Signal], contract: dict) -> dict:
    return v1.frequency_result(strategy_id, raw, contract)


def validate_report(value: dict) -> None:
    if [row["strategy_id"] for row in value["strategy_results"]] != list(CANDIDATES):
        raise Batch2CountError("candidate result order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_frequency_pass"]]
    if value["frequency_pass_candidates"] != expected:
        raise Batch2CountError("passing candidate list mismatch")
    if value["return_calculated"] or value["research_outcomes_calculated"] or value["outcome_fields"]:
        raise Batch2CountError("outcome boundary violated")
    if value["persistent_price_files_after_cleanup"] != 0 or value["formal_phase9_authorization_effect"]:
        raise Batch2CountError("custody or formal boundary violated")
    base.reject_outcomes(value)


def write_artifact(report_dir: Path, report: dict) -> None:
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    payload = report_dir / OUTPUT
    base.write_new_json(payload, report)
    manifest = report_dir / "artifact_manifest_sha256.txt"
    manifest.write_text(f"{sha256_file(payload)}  {OUTPUT}\n", encoding="utf-8")
    if {path.name for path in report_dir.iterdir()} != {OUTPUT, "artifact_manifest_sha256.txt"}:
        raise Batch2CountError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch2CountError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = load_contract(contract_path)
    base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    series = base.load_all_series(work_dir)
    raw: dict[str, list[Signal]] = {candidate: [] for candidate in CANDIDATES}
    for symbol in SYMBOLS:
        raw["EXP-P9-MTF-305"].extend(scan_305(symbol, series[(symbol, "H1")], series[(symbol, "H4")], series[(symbol, "D1")], contract["candidates"]["EXP-P9-MTF-305"]))
        raw["EXP-P9-MTF-306"].extend(scan_306(symbol, series[(symbol, "D1")], series[(symbol, "H4")], contract["candidates"]["EXP-P9-MTF-306"]))
        raw["EXP-P9-MTF-307"].extend(scan_307(symbol, series[(symbol, "H4")], series[(symbol, "H1")], contract["candidates"]["EXP-P9-MTF-307"]))
        raw["EXP-P9-MTF-308"].extend(scan_308(symbol, series[(symbol, "M15")], series[(symbol, "H1")], series[(symbol, "H4")], contract["candidates"]["EXP-P9-MTF-308"]))
    results = [frequency_result(candidate, raw[candidate], contract) for candidate in CANDIDATES]
    passing = [row["strategy_id"] for row in results if row["exploratory_frequency_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch2-count-only-result-v1.0.0",
        "status": "BLIND_MTF_BATCH2_COUNT_ONLY_COMPLETE_NO_OUTCOME",
        "run_identity": {"run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"), "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"), "head_sha": os.getenv("GITHUB_SHA", "LOCAL")},
        "contract_sha256": sha256_file(contract_path),
        "canonical_mtf_report_sha256": sha256_file(CANONICAL_MTF),
        "current_mtf_report_sha256": sha256_file(current_mtf),
        "dataset": {"symbols": list(SYMBOLS), "start_inclusive": contract["dataset"]["start_inclusive"], "end_exclusive": contract["dataset"]["end_exclusive"], "timeframes": contract["dataset"]["available_timeframes"], "price_or_event_timestamp_in_artifact": False},
        "strategy_results": results,
        "frequency_pass_candidates": passing,
        "candidate_signal_counts_calculated": True,
        "return_calculated": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "persistent_price_files_after_cleanup": 0,
        "formal_phase9_authorization_effect": False,
        "v1_candidate_rescue_performed": False,
        "result_dependent_rule_change": False,
        "next_gate": "SEPARATE_CUMULATIVE_MULTIPLICITY_ADJUSTED_RETURN_OOS_GATE_FOR_FREQUENCY_PASSERS_ONLY" if passing else "NO_RETURN_GATE",
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
        raise Batch2CountError("exact batch2 Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch2CountError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
