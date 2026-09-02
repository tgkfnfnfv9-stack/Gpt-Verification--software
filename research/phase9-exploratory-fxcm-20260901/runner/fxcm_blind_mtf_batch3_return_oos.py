#!/usr/bin/env python3
"""Cumulative-multiplicity Return/OOS gate for Batch 3 Count passers 311/312."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH3_RETURN_OOS_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
SELECTED = ("EXP-P9-MTF-311", "EXP-P9-MTF-312")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH3_RETURN_OOS.json"
ROOT = Path(__file__).resolve().parents[1]
LEGACY_RETURN_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_return_oos.py")
BATCH3_COUNT_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only_v3.py")
CANDIDATE_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v3.frozen.json"
COUNT_RESULT = ROOT / "results/run-33591731464/EXPLORATORY_FXCM_BLIND_MTF_BATCH3_COUNT_ONLY.json"
COUNT_AUDIT = ROOT / "results/run-33591731464/BLIND_MTF_BATCH3_COUNT_ONLY_INDEPENDENT_AUDIT.json"
PRIOR_RETURN_RESULT = ROOT / "results/run-33587536789/EXPLORATORY_FXCM_BLIND_MTF_BATCH2_RETURN_OOS.json"
PRIOR_RETURN_AUDIT = ROOT / "results/run-33587536789/BLIND_MTF_BATCH2_RETURN_OOS_INDEPENDENT_AUDIT.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


legacy = load_module("fxcm_blind_mtf_batch3_return_legacy", LEGACY_RETURN_RUNNER)
batch3 = load_module("fxcm_blind_mtf_batch3_return_count", BATCH3_COUNT_RUNNER)
SYMBOLS = batch3.SYMBOLS
ExecutionBar = legacy.ExecutionBar
Outcome = legacy.Outcome


class Batch3ReturnGateError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return batch3.sha256_file(path)


def load_json(path: Path) -> dict:
    return batch3.base.load_json(path)


def validate_contract(path: Path) -> dict:
    value = load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-batch3-return-oos-v1.0.0":
        raise Batch3ReturnGateError("batch3 return contract schema mismatch")
    if value.get("status") != "FROZEN_AFTER_BATCH3_COUNT_BEFORE_FIRST_BATCH3_RETURN_OR_OUTCOME":
        raise Batch3ReturnGateError("batch3 return contract status mismatch")
    selection = value["selection_integrity"]
    if tuple(selection["selected_candidates"]) != SELECTED:
        raise Batch3ReturnGateError("selected candidate mismatch")
    if selection["candidate_return_or_outcome_viewed_before_freeze"] is not False:
        raise Batch3ReturnGateError("prior batch3 outcome state mismatch")
    if selection["nonpasser_rescue_allowed"] is not False:
        raise Batch3ReturnGateError("batch3 nonpasser rescue enabled")
    if tuple(selection["excluded_frequency_failures"]) != ("EXP-P9-MTF-309", "EXP-P9-MTF-310"):
        raise Batch3ReturnGateError("frequency failure exclusion mismatch")
    if tuple(selection["prior_outcome_tested_rejections"]) != (
        "EXP-P9-MTF-302", "EXP-P9-MTF-304", "EXP-P9-MTF-305",
    ):
        raise Batch3ReturnGateError("prior outcome family mismatch")
    if selection["minimum_oos_outcomes_selected_from_count_only_not_outcome"] is not True:
        raise Batch3ReturnGateError("pre-outcome OOS minimum rationale missing")
    if value["candidate_pass_gate"]["minimum_oos_outcomes"] != 120:
        raise Batch3ReturnGateError("minimum OOS outcome gate mismatch")
    if value["split"] != {
        "assignment_key": "ENTRY_TIME_UTC_YEAR",
        "in_sample": "2017",
        "out_of_sample": "2018",
        "oos_used_for_rule_or_threshold_selection": False,
    }:
        raise Batch3ReturnGateError("split mismatch")
    inference = value["inference"]
    if inference["prior_outcome_tested_candidate_count"] != 3:
        raise Batch3ReturnGateError("prior multiplicity count mismatch")
    if inference["new_selected_candidate_count"] != 2:
        raise Batch3ReturnGateError("new multiplicity count mismatch")
    if inference["cumulative_outcome_tested_candidate_count"] != 5:
        raise Batch3ReturnGateError("cumulative multiplicity count mismatch")
    if inference["bonferroni_one_sided_alpha_each"] != 0.05 / 5:
        raise Batch3ReturnGateError("cumulative Bonferroni alpha mismatch")
    expected = {
        "batch3_candidate_contract_sha256": (CANDIDATE_CONTRACT, "54b73dcf66ced89abc9a33cc68689af7d3180ee7ed4c0db329ab49f24d7faa7e"),
        "batch3_count_runner_sha256": (BATCH3_COUNT_RUNNER, "86d5ef07bf634c506bc99f126183a4b0758d29088bb482e0245fbb10b9bda81b"),
        "batch3_count_result_sha256": (COUNT_RESULT, "f6ed510f3e22f08f89d7a732fe6d898d3af082bb3320d3b430afc24787115523"),
        "batch3_count_independent_audit_sha256": (COUNT_AUDIT, "1ac90bdacd5323946d6e55e3bb0fc079f091a072fcf96fc7ba89e948398a330d"),
        "prior_batch2_return_result_sha256": (PRIOR_RETURN_RESULT, "c2aa059958fb1d85858a337772f5c92717649b5d86745485887bd688c2fd1d07"),
        "prior_batch2_return_independent_audit_sha256": (PRIOR_RETURN_AUDIT, "83f136d8ef8ffb50bda9f92edd3a7cccb4c0b2aa4f783572147371cba56290e0"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
    }
    for key, (anchor_path, frozen_sha) in expected.items():
        if value["anchors"].get(key) != frozen_sha or sha256_file(anchor_path) != frozen_sha:
            raise Batch3ReturnGateError(f"anchor mismatch: {key}")
    count = load_json(COUNT_RESULT)
    audit = load_json(COUNT_AUDIT)
    prior_result = load_json(PRIOR_RETURN_RESULT)
    prior_audit = load_json(PRIOR_RETURN_AUDIT)
    if tuple(count.get("frequency_pass_candidates", [])) != SELECTED:
        raise Batch3ReturnGateError("batch3 Count passer mismatch")
    if tuple(audit.get("frequency_pass_candidates", [])) != SELECTED:
        raise Batch3ReturnGateError("batch3 audit passer mismatch")
    if count.get("return_calculated") is not False or count.get("research_outcomes_calculated") is not False:
        raise Batch3ReturnGateError("batch3 Count result already contains outcomes")
    if prior_result.get("selected_candidates") != ["EXP-P9-MTF-305"]:
        raise Batch3ReturnGateError("latest prior result mismatch")
    if prior_result.get("exploratory_edge_pass_candidates") != []:
        raise Batch3ReturnGateError("prior edge rejection state mismatch")
    state = prior_audit.get("research_state", {})
    if state.get("outcome_tested_exploratory_candidate_count") != 3:
        raise Batch3ReturnGateError("prior tested family count mismatch")
    if prior_audit.get("exploratory_edge_pass_candidates") != []:
        raise Batch3ReturnGateError("prior audit rejection state mismatch")
    return value


def rebuild_locked_episodes(series: dict[tuple[str, str], list], contract: dict) -> dict[str, list]:
    candidate_contract = batch3.load_contract(CANDIDATE_CONTRACT)
    raw = {candidate: [] for candidate in SELECTED}
    h1_by_symbol = {symbol: series[(symbol, "H1")] for symbol in SYMBOLS}
    for symbol in SYMBOLS:
        raw["EXP-P9-MTF-311"].extend(batch3.scan_311(
            symbol,
            series[(symbol, "H1")],
            series[(symbol, "H4")],
            candidate_contract["candidates"]["EXP-P9-MTF-311"],
        ))
    raw["EXP-P9-MTF-312"].extend(batch3.scan_312(
        h1_by_symbol,
        candidate_contract["candidates"]["EXP-P9-MTF-312"],
    ))
    output = {}
    for candidate in SELECTED:
        episodes = batch3.base.primary_episodes(batch3.base.utility.collapse_overlaps(raw[candidate]))
        lock = contract["signal_identity_locks"][candidate]
        if len(episodes) != lock["primary_episode_count"]:
            raise Batch3ReturnGateError(f"episode count identity mismatch: {candidate}")
        if batch3.v1.event_hash(episodes) != lock["primary_episode_identity_sha256"]:
            raise Batch3ReturnGateError(f"episode hash identity mismatch: {candidate}")
        output[candidate] = episodes
    return output


def validate_report(value: dict) -> None:
    if value["selected_candidates"] != list(SELECTED):
        raise Batch3ReturnGateError("result candidate order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_edge_pass"]]
    if value["exploratory_edge_pass_candidates"] != expected:
        raise Batch3ReturnGateError("edge passer list mismatch")
    if value["cumulative_outcome_tested_candidate_count"] != 5:
        raise Batch3ReturnGateError("report multiplicity mismatch")
    if value["bonferroni_one_sided_alpha_each"] != 0.01:
        raise Batch3ReturnGateError("report alpha mismatch")
    if value["return_calculated"] is not True or value["research_outcomes_calculated"] is not True:
        raise Batch3ReturnGateError("outcome state mismatch")
    if value["persistent_price_files_after_cleanup"] != 0:
        raise Batch3ReturnGateError("price persistence mismatch")
    if value["trade_rows_in_artifact"] or value["price_values_in_artifact"] or value["signal_or_entry_timestamps_in_artifact"]:
        raise Batch3ReturnGateError("artifact disclosure boundary mismatch")
    if value["formal_phase9_authorization_effect"]:
        raise Batch3ReturnGateError("formal authorization changed")
    if value["nonpasser_rescue_performed"] or value["result_dependent_rule_change"]:
        raise Batch3ReturnGateError("post-result rule change detected")


def write_artifact(report_dir: Path, report: dict) -> None:
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    payload = report_dir / OUTPUT
    batch3.base.write_new_json(payload, report)
    manifest = report_dir / "artifact_manifest_sha256.txt"
    manifest.write_text(f"{sha256_file(payload)}  {OUTPUT}\n", encoding="utf-8")
    if {path.name for path in report_dir.iterdir()} != {OUTPUT, "artifact_manifest_sha256.txt"}:
        raise Batch3ReturnGateError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch3ReturnGateError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = validate_contract(contract_path)
    batch3.base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    mid_series = batch3.base.load_all_series(work_dir)
    execution = legacy.load_h1_execution(work_dir)
    episodes = rebuild_locked_episodes(mid_series, contract)
    results = [legacy.evaluate(candidate, episodes[candidate], mid_series, execution, contract) for candidate in SELECTED]
    passing = [row["strategy_id"] for row in results if row["exploratory_edge_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch3-return-oos-result-v1.0.0",
        "status": "BLIND_MTF_BATCH3_RETURN_OOS_COMPLETE",
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
        "prior_outcome_tested_candidates": ["EXP-P9-MTF-302", "EXP-P9-MTF-304", "EXP-P9-MTF-305"],
        "cumulative_outcome_tested_candidate_count": 5,
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
        raise Batch3ReturnGateError("exact Batch 3 Return/OOS confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch3ReturnGateError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
