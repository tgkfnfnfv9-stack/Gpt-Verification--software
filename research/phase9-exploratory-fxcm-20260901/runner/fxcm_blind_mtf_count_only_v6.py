#!/usr/bin/env python3
"""Count-only screen for the independent sixth blind FX8 MTF batch."""

from __future__ import annotations

import argparse
from datetime import timedelta
import importlib.util
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH6_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
CANDIDATES = ("EXP-P9-MTF-321", "EXP-P9-MTF-322", "EXP-P9-MTF-323", "EXP-P9-MTF-324")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH6_COUNT_ONLY.json"
ROOT = Path(__file__).resolve().parents[1]
V5_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only_v5.py")
MTF_RUNNER = Path(__file__).with_name("fxcm_multitimeframe_qc.py")
BASE_UTILITY = Path(__file__).with_name("fxcm_single_pair_count_only.py")
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
PRIOR_CONTRACTS = tuple(ROOT / f"spec/fxcm_blind_mtf_candidates_v{i}.frozen.json" for i in range(1, 6))
LATEST_OUTCOME_AUDIT = ROOT / "results/run-33610462879/BLIND_MTF_BATCH5_RETURN_OOS_INDEPENDENT_AUDIT.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v5 = load_module("fxcm_blind_mtf_batch6_base", V5_RUNNER)
base = v5.base
Bar = base.Bar
Signal = base.Signal
SYMBOLS = base.SYMBOLS


