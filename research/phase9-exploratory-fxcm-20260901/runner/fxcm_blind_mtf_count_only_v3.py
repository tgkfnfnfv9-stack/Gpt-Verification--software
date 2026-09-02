#!/usr/bin/env python3
"""Count-only screen for the independent third blind FX8 MTF batch."""

from __future__ import annotations

import argparse
import bisect
from collections import defaultdict
from datetime import datetime, timedelta
import importlib.util
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH3_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
CANDIDATES = ("EXP-P9-MTF-309", "EXP-P9-MTF-310", "EXP-P9-MTF-311", "EXP-P9-MTF-312")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH3_COUNT_ONLY.json"
ROOT = Path(__file__).resolve().parents[1]
V1_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only.py")
MTF_RUNNER = Path(__file__).with_name("fxcm_multitimeframe_qc.py")
BASE_UTILITY = Path(__file__).with_name("fxcm_single_pair_count_only.py")
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
BATCH1_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v1.frozen.json"
BATCH2_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v2.frozen.json"
LATEST_OUTCOME_AUDIT = ROOT / "results/run-33587536789/BLIND_MTF_BATCH2_RETURN_OOS_INDEPENDENT_AUDIT.json"
PAIR_CURRENCIES = {
    "AUDJPY": ("AUD", "JPY"), "AUDUSD": ("AUD", "USD"),
    "EURGBP": ("EUR", "GBP"), "EURJPY": ("EUR", "JPY"),
    "EURUSD": ("EUR", "USD"), "GBPJPY": ("GBP", "JPY"),
    "GBPUSD": ("GBP", "USD"), "USDJPY": ("USD", "JPY"),
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v1 = load_module("fxcm_blind_mtf_batch3_base", V1_RUNNER)
base = v1.base
Bar = base.Bar
Signal = base.Signal
SYMBOLS = base.SYMBOLS


class Batch3CountError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def load_contract(path: Path) -> dict:
    value = base.load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-candidates-v3.0.0":
        raise Batch3CountError("batch3 schema mismatch")
    if value.get("status") != "FROZEN_AFTER_BATCH2_REJECTION_BEFORE_FIRST_BATCH3_SIGNAL_COUNT":
        raise Batch3CountError("batch3 freeze status mismatch")
    if tuple(value.get("candidates", {})) != CANDIDATES:
        raise Batch3CountError("batch3 candidate order mismatch")
    if value["dataset"]["symbols"] != list(SYMBOLS):
        raise Batch3CountError("batch3 FX8 scope mismatch")
    integrity = value["selection_integrity"]
    if integrity["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"] is not False:
        raise Batch3CountError("prior candidate rescue enabled")
    if integrity["batch3_count_or_outcome_viewed_before_freeze"] is not False:
        raise Batch3CountError("batch3 results viewed before freeze")
    if integrity["future_return_familywise_correction_must_include_prior_three_outcome_candidates"] is not True:
        raise Batch3CountError("future cumulative multiplicity boundary missing")
    if value["common_rules"]["forward_outcome_access"] is not False:
        raise Batch3CountError("forward outcome access enabled")
    if value["candidates"]["EXP-P9-MTF-312"]["target_pair_excluded_from_currency_vote"] is not True:
        raise Batch3CountError("target pair exclusion disabled")
    if value["candidates"]["EXP-P9-MTF-312"]["frequency_gate_unit"] != "SYNCHRONIZED_UTC_DATE_PLUS_DIRECTION":
        raise Batch3CountError("312 frequency unit mismatch")
    if value["candidates"]["EXP-P9-MTF-312"]["instrument_breadth_gate_applicable"] is not False:
        raise Batch3CountError("312 synchronized-event gate mismatch")
    if value["candidates"]["EXP-P9-MTF-309"]["h4_exhaustion_selection"] != "EARLIEST_QUALIFYING_EXHAUSTION_ONLY":
        raise Batch3CountError("309 event selection mismatch")
    if value["candidates"]["EXP-P9-MTF-310"]["h4_failure_selection"] != "EARLIEST_QUALIFYING_FAILURE_ONLY":
        raise Batch3CountError("310 event selection mismatch")
    expected = {
        "base_count_utility_sha256": (BASE_UTILITY, "2991575f471c19de35d04ae21d276cc25d52d9fb705587a8259f70d43639cdad"),
        "mtf_qc_runner_sha256": (MTF_RUNNER, "09da37be5955dcf142752d70dc21542f21e5ea71835c7f1073e68f52585971cd"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
        "batch1_candidate_contract_sha256": (BATCH1_CONTRACT, "8d832dbf779098d00c731d87547b30ed6944ee2c227d505e540ea95a7efaa1e3"),
        "batch2_candidate_contract_sha256": (BATCH2_CONTRACT, "4fac27599445d7dc28b7cffc99c8c6fdd19c640e2fb0fca1a90b9d5f799bc615"),
        "latest_outcome_audit_sha256": (LATEST_OUTCOME_AUDIT, "83f136d8ef8ffb50bda9f92edd3a7cccb4c0b2aa4f783572147371cba56290e0"),
    }
    for key, (anchor_path, frozen) in expected.items():
        if value["anchors"].get(key) != frozen or sha256_file(anchor_path) != frozen:
            raise Batch3CountError(f"anchor mismatch: {key}")
    if set(value["mechanism_independence"]) != set(CANDIDATES):
        raise Batch3CountError("mechanism independence matrix mismatch")
    return value


def signal(strategy_id: str, symbol: str, timeframe: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(
        strategy_id, symbol, timeframe, direction,
        bars[index].timestamp + base.TIMEFRAME_DELTA[timeframe],
        bars[index + 1].timestamp, 0,
    )


def terminal_wick_ratio(row: Bar, reversal_direction: str) -> float:
    width = base.bar_range(row)
    if width <= 0:
        return 0.0
    if reversal_direction == "SHORT":
        return (row.high - max(row.open, row.close)) / width
    return (min(row.open, row.close) - row.low) / width


def scan_309(symbol: str, d1: list[Bar], h4: list[Bar], h1: list[Bar], rules: dict) -> list[Signal]:
    ema20 = base.ema([row.close for row in d1], rules["d1_ema_period"])
    h4_times = [row.timestamp for row in h4]
    h1_times = [row.timestamp for row in h1]
    output = []
    for d1_index in range(max(15, rules["d1_ema_period"]), len(d1)):
        atr = base.atr_before(d1, d1_index)
        if atr is None:
            continue
        displacement = d1[d1_index].close - ema20[d1_index]
        if displacement >= rules["d1_overextension_atr_min"] * atr:
            direction = "SHORT"
        elif displacement <= -rules["d1_overextension_atr_min"] * atr:
            direction = "LONG"
        else:
            continue
        available = d1[d1_index].timestamp + timedelta(days=1)
        first_h4 = bisect.bisect_left(h4_times, available)
        for h4_index in range(first_h4, min(first_h4 + rules["h4_exhaustion_bars_max"], len(h4))):
            h4_atr = base.atr_before(h4, h4_index)
            row = h4[h4_index]
            if h4_atr is None or base.bar_range(row) < rules["h4_range_atr_min"] * h4_atr:
                continue
            extension_agrees = row.close > row.open if direction == "SHORT" else row.close < row.open
            if not extension_agrees or terminal_wick_ratio(row, direction) < rules["h4_terminal_wick_ratio_min"]:
                continue
            midpoint = (row.high + row.low) / 2.0
            first_h1 = bisect.bisect_left(h1_times, row.timestamp + timedelta(hours=4))
            for h1_index in range(first_h1, min(first_h1 + rules["h1_recapture_bars_max"], len(h1) - 1)):
                confirm = h1[h1_index]
                recaptured = confirm.close < midpoint if direction == "SHORT" else confirm.close > midpoint
                directional = confirm.close < confirm.open if direction == "SHORT" else confirm.close > confirm.open
                if recaptured and directional and base.body_ratio(confirm) >= rules["h1_body_ratio_min"] and base.entry_exists(h1, h1_index, "H1"):
                    output.append(signal("EXP-P9-MTF-309", symbol, "H1", direction, h1, h1_index))
                    break
            break
    return output


def scan_310(symbol: str, h4: list[Bar], m15: list[Bar], rules: dict) -> list[Signal]:
    m15_times = [row.timestamp for row in m15]
    output = []
    lookback = rules["h4_boundary_lookback"]
    for break_index in range(max(15, lookback), len(h4) - 1):
        atr = base.atr_before(h4, break_index)
        row = h4[break_index]
        if atr is None or base.body_ratio(row) < rules["h4_break_body_ratio_min"]:
            continue
        prior = h4[break_index - lookback:break_index]
        high_boundary = max(item.high for item in prior)
        low_boundary = min(item.low for item in prior)
        if row.close >= high_boundary + rules["h4_break_distance_atr_min"] * atr and row.close > row.open:
            breakout_direction, reversal_direction, boundary = "LONG", "SHORT", high_boundary
        elif row.close <= low_boundary - rules["h4_break_distance_atr_min"] * atr and row.close < row.open:
            breakout_direction, reversal_direction, boundary = "SHORT", "LONG", low_boundary
        else:
            continue
        for failure_index in range(break_index + 1, min(break_index + 1 + rules["h4_failure_bars_max"], len(h4))):
            failure = h4[failure_index]
            failure_atr = base.atr_before(h4, failure_index)
            if failure_atr is None or base.body_ratio(failure) < rules["h4_failure_body_ratio_min"]:
                continue
            failed = (
                failure.close <= boundary - rules["h4_reentry_distance_atr_min"] * failure_atr
                if breakout_direction == "LONG" else
                failure.close >= boundary + rules["h4_reentry_distance_atr_min"] * failure_atr
            )
            directional = failure.close < failure.open if reversal_direction == "SHORT" else failure.close > failure.open
            if not failed or not directional:
                continue
            midpoint = (failure.high + failure.low) / 2.0
            first_m15 = bisect.bisect_left(m15_times, failure.timestamp + timedelta(hours=4))
            for m15_index in range(first_m15, min(first_m15 + rules["m15_confirmation_bars_max"], len(m15) - 1)):
                confirm = m15[m15_index]
                crossed = confirm.close < midpoint if reversal_direction == "SHORT" else confirm.close > midpoint
                agrees = confirm.close < confirm.open if reversal_direction == "SHORT" else confirm.close > confirm.open
                if crossed and agrees and base.body_ratio(confirm) >= rules["m15_body_ratio_min"] and base.entry_exists(m15, m15_index, "M15"):
                    output.append(signal("EXP-P9-MTF-310", symbol, "M15", reversal_direction, m15, m15_index))
                    break
            break
    return output


def scan_311(symbol: str, h1: list[Bar], h4: list[Bar], rules: dict) -> list[Signal]:
    h4_times, h4_states = v1.h4_direction(h4, rules)
    output = []
    for index in range(15, len(h1) - 1):
        row = h1[index]
        if row.timestamp.hour != rules["fixed_signal_bar_open_hour_utc"]:
            continue
        direction = v1.latest(h4_times, h4_states, row.timestamp + timedelta(hours=1))
        atr = base.atr_before(h1, index)
        if direction is None or atr is None:
            continue
        range_ratio = base.bar_range(row) / atr
        directional = row.close > row.open if direction == "LONG" else row.close < row.open
        if (
            rules["h1_range_atr_min"] <= range_ratio <= rules["h1_range_atr_max"]
            and directional
            and base.body_ratio(row) >= rules["h1_body_ratio_min"]
            and base.entry_exists(h1, index, "H1")
        ):
            output.append(signal("EXP-P9-MTF-311", symbol, "H1", direction, h1, index))
    return output


def currency_vote(pair: str, change: float, scores: dict[str, int], counts: dict[str, int]) -> None:
    base_currency, quote_currency = PAIR_CURRENCIES[pair]
    if change == 0:
        return
    direction = 1 if change > 0 else -1
    scores[base_currency] += direction
    scores[quote_currency] -= direction
    counts[base_currency] += 1
    counts[quote_currency] += 1


def scan_312(h1_by_symbol: dict[str, list[Bar]], rules: dict) -> list[Signal]:
    maps = {symbol: {row.timestamp: (index, row) for index, row in enumerate(rows)} for symbol, rows in h1_by_symbol.items()}
    common_times = set.intersection(*(set(value) for value in maps.values()))
    lookback = timedelta(hours=rules["cross_pair_lookback_hours"])
    output = []
    for when in sorted(common_times):
        prior_time = when - lookback
        if not all(prior_time in maps[symbol] for symbol in SYMBOLS):
            continue
        changes = {
            symbol: maps[symbol][when][1].close - maps[symbol][prior_time][1].close
            for symbol in SYMBOLS
        }
        for target in SYMBOLS:
            scores: dict[str, int] = defaultdict(int)
            counts: dict[str, int] = defaultdict(int)
            for other in SYMBOLS:
                if other != target:
                    currency_vote(other, changes[other], scores, counts)
            base_currency, quote_currency = PAIR_CURRENCIES[target]
            vote_count = counts[base_currency] + counts[quote_currency]
            if vote_count < rules["minimum_other_currency_votes"] or counts[base_currency] == 0 or counts[quote_currency] == 0:
                continue
            strength_spread = scores[base_currency] / counts[base_currency] - scores[quote_currency] / counts[quote_currency]
            if strength_spread >= rules["normalized_currency_strength_spread_min"]:
                direction = "LONG"
            elif strength_spread <= -rules["normalized_currency_strength_spread_min"]:
                direction = "SHORT"
            else:
                continue
            index, row = maps[target][when]
            bars = h1_by_symbol[target]
            atr = base.atr_before(bars, index)
            agrees = changes[target] > 0 if direction == "LONG" else changes[target] < 0
            if (
                atr is not None
                and abs(changes[target]) >= rules["target_change_atr_min"] * atr
                and agrees
                and base.body_ratio(row) >= rules["target_body_ratio_min"]
                and base.entry_exists(bars, index, "H1")
            ):
                output.append(signal("EXP-P9-MTF-312", target, "H1", direction, bars, index))
    return output


def frequency_result(strategy_id: str, raw: list[Signal], contract: dict) -> dict:
    return v1.frequency_result(strategy_id, raw, contract)


def validate_report(value: dict) -> None:
    if [row["strategy_id"] for row in value["strategy_results"]] != list(CANDIDATES):
        raise Batch3CountError("candidate result order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_frequency_pass"]]
    if value["frequency_pass_candidates"] != expected:
        raise Batch3CountError("passing candidate list mismatch")
    if value["return_calculated"] or value["research_outcomes_calculated"] or value["outcome_fields"]:
        raise Batch3CountError("outcome boundary violated")
    if value["persistent_price_files_after_cleanup"] != 0 or value["formal_phase9_authorization_effect"]:
        raise Batch3CountError("custody or formal boundary violated")
    if value["prior_candidate_rescue_performed"] or value["result_dependent_rule_change"]:
        raise Batch3CountError("research independence boundary violated")
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
        raise Batch3CountError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch3CountError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = load_contract(contract_path)
    base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    series = base.load_all_series(work_dir)
    raw: dict[str, list[Signal]] = {candidate: [] for candidate in CANDIDATES}
    h1_by_symbol = {symbol: series[(symbol, "H1")] for symbol in SYMBOLS}
    for symbol in SYMBOLS:
        raw["EXP-P9-MTF-309"].extend(scan_309(symbol, series[(symbol, "D1")], series[(symbol, "H4")], series[(symbol, "H1")], contract["candidates"]["EXP-P9-MTF-309"]))
        raw["EXP-P9-MTF-310"].extend(scan_310(symbol, series[(symbol, "H4")], series[(symbol, "M15")], contract["candidates"]["EXP-P9-MTF-310"]))
        raw["EXP-P9-MTF-311"].extend(scan_311(symbol, series[(symbol, "H1")], series[(symbol, "H4")], contract["candidates"]["EXP-P9-MTF-311"]))
    raw["EXP-P9-MTF-312"].extend(scan_312(h1_by_symbol, contract["candidates"]["EXP-P9-MTF-312"]))
    results = [frequency_result(candidate, raw[candidate], contract) for candidate in CANDIDATES]
    passing = [row["strategy_id"] for row in results if row["exploratory_frequency_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch3-count-only-result-v1.0.0",
        "status": "BLIND_MTF_BATCH3_COUNT_ONLY_COMPLETE_NO_OUTCOME",
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
        "prior_candidate_rescue_performed": False,
        "result_dependent_rule_change": False,
        "prior_outcome_tested_candidate_count": 3,
        "future_cumulative_multiplicity_required": True,
        "next_gate": "FREEZE_SEPARATE_CUMULATIVE_MULTIPLICITY_ADJUSTED_RETURN_OOS_GATE_FOR_FREQUENCY_PASSERS_ONLY" if passing else "NO_RETURN_GATE",
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
        raise Batch3CountError("exact batch3 Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch3CountError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
