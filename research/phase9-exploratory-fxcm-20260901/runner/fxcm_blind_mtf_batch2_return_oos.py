#!/usr/bin/env python3
"""Cumulative-multiplicity Return/OOS gate for batch2 Count passer 305."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH2_RETURN_OOS_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
SELECTED = ("EXP-P9-MTF-305",)
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH2_RETURN_OOS.json"
ROOT = Path(__file__).resolve().parents[1]
LEGACY_RETURN_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_return_oos.py")
BATCH2_COUNT_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only_v2.py")
CANDIDATE_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v2.frozen.json"
COUNT_RESULT = ROOT / "results/run-33585508306/EXPLORATORY_FXCM_BLIND_MTF_BATCH2_COUNT_ONLY.json"
COUNT_AUDIT = ROOT / "results/run-33585508306/BLIND_MTF_BATCH2_COUNT_ONLY_INDEPENDENT_AUDIT.json"
PRIOR_RETURN_RESULT = ROOT / "results/run-33582968006/EXPLORATORY_FXCM_BLIND_MTF_RETURN_OOS.json"
PRIOR_RETURN_AUDIT = ROOT / "results/run-33582968006/BLIND_MTF_RETURN_OOS_INDEPENDENT_AUDIT.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


legacy = load_module("fxcm_blind_mtf_batch2_return_legacy", LEGACY_RETURN_RUNNER)
batch2 = load_module("fxcm_blind_mtf_batch2_return_count", BATCH2_COUNT_RUNNER)
SYMBOLS = batch2.SYMBOLS
ExecutionBar = legacy.ExecutionBar
Outcome = legacy.Outcome


class Batch2ReturnGateError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return batch2.sha256_file(path)


def load_json(path: Path) -> dict:
    return batch2.base.load_json(path)


def validate_contract(path: Path) -> dict:
    value = load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-batch2-return-oos-v1.0.0":
        raise Batch2ReturnGateError("batch2 return contract schema mismatch")
    if value.get("status") != "FROZEN_AFTER_BATCH2_COUNT_BEFORE_FIRST_BATCH2_RETURN_OR_OUTCOME":
        raise Batch2ReturnGateError("batch2 return contract status mismatch")
    selection = value["selection_integrity"]
    if tuple(selection["selected_candidates"]) != SELECTED:
        raise Batch2ReturnGateError("selected candidate mismatch")
    if selection["candidate_return_or_outcome_viewed_before_freeze"] is not False:
        raise Batch2ReturnGateError("prior batch2 outcome state mismatch")
    if selection["nonpasser_rescue_allowed"] is not False:
        raise Batch2ReturnGateError("batch2 nonpasser rescue enabled")
    if tuple(selection["excluded_frequency_failures"]) != (
        "EXP-P9-MTF-306", "EXP-P9-MTF-307", "EXP-P9-MTF-308",
    ):
        raise Batch2ReturnGateError("frequency failure exclusion mismatch")
    if value["split"] != {
        "assignment_key": "ENTRY_TIME_UTC_YEAR",
        "in_sample": "2017",
        "out_of_sample": "2018",
        "oos_used_for_rule_or_threshold_selection": False,
    }:
        raise Batch2ReturnGateError("split mismatch")
    inference = value["inference"]
    if inference["prior_outcome_tested_candidate_count"] != 2:
        raise Batch2ReturnGateError("prior multiplicity count mismatch")
    if inference["new_selected_candidate_count"] != 1:
        raise Batch2ReturnGateError("new multiplicity count mismatch")
    if inference["cumulative_outcome_tested_candidate_count"] != 3:
        raise Batch2ReturnGateError("cumulative multiplicity count mismatch")
    if inference["bonferroni_one_sided_alpha_each"] != 0.05 / 3:
        raise Batch2ReturnGateError("cumulative Bonferroni alpha mismatch")
    expected = {
        "batch2_candidate_contract_sha256": (CANDIDATE_CONTRACT, "4fac27599445d7dc28b7cffc99c8c6fdd19c640e2fb0fca1a90b9d5f799bc615"),
        "batch2_count_runner_sha256": (BATCH2_COUNT_RUNNER, "f918a0590e2c7922d072553570a4aa44abbb0aa1ce01c606956e55fab7e9020c"),
        "batch2_count_result_sha256": (COUNT_RESULT, "941e0bb630059a5129e09221768853eaa9fcd01fa2118c512c0d129b24308e2f"),
        "batch2_count_independent_audit_sha256": (COUNT_AUDIT, "378bcabf9ffcee4d5fbcc1df01779d2afdfac5de0099713fbfd294726121d036"),
        "prior_return_result_sha256": (PRIOR_RETURN_RESULT, "4bb5005c7a3487a179c2ba30af6dac70443537d929628081baf9992dd6e1170e"),
        "prior_return_independent_audit_sha256": (PRIOR_RETURN_AUDIT, "29a04b2934374fe26e3bb3b8f08f26cac480cb869bc1864a67f015c3cc0b0478"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
    }
    for key, (anchor_path, frozen_sha) in expected.items():
        if value["anchors"].get(key) != frozen_sha or sha256_file(anchor_path) != frozen_sha:
            raise Batch2ReturnGateError(f"anchor mismatch: {key}")
    count = load_json(COUNT_RESULT)
    audit = load_json(COUNT_AUDIT)
    prior_result = load_json(PRIOR_RETURN_RESULT)
    prior_audit = load_json(PRIOR_RETURN_AUDIT)
    if tuple(count.get("frequency_pass_candidates", [])) != SELECTED:
        raise Batch2ReturnGateError("batch2 Count passer mismatch")
    if tuple(audit.get("frequency_pass_candidates", [])) != SELECTED:
        raise Batch2ReturnGateError("batch2 audit passer mismatch")
    if count.get("return_calculated") is not False or count.get("research_outcomes_calculated") is not False:
        raise Batch2ReturnGateError("batch2 Count result already contains outcomes")
    if prior_result.get("selected_candidates") != ["EXP-P9-MTF-302", "EXP-P9-MTF-304"]:
        raise Batch2ReturnGateError("prior outcome family mismatch")
    if prior_result.get("exploratory_edge_pass_candidates") != []:
        raise Batch2ReturnGateError("prior edge rejection state mismatch")
    if prior_audit.get("exploratory_edge_pass_candidates") != []:
        raise Batch2ReturnGateError("prior audit rejection state mismatch")
    return value


def rebuild_locked_episodes(series: dict[tuple[str, str], list], contract: dict) -> dict[str, list]:
    candidate_contract = batch2.load_contract(CANDIDATE_CONTRACT)
    raw = []
    for symbol in SYMBOLS:
        raw.extend(batch2.scan_305(
            symbol,
            series[(symbol, "H1")],
            series[(symbol, "H4")],
            series[(symbol, "D1")],
            candidate_contract["candidates"]["EXP-P9-MTF-305"],
        ))
    episodes = batch2.base.primary_episodes(batch2.base.utility.collapse_overlaps(raw))
    lock = contract["signal_identity_locks"]["EXP-P9-MTF-305"]
    if len(episodes) != lock["primary_episode_count"]:
        raise Batch2ReturnGateError("305 episode count identity mismatch")
    if batch2.v1.event_hash(episodes) != lock["primary_episode_identity_sha256"]:
        raise Batch2ReturnGateError("305 episode hash identity mismatch")
    return {"EXP-P9-MTF-305": episodes}


def validate_report(value: dict) -> None:
    if value["selected_candidates"] != list(SELECTED):
        raise Batch2ReturnGateError("result candidate order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_edge_pass"]]
    if value["exploratory_edge_pass_candidates"] != expected:
        raise Batch2ReturnGateError("edge passer list mismatch")
    if value["cumulative_outcome_tested_candidate_count"] != 3:
        raise Batch2ReturnGateError("report multiplicity mismatch")
    if value["return_calculated"] is not True or value["research_outcomes_calculated"] is not True:
        raise Batch2ReturnGateError("outcome state mismatch")
    if value["persistent_price_files_after_cleanup"] != 0:
        raise Batch2ReturnGateError("price persistence mismatch")
    if value["trade_rows_in_artifact"] or value["price_values_in_artifact"] or value["signal_or_entry_timestamps_in_artifact"]:
        raise Batch2ReturnGateError("artifact disclosure boundary mismatch")
    if value["formal_phase9_authorization_effect"]:
        raise Batch2ReturnGateError("formal authorization changed")


def write_artifact(report_dir: Path, report: dict) -> None:
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    payload = report_dir / OUTPUT
    batch2.base.write_new_json(payload, report)
    manifest = report_dir / "artifact_manifest_sha256.txt"
    manifest.write_text(f"{sha256_file(payload)}  {OUTPUT}\n", encoding="utf-8")
    if {path.name for path in report_dir.iterdir()} != {OUTPUT, "artifact_manifest_sha256.txt"}:
        raise Batch2ReturnGateError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch2ReturnGateError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = validate_contract(contract_path)
    batch2.base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    mid_series = batch2.base.load_all_series(work_dir)
    execution = legacy.load_h1_execution(work_dir)
    episodes = rebuild_locked_episodes(mid_series, contract)
    results = [legacy.evaluate(candidate, episodes[candidate], mid_series, execution, contract) for candidate in SELECTED]
    passing = [row["strategy_id"] for row in results if row["exploratory_edge_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch2-return-oos-result-v1.0.0",
        "status": "BLIND_MTF_BATCH2_RETURN_OOS_COMPLETE",
        "run_identity": {
            "run_id": os.getenv("GITHUB_RUN_ID", "LOCAL"),
            "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "LOCAL"),
            "head_sha": os.getenv("GITHUB_SHA", "LOCAL"),
        },
        "contract_sha256": sha256_file(contract_path),
        "count_result_sha256": sha256_file(COUNT_RESULT),
        "canonical_mtf_report_sha256": sha256_file(CANONICAL_MTF),
        "current_mtf_report_sha256": sha256_file(current_mtf),
        "selected_candidates": list(SELECTED),
        "prior_outcome_tested_candidates": ["EXP-P9-MTF-302", "EXP-P9-MTF-304"],
        "cumulative_outcome_tested_candidate_count": 3,
        "multiplicity_method": contract["inference"]["multiplicity_method"],
        "bonferroni_one_sided_alpha_each": contract["inference"]["bonferroni_one_sided_alpha_each"],
        "strategy_results": results,
        "exploratory_edge_pass_candidates": passing,
        "return_calculated": True,
        "research_outcomes_calculated": True,
        "outcome_fields": [
            "spread_inclusive_atr_normalized_return", "mean_r", "median_r", "sum_r",
            "win_rate", "profit_factor", "max_chronological_drawdown_r",
            "date_cluster_bootstrap_lower_mean_r",
        ],
        "trade_rows_in_artifact": False,
        "price_values_in_artifact": False,
        "signal_or_entry_timestamps_in_artifact": False,
        "persistent_price_files_after_cleanup": 0,
        "formal_phase9_authorization_effect": False,
        "result_dependent_rule_change": False,
        "nonpasser_rescue_performed": False,
        "next_gate": (
            "SEPARATE_ROBUSTNESS_AND_NEW_PERIOD_CONFIRMATION_FOR_EDGE_PASSERS_ONLY"
            if passing else "NO_CANDIDATE_FOR_ROBUSTNESS_GATE"
        ),
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
        raise Batch2ReturnGateError("exact batch2 Return/OOS confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch2ReturnGateError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
