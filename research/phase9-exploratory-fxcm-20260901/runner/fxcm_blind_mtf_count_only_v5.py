#!/usr/bin/env python3
"""Count-only screen for the independent fifth blind FX8 MTF batch."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import timedelta
import importlib.util
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH5_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
CANDIDATES = ("EXP-P9-MTF-317", "EXP-P9-MTF-318", "EXP-P9-MTF-319", "EXP-P9-MTF-320")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH5_COUNT_ONLY.json"
ROOT = Path(__file__).resolve().parents[1]
V4_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only_v4.py")
MTF_RUNNER = Path(__file__).with_name("fxcm_multitimeframe_qc.py")
BASE_UTILITY = Path(__file__).with_name("fxcm_single_pair_count_only.py")
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
PRIOR_CONTRACTS = tuple(ROOT / f"spec/fxcm_blind_mtf_candidates_v{i}.frozen.json" for i in range(1, 5))
LATEST_OUTCOME_AUDIT = ROOT / "results/run-33604445976/BLIND_MTF_BATCH4_RETURN_OOS_INDEPENDENT_AUDIT.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v4 = load_module("fxcm_blind_mtf_batch5_base", V4_RUNNER)
base = v4.base
Bar = base.Bar
Signal = base.Signal
SYMBOLS = base.SYMBOLS


class Batch5CountError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def load_contract(path: Path) -> dict:
    value = base.load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-candidates-v5.0.0":
        raise Batch5CountError("batch5 schema mismatch")
    if value.get("status") != "FROZEN_AFTER_BATCH4_REJECTION_BEFORE_FIRST_BATCH5_SIGNAL_COUNT":
        raise Batch5CountError("batch5 freeze status mismatch")
    if tuple(value.get("candidates", {})) != CANDIDATES:
        raise Batch5CountError("batch5 candidate order mismatch")
    if value["dataset"]["symbols"] != list(SYMBOLS):
        raise Batch5CountError("batch5 FX8 scope mismatch")
    integrity = value["selection_integrity"]
    if integrity["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"] is not False:
        raise Batch5CountError("prior candidate rescue enabled")
    if integrity["prior_outcomes_used_to_choose_batch5_thresholds"] is not False:
        raise Batch5CountError("prior outcomes used for Batch 5 rules")
    if integrity["batch5_count_or_outcome_viewed_before_freeze"] is not False:
        raise Batch5CountError("batch5 result viewed before freeze")
    if integrity["future_return_familywise_correction_must_include_prior_six_outcome_candidates"] is not True:
        raise Batch5CountError("future cumulative multiplicity boundary missing")
    if value["common_rules"]["forward_outcome_access"] is not False:
        raise Batch5CountError("forward outcome access enabled")
    expected = {
        "base_count_utility_sha256": (BASE_UTILITY, "2991575f471c19de35d04ae21d276cc25d52d9fb705587a8259f70d43639cdad"),
        "mtf_qc_runner_sha256": (MTF_RUNNER, "09da37be5955dcf142752d70dc21542f21e5ea71835c7f1073e68f52585971cd"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
        "batch1_candidate_contract_sha256": (PRIOR_CONTRACTS[0], "8d832dbf779098d00c731d87547b30ed6944ee2c227d505e540ea95a7efaa1e3"),
        "batch2_candidate_contract_sha256": (PRIOR_CONTRACTS[1], "4fac27599445d7dc28b7cffc99c8c6fdd19c640e2fb0fca1a90b9d5f799bc615"),
        "batch3_candidate_contract_sha256": (PRIOR_CONTRACTS[2], "54b73dcf66ced89abc9a33cc68689af7d3180ee7ed4c0db329ab49f24d7faa7e"),
        "batch4_candidate_contract_sha256": (PRIOR_CONTRACTS[3], "cc2c6ef49b8e8119f48406311d0cd8ba06803c063b92593425681dff7c7c63e9"),
        "latest_outcome_audit_sha256": (LATEST_OUTCOME_AUDIT, "13d72363defbb95e8c606b316d7a8e64390629452f2968b079e63968b190bd89"),
    }
    for key, (anchor_path, frozen) in expected.items():
        if value["anchors"].get(key) != frozen or sha256_file(anchor_path) != frozen:
            raise Batch5CountError(f"anchor mismatch: {key}")
    if set(value["mechanism_independence"]) != set(CANDIDATES):
        raise Batch5CountError("mechanism independence matrix mismatch")
    return value


def signal(strategy_id: str, symbol: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(strategy_id, symbol, "H1", direction, bars[index].timestamp + timedelta(hours=1), bars[index + 1].timestamp, 0)


def scan_317(symbol: str, h1: list[Bar], rules: dict) -> list[Signal]:
    by_date = defaultdict(dict)
    for index, row in enumerate(h1):
        by_date[row.timestamp.date()][row.timestamp.hour] = index
    output = []
    hours = rules["range_hours_utc"]
    for hour_map in by_date.values():
        if any(hour not in hour_map for hour in hours) or rules["confirmation_bar_open_hour_utc"] not in hour_map:
            continue
        index = hour_map[rules["confirmation_bar_open_hour_utc"]]
        if index < 15 or index + 1 >= len(h1) or not base.entry_exists(h1, index, "H1"):
            continue
        session = [h1[hour_map[hour]] for hour in hours]
        high, low = max(row.high for row in session), min(row.low for row in session)
        atr = base.atr_before(h1, index)
        if atr is None:
            continue
        margin = rules["close_beyond_range_atr_min"] * atr
        if h1[index].close >= high + margin:
            output.append(signal("EXP-P9-MTF-317", symbol, "LONG", h1, index))
        elif h1[index].close <= low - margin:
            output.append(signal("EXP-P9-MTF-317", symbol, "SHORT", h1, index))
    return output


def scan_318(symbol: str, d1: list[Bar], h1: list[Bar], rules: dict) -> list[Signal]:
    h1_map = {row.timestamp: index for index, row in enumerate(h1)}
    output = []
    for index in range(14, len(d1)):
        atr = base.atr_before(d1, index)
        row = d1[index]
        width = row.high - row.low
        if atr is None or width <= 0 or width < rules["range_atr_min"] * atr:
            continue
        location = (row.close - row.low) / width
        if location >= 1.0 - rules["extreme_close_fraction"]:
            direction = "LONG"
        elif location <= rules["extreme_close_fraction"]:
            direction = "SHORT"
        else:
            continue
        decision = row.timestamp + timedelta(days=1, hours=rules["fixed_entry_decision_hour_utc"])
        h1_index = h1_map.get(decision)
        if h1_index is not None and h1_index + 1 < len(h1) and base.entry_exists(h1, h1_index, "H1"):
            output.append(signal("EXP-P9-MTF-318", symbol, direction, h1, h1_index))
    return output


def scan_319(symbol: str, h1: list[Bar], rules: dict) -> list[Signal]:
    output = []
    window = rules["return_observations"]
    for index in range(max(15, window), len(h1) - 1):
        atr = base.atr_before(h1, index)
        if atr is None or atr <= 0:
            continue
        returns = [h1[pos].close - h1[pos - 1].close for pos in range(index - window + 1, index + 1)]
        upward = sum(value * value for value in returns if value > 0)
        downward = sum(value * value for value in returns if value < 0)
        net = sum(returns)
        if abs(net) < rules["minimum_total_atr_normalized_move"] * atr:
            continue
        floor = max((1e-12 * atr) ** 2, 1e-30)
        ratio = max(upward, downward) / max(min(upward, downward), floor)
        if ratio < rules["dominant_to_opposite_semivariance_ratio_min"]:
            continue
        direction = "SHORT" if upward > downward else "LONG"
        if base.entry_exists(h1, index, "H1"):
            output.append(signal("EXP-P9-MTF-319", symbol, direction, h1, index))
    return output


def scan_320(h1_by_symbol: dict[str, list[Bar]], rules: dict) -> list[Signal]:
    maps = {symbol: {row.timestamp: index for index, row in enumerate(rows)} for symbol, rows in h1_by_symbol.items()}
    common_times = set.intersection(*(set(value) for value in maps.values()))
    output = []
    lag = timedelta(hours=rules["lookback_hours"])
    for when in sorted(common_times):
        if when.hour != rules["fixed_decision_bar_open_hour_utc"]:
            continue
        scores = []
        valid = True
        for symbol in SYMBOLS:
            current_index = maps[symbol][when]
            past_index = maps[symbol].get(when - lag)
            bars = h1_by_symbol[symbol]
            atr = base.atr_before(bars, current_index)
            if past_index is None or atr is None or atr <= 0 or current_index + 1 >= len(bars):
                valid = False
                break
            scores.append(((bars[current_index].close - bars[past_index].close) / atr, symbol))
        if not valid:
            continue
        ranked = sorted(scores, key=lambda item: (item[0], item[1]))
        if ranked[-1][0] - ranked[0][0] < rules["dispersion_score_range_min"]:
            continue
        directions = {
            **{symbol: "LONG" for _, symbol in ranked[:rules["long_bottom_rank_count"]]},
            **{symbol: "SHORT" for _, symbol in ranked[-rules["short_top_rank_count"]:]},
        }
        for symbol, direction in directions.items():
            index = maps[symbol][when]
            if base.entry_exists(h1_by_symbol[symbol], index, "H1"):
                output.append(signal("EXP-P9-MTF-320", symbol, direction, h1_by_symbol[symbol], index))
    return output


def validate_report(value: dict) -> None:
    if [row["strategy_id"] for row in value["strategy_results"]] != list(CANDIDATES):
        raise Batch5CountError("candidate result order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_frequency_pass"]]
    if value["frequency_pass_candidates"] != expected:
        raise Batch5CountError("passing candidate list mismatch")
    if value["return_calculated"] or value["research_outcomes_calculated"] or value["outcome_fields"]:
        raise Batch5CountError("outcome boundary violated")
    if value["persistent_price_files_after_cleanup"] != 0 or value["formal_phase9_authorization_effect"]:
        raise Batch5CountError("custody or formal boundary violated")
    if value["prior_candidate_rescue_performed"] or value["result_dependent_rule_change"]:
        raise Batch5CountError("research independence boundary violated")
    if value["prior_outcome_tested_candidate_count"] != 6:
        raise Batch5CountError("prior multiplicity count mismatch")
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
        raise Batch5CountError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch5CountError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = load_contract(contract_path)
    base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    series = base.load_all_series(work_dir)
    raw = {candidate: [] for candidate in CANDIDATES}
    h1_by_symbol = {symbol: series[(symbol, "H1")] for symbol in SYMBOLS}
    for symbol in SYMBOLS:
        raw["EXP-P9-MTF-317"].extend(scan_317(symbol, h1_by_symbol[symbol], contract["candidates"]["EXP-P9-MTF-317"]))
        raw["EXP-P9-MTF-318"].extend(scan_318(symbol, series[(symbol, "D1")], h1_by_symbol[symbol], contract["candidates"]["EXP-P9-MTF-318"]))
        raw["EXP-P9-MTF-319"].extend(scan_319(symbol, h1_by_symbol[symbol], contract["candidates"]["EXP-P9-MTF-319"]))
    raw["EXP-P9-MTF-320"].extend(scan_320(h1_by_symbol, contract["candidates"]["EXP-P9-MTF-320"]))
    results = [v4.frequency_result(candidate, raw[candidate], contract) for candidate in CANDIDATES]
    passing = [row["strategy_id"] for row in results if row["exploratory_frequency_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch5-count-only-result-v1.0.0",
        "status": "BLIND_MTF_BATCH5_COUNT_ONLY_COMPLETE_NO_OUTCOME",
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
        "prior_outcome_tested_candidate_count": 6,
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
        raise Batch5CountError("exact Batch 5 Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch5CountError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