class Batch6CountError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def load_contract(path: Path) -> dict:
    value = base.load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-candidates-v6.0.0":
        raise Batch6CountError("batch6 schema mismatch")
    if value.get("status") != "FROZEN_AFTER_BATCH5_REJECTION_BEFORE_FIRST_BATCH6_SIGNAL_COUNT":
        raise Batch6CountError("batch6 freeze status mismatch")
    if tuple(value.get("candidates", {})) != CANDIDATES:
        raise Batch6CountError("batch6 candidate order mismatch")
    if value["dataset"]["symbols"] != list(SYMBOLS):
        raise Batch6CountError("batch6 FX8 scope mismatch")
    integrity = value["selection_integrity"]
    if integrity["prior_candidates_301_through_320_rescued"] is not False:
        raise Batch6CountError("prior candidate rescue enabled")
    if integrity["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"] is not False:
        raise Batch6CountError("prior candidate rule rescue enabled")
    if integrity["prior_outcomes_used_to_choose_batch6_rules_or_thresholds"] is not False:
        raise Batch6CountError("prior outcomes used for Batch 6 rules")
    if integrity["batch6_count_or_outcome_viewed_before_freeze"] is not False:
        raise Batch6CountError("batch6 result viewed before freeze")
    if integrity["frequency_thresholds_selected_from_opportunity_geometry_before_batch6_count"] is not True:
        raise Batch6CountError("pre-Count frequency rationale missing")
    if integrity["future_return_familywise_correction_must_include_prior_seven_outcome_candidates"] is not True:
        raise Batch6CountError("future cumulative multiplicity boundary missing")
    if value["common_rules"]["forward_outcome_access"] is not False:
        raise Batch6CountError("forward outcome access enabled")
    expected = {
        "base_count_utility_sha256": (BASE_UTILITY, "2991575f471c19de35d04ae21d276cc25d52d9fb705587a8259f70d43639cdad"),
        "mtf_qc_runner_sha256": (MTF_RUNNER, "09da37be5955dcf142752d70dc21542f21e5ea71835c7f1073e68f52585971cd"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
        "batch1_candidate_contract_sha256": (PRIOR_CONTRACTS[0], "8d832dbf779098d00c731d87547b30ed6944ee2c227d505e540ea95a7efaa1e3"),
        "batch2_candidate_contract_sha256": (PRIOR_CONTRACTS[1], "4fac27599445d7dc28b7cffc99c8c6fdd19c640e2fb0fca1a90b9d5f799bc615"),
        "batch3_candidate_contract_sha256": (PRIOR_CONTRACTS[2], "54b73dcf66ced89abc9a33cc68689af7d3180ee7ed4c0db329ab49f24d7faa7e"),
        "batch4_candidate_contract_sha256": (PRIOR_CONTRACTS[3], "cc2c6ef49b8e8119f48406311d0cd8ba06803c063b92593425681dff7c7c63e9"),
        "batch5_candidate_contract_sha256": (PRIOR_CONTRACTS[4], "88cffdcc16e058c09c6309f618d7eab1bb4558b6210469786c6bc40bc3bc0265"),
        "latest_outcome_audit_sha256": (LATEST_OUTCOME_AUDIT, "319c543cb1630622e46d4f759b856e080a4a1c5b26763475eeb575afc08d5545"),
    }
    for key, (anchor_path, frozen) in expected.items():
        if value["anchors"].get(key) != frozen or sha256_file(anchor_path) != frozen:
            raise Batch6CountError(f"anchor mismatch: {key}")
    if set(value["mechanism_independence"]) != set(CANDIDATES):
        raise Batch6CountError("mechanism independence matrix mismatch")
    latest = base.load_json(LATEST_OUTCOME_AUDIT)
    if latest.get("exploratory_edge_pass_candidates") != []:
        raise Batch6CountError("latest edge rejection state mismatch")
    if latest.get("outcome_tested_exploratory_candidate_count") != 7:
        raise Batch6CountError("prior outcome family mismatch")
    return value


def signal(strategy_id: str, symbol: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(strategy_id, symbol, "H1", direction, bars[index].timestamp + timedelta(hours=1), bars[index + 1].timestamp, 0)


def scan_321(symbol: str, h1: list[Bar], rules: dict) -> list[Signal]:
    output = []
    window = rules["return_observations"]
    for index in range(max(15, window), len(h1) - 1):
        atr = base.atr_before(h1, index)
        changes = [h1[pos].close - h1[pos - 1].close for pos in range(index - window + 1, index + 1)]
        net = sum(changes)
        path = sum(abs(value) for value in changes)
        if atr is None or atr <= 0 or path <= 0:
            continue
        if abs(net) < rules["minimum_net_atr_normalized_move"] * atr:
            continue
        if abs(net) / path < rules["path_efficiency_ratio_min"]:
            continue
        if base.entry_exists(h1, index, "H1"):
            output.append(signal("EXP-P9-MTF-321", symbol, "LONG" if net > 0 else "SHORT", h1, index))
    return output


def scan_322(symbol: str, h1: list[Bar], rules: dict) -> list[Signal]:
    output = []
    run_length = rules["consecutive_same_sign_changes"]
    for index in range(max(15, run_length + 1), len(h1) - 1):
        atr = base.atr_before(h1, index)
        changes = [h1[pos].close - h1[pos - 1].close for pos in range(index - run_length + 1, index + 1)]
        if atr is None or atr <= 0 or any(value == 0 for value in changes):
            continue
        positive = all(value > 0 for value in changes)
        negative = all(value < 0 for value in changes)
        if not (positive or negative) or abs(sum(changes)) < rules["minimum_run_atr_normalized_move"] * atr:
            continue
        previous = h1[index - run_length].close - h1[index - run_length - 1].close
        if (positive and previous > 0) or (negative and previous < 0):
            continue
        if base.entry_exists(h1, index, "H1"):
            output.append(signal("EXP-P9-MTF-322", symbol, "SHORT" if positive else "LONG", h1, index))
    return output


def scan_323(symbol: str, d1: list[Bar], h1: list[Bar], rules: dict) -> list[Signal]:
    h1_map = {row.timestamp: index for index, row in enumerate(h1)}
    output = []
    lookback = rules["completed_d1_lookback"]
    for index in range(lookback + 1, len(d1)):
        row = d1[index]
        previous = d1[index - 1]
        if (row.timestamp.year, row.timestamp.month) == (previous.timestamp.year, previous.timestamp.month):
            continue
        atr = base.atr_before(d1, index)
        displacement = previous.close - d1[index - 1 - lookback].close
        if atr is None or atr <= 0 or abs(displacement) < rules["minimum_prior_month_atr_normalized_move"] * atr:
            continue
        decision = row.timestamp + timedelta(hours=rules["fixed_entry_decision_hour_utc"])
        h1_index = h1_map.get(decision)
        if h1_index is not None and h1_index + 1 < len(h1) and base.entry_exists(h1, h1_index, "H1"):
            output.append(signal("EXP-P9-MTF-323", symbol, "LONG" if displacement > 0 else "SHORT", h1, h1_index))
    return output


def scan_324(symbol: str, h1: list[Bar], rules: dict) -> list[Signal]:
    maps = {row.timestamp: index for index, row in enumerate(h1)}
    output = []
    lag = timedelta(hours=rules["displacement_lookback_hours"])
    for index, row in enumerate(h1[:-1]):
        if row.timestamp.weekday() != rules["fixed_confirmation_weekday_utc"] or row.timestamp.hour != rules["fixed_confirmation_bar_open_hour_utc"]:
            continue
        past_index = maps.get(row.timestamp - lag)
        atr = base.atr_before(h1, index)
        if past_index is None or atr is None or atr <= 0:
            continue
        displacement = row.open - h1[past_index].open
        if abs(displacement) < rules["minimum_displacement_atr_normalized_move"] * atr:
            continue
        retrace = rules["same_bar_retrace_fraction_min"] * abs(displacement)
        if displacement > 0 and row.close <= row.open - retrace:
            direction = "SHORT"
        elif displacement < 0 and row.close >= row.open + retrace:
            direction = "LONG"
        else:
            continue
        if base.entry_exists(h1, index, "H1"):
            output.append(signal("EXP-P9-MTF-324", symbol, direction, h1, index))
    return output


def validate_report(value: dict) -> None:
    if [row["strategy_id"] for row in value["strategy_results"]] != list(CANDIDATES):
        raise Batch6CountError("candidate result order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_frequency_pass"]]
    if value["frequency_pass_candidates"] != expected:
        raise Batch6CountError("passing candidate list mismatch")
    if value["return_calculated"] or value["research_outcomes_calculated"] or value["outcome_fields"]:
        raise Batch6CountError("outcome boundary violated")
    if value["persistent_price_files_after_cleanup"] != 0 or value["formal_phase9_authorization_effect"]:
        raise Batch6CountError("custody or formal boundary violated")
    if value["prior_candidate_rescue_performed"] or value["result_dependent_rule_change"]:
        raise Batch6CountError("research independence boundary violated")
    if value["prior_outcome_tested_candidate_count"] != 7:
        raise Batch6CountError("prior multiplicity count mismatch")
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
        raise Batch6CountError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch6CountError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = load_contract(contract_path)
    base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    series = base.load_all_series(work_dir)
    raw = {candidate: [] for candidate in CANDIDATES}
    for symbol in SYMBOLS:
        h1 = series[(symbol, "H1")]
        raw["EXP-P9-MTF-321"].extend(scan_321(symbol, h1, contract["candidates"]["EXP-P9-MTF-321"]))
        raw["EXP-P9-MTF-322"].extend(scan_322(symbol, h1, contract["candidates"]["EXP-P9-MTF-322"]))
        raw["EXP-P9-MTF-323"].extend(scan_323(symbol, series[(symbol, "D1")], h1, contract["candidates"]["EXP-P9-MTF-323"]))
        raw["EXP-P9-MTF-324"].extend(scan_324(symbol, h1, contract["candidates"]["EXP-P9-MTF-324"]))
    results = [v5.v4.frequency_result(candidate, raw[candidate], contract) for candidate in CANDIDATES]
    passing = [row["strategy_id"] for row in results if row["exploratory_frequency_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch6-count-only-result-v1.0.0",
        "status": "BLIND_MTF_BATCH6_COUNT_ONLY_COMPLETE_NO_OUTCOME",
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
        "prior_outcome_tested_candidate_count": 7,
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
        raise Batch6CountError("exact Batch 6 Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch6CountError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
