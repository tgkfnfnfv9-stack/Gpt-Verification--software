#!/usr/bin/env python3
"""Cumulative-multiplicity Return/OOS gate for Batch 5 Count passer 319."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH5_RETURN_OOS_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
SELECTED = ("EXP-P9-MTF-319",)
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH5_RETURN_OOS.json"
ROOT = Path(__file__).resolve().parents[1]
LEGACY_RETURN_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_return_oos.py")
BATCH5_COUNT_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only_v5.py")
CANDIDATE_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v5.frozen.json"
COUNT_RESULT = ROOT / "results/run-33607154053/EXPLORATORY_FXCM_BLIND_MTF_BATCH5_COUNT_ONLY.json"
COUNT_AUDIT = ROOT / "results/run-33607154053/BLIND_MTF_BATCH5_COUNT_ONLY_INDEPENDENT_AUDIT.json"
PRIOR_RETURN_RESULT = ROOT / "results/run-33604445976/EXPLORATORY_FXCM_BLIND_MTF_BATCH4_RETURN_OOS.json"
PRIOR_RETURN_AUDIT = ROOT / "results/run-33604445976/BLIND_MTF_BATCH4_RETURN_OOS_INDEPENDENT_AUDIT.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


legacy = load_module("fxcm_blind_mtf_batch5_return_legacy", LEGACY_RETURN_RUNNER)
batch5 = load_module("fxcm_blind_mtf_batch5_return_count", BATCH5_COUNT_RUNNER)
SYMBOLS = batch5.SYMBOLS
ExecutionBar = legacy.ExecutionBar
Outcome = legacy.Outcome


class Batch5ReturnGateError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return batch5.sha256_file(path)


def load_json(path: Path) -> dict:
    return batch5.base.load_json(path)


def validate_contract(path: Path) -> dict:
    value = load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-batch5-return-oos-v1.0.0":
        raise Batch5ReturnGateError("batch5 return contract schema mismatch")
    if value.get("status") != "FROZEN_AFTER_BATCH5_COUNT_BEFORE_FIRST_BATCH5_RETURN_OR_OUTCOME":
        raise Batch5ReturnGateError("batch5 return contract status mismatch")
    selection = value["selection_integrity"]
    if tuple(selection["selected_candidates"]) != SELECTED:
        raise Batch5ReturnGateError("selected candidate mismatch")
    if selection["candidate_return_or_outcome_viewed_before_freeze"] is not False:
        raise Batch5ReturnGateError("prior batch5 outcome state mismatch")
    if selection["nonpasser_rescue_allowed"] is not False:
        raise Batch5ReturnGateError("batch5 nonpasser rescue enabled")
    if tuple(selection["excluded_frequency_failures"]) != (
        "EXP-P9-MTF-317", "EXP-P9-MTF-318", "EXP-P9-MTF-320",
    ):
        raise Batch5ReturnGateError("frequency failure exclusion mismatch")
    if tuple(selection["prior_outcome_tested_rejections"]) != (
        "EXP-P9-MTF-302", "EXP-P9-MTF-304", "EXP-P9-MTF-305",
        "EXP-P9-MTF-311", "EXP-P9-MTF-312", "EXP-P9-MTF-316",
    ):
        raise Batch5ReturnGateError("prior outcome family mismatch")
    if selection["minimum_oos_outcomes_selected_from_count_only_not_outcome"] is not True:
        raise Batch5ReturnGateError("pre-outcome OOS minimum rationale missing")
    if value["candidate_pass_gate"]["minimum_oos_outcomes"] != 220:
        raise Batch5ReturnGateError("minimum OOS outcome gate mismatch")
    if value["split"] != {
        "assignment_key": "ENTRY_TIME_UTC_YEAR",
        "in_sample": "2017",
        "out_of_sample": "2018",
        "oos_used_for_rule_or_threshold_selection": False,
    }:
        raise Batch5ReturnGateError("split mismatch")
    inference = value["inference"]
    if inference["prior_outcome_tested_candidate_count"] != 6:
        raise Batch5ReturnGateError("prior multiplicity count mismatch")
    if inference["new_selected_candidate_count"] != 1:
        raise Batch5ReturnGateError("new multiplicity count mismatch")
    if inference["cumulative_outcome_tested_candidate_count"] != 7:
        raise Batch5ReturnGateError("cumulative multiplicity count mismatch")
    if inference["bonferroni_one_sided_alpha_each"] != 0.05 / 7:
        raise Batch5ReturnGateError("cumulative Bonferroni alpha mismatch")
    expected = {
        "batch5_candidate_contract_sha256": (CANDIDATE_CONTRACT, "88cffdcc16e058c09c6309f618d7eab1bb4558b6210469786c6bc40bc3bc0265"),
        "batch5_count_runner_sha256": (BATCH5_COUNT_RUNNER, "d1d9065085affd12708814156a8df485a542ef041d507e561eaad2864949aacc"),
        "batch5_count_result_sha256": (COUNT_RESULT, "f94a3c953fed409f0dc14bd40865770979223001fc4ceeb084cb672e39b9a1d3"),
        "batch5_count_independent_audit_sha256": (COUNT_AUDIT, "9470d9002cc4b4b6093774953119dd8984f2dc7a6ebd6b05f6486264b638cabb"),
        "prior_batch4_return_result_sha256": (PRIOR_RETURN_RESULT, "36cbee3076b35d0b9ea95f01c30e008f63e932ee883649c45a1497f8c1cd3d1d"),
        "prior_batch4_return_independent_audit_sha256": (PRIOR_RETURN_AUDIT, "13d72363defbb95e8c606b316d7a8e64390629452f2968b079e63968b190bd89"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
    }
    for key, (anchor_path, frozen_sha) in expected.items():
        if value["anchors"].get(key) != frozen_sha or sha256_file(anchor_path) != frozen_sha:
            raise Batch5ReturnGateError(f"anchor mismatch: {key}")
    count = load_json(COUNT_RESULT)
    audit = load_json(COUNT_AUDIT)
    prior_result = load_json(PRIOR_RETURN_RESULT)
    prior_audit = load_json(PRIOR_RETURN_AUDIT)
    if tuple(count.get("frequency_pass_candidates", [])) != SELECTED:
        raise Batch5ReturnGateError("batch5 Count passer mismatch")
    if tuple(audit.get("frequency_pass_candidates", [])) != SELECTED:
        raise Batch5ReturnGateError("batch5 audit passer mismatch")
    if count.get("return_calculated") is not False or count.get("research_outcomes_calculated") is not False:
        raise Batch5ReturnGateError("batch5 Count result already contains outcomes")
    if prior_result.get("cumulative_outcome_tested_candidate_count") != 6:
        raise Batch5ReturnGateError("latest prior outcome family mismatch")
    if prior_result.get("exploratory_edge_pass_candidates") != []:
        raise Batch5ReturnGateError("prior edge rejection state mismatch")
    if prior_audit.get("exploratory_edge_pass_candidates") != []:
        raise Batch5ReturnGateError("prior audit rejection state mismatch")
    return value


def rebuild_locked_episodes(series: dict[tuple[str, str], list], contract: dict) -> dict[str, list]:
    candidate_contract = batch5.load_contract(CANDIDATE_CONTRACT)
    h1_by_symbol = {symbol: series[(symbol, "H1")] for symbol in SYMBOLS}
    rules = candidate_contract["candidates"]["EXP-P9-MTF-319"]
    raw = []
    for symbol in SYMBOLS:
        raw.extend(batch5.scan_319(symbol, h1_by_symbol[symbol], rules))
    episodes = batch5.base.primary_episodes(batch5.base.utility.collapse_overlaps(raw))
    lock = contract["signal_identity_locks"]["EXP-P9-MTF-319"]
    if len(episodes) != lock["primary_episode_count"]:
        raise Batch5ReturnGateError("episode count identity mismatch: EXP-P9-MTF-319")
    if batch5.v4.v3.v1.event_hash(episodes) != lock["primary_episode_identity_sha256"]:
        raise Batch5ReturnGateError("episode hash identity mismatch: EXP-P9-MTF-319")
    return {"EXP-P9-MTF-319": episodes}


def validate_report(value: dict) -> None:
    if value["selected_candidates"] != list(SELECTED):
        raise Batch5ReturnGateError("result candidate order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_edge_pass"]]
    if value["exploratory_edge_pass_candidates"] != expected:
        raise Batch5ReturnGateError("edge passer list mismatch")
    if value["cumulative_outcome_tested_candidate_count"] != 7:
        raise Batch5ReturnGateError("report multiplicity mismatch")
    if value["bonferroni_one_sided_alpha_each"] != 0.05 / 7:
        raise Batch5ReturnGateError("report alpha mismatch")
    if value["return_calculated"] is not True or value["research_outcomes_calculated"] is not True:
        raise Batch5ReturnGateError("outcome state mismatch")
    if value["persistent_price_files_after_cleanup"] != 0:
        raise Batch5ReturnGateError("price persistence mismatch")
    if value["trade_rows_in_artifact"] or value["price_values_in_artifact"] or value["signal_or_entry_timestamps_in_artifact"]:
        raise Batch5ReturnGateError("artifact disclosure boundary mismatch")
    if value["formal_phase9_authorization_effect"]:
        raise Batch5ReturnGateError("formal authorization changed")
    if value["nonpasser_rescue_performed"] or value["result_dependent_rule_change"]:
        raise Batch5ReturnGateError("post-result rule change detected")


def write_artifact(report_dir: Path, report: dict) -> None:
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    payload = report_dir / OUTPUT
    batch5.base.write_new_json(payload, report)
    manifest = report_dir / "artifact_manifest_sha256.txt"
    manifest.write_text(f"{sha256_file(payload)}  {OUTPUT}\n", encoding="utf-8")
    if {path.name for path in report_dir.iterdir()} != {OUTPUT, "artifact_manifest_sha256.txt"}:
        raise Batch5ReturnGateError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch5ReturnGateError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = validate_contract(contract_path)
    batch5.base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    mid_series = batch5.base.load_all_series(work_dir)
    execution = legacy.load_h1_execution(work_dir)
    episodes = rebuild_locked_episodes(mid_series, contract)
    results = [legacy.evaluate(candidate, episodes[candidate], mid_series, execution, contract) for candidate in SELECTED]
    passing = [row["strategy_id"] for row in results if row["exploratory_edge_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch5-return-oos-result-v1.0.0",
        "status": "BLIND_MTF_BATCH5_RETURN_OOS_COMPLETE",
        "run_identity": {"run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"), "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"), "head_sha": os.getenv("GITHUB_SHA", "LOCAL")},
        "contract_sha256": sha256_file(contract_path),
        "count_result_sha256": sha256_file(COUNT_RESULT),
        "canonical_mtf_report_sha256": sha256_file(CANONICAL_MTF),
        "current_mtf_report_sha256": sha256_file(current_mtf),
        "selected_candidates": list(SELECTED),
        "prior_outcome_tested_candidates": ["EXP-P9-MTF-302", "EXP-P9-MTF-304", "EXP-P9-MTF-305", "EXP-P9-MTF-311", "EXP-P9-MTF-312", "EXP-P9-MTF-316"],
        "cumulative_outcome_tested_candidate_count": 7,
        "multiplicity_method": contract["inference"]["multiplicity_method"],
        "bonferroni_one_sided_alpha_each": contract["inference"]["bonferroni_one_sided_alpha_each"],
        "strategy_results": results,
        "exploratory_edge_pass_candidates": passing,
        "return_calculated": True,
        "research_outcomes_calculated": True,
        "outcome_fields": ["spread_inclusive_atr_normalized_return", "mean_r", "median_r", "sum_r", "win_rate", "profit_factor", "max_chronological_drawdown_r", "date_cluster_bootstrap_lower_mean_r"],
        "trade_rows_in_artifact": False,
        "price_values_in_artifact": False,
        "signal_or_entry_timestamps_in_artifact": False,
        "persistent_price_files_after_cleanup": 0,
        "formal_phase9_authorization_effect": False,
        "result_dependent_rule_change": False,
        "nonpasser_rescue_performed": False,
        "next_gate": "SEPARATE_ROBUSTNESS_AND_NEW_PERIOD_CONFIRMATION_FOR_EDGE_PASSERS_ONLY" if passing else "NO_CANDIDATE_FOR_ROBUSTNESS_GATE",
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
        raise Batch5ReturnGateError("exact Batch 5 Return/OOS confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch5ReturnGateError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
