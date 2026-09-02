#!/usr/bin/env python3
"""Count-only screen for the independent fourth blind FX8 MTF batch."""

from __future__ import annotations

import argparse
import bisect
from collections import defaultdict
from datetime import timedelta
import importlib.util
import math
import os
from pathlib import Path
import stat
import sys


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_BATCH4_COUNT_ONLY_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
CANDIDATES = ("EXP-P9-MTF-313", "EXP-P9-MTF-314", "EXP-P9-MTF-315", "EXP-P9-MTF-316")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_BATCH4_COUNT_ONLY.json"
ROOT = Path(__file__).resolve().parents[1]
V3_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only_v3.py")
MTF_RUNNER = Path(__file__).with_name("fxcm_multitimeframe_qc.py")
BASE_UTILITY = Path(__file__).with_name("fxcm_single_pair_count_only.py")
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"
BATCH1_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v1.frozen.json"
BATCH2_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v2.frozen.json"
BATCH3_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v3.frozen.json"
LATEST_OUTCOME_AUDIT = ROOT / "results/run-33593743345/BLIND_MTF_BATCH3_RETURN_OOS_INDEPENDENT_AUDIT.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v3 = load_module("fxcm_blind_mtf_batch4_base", V3_RUNNER)
base = v3.base
Bar = base.Bar
Signal = base.Signal
SYMBOLS = base.SYMBOLS


class Batch4CountError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return base.sha256_file(path)


def load_contract(path: Path) -> dict:
    value = base.load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-candidates-v4.0.0":
        raise Batch4CountError("batch4 schema mismatch")
    if value.get("status") != "FROZEN_AFTER_BATCH3_REJECTION_BEFORE_FIRST_BATCH4_SIGNAL_COUNT":
        raise Batch4CountError("batch4 freeze status mismatch")
    if tuple(value.get("candidates", {})) != CANDIDATES:
        raise Batch4CountError("batch4 candidate order mismatch")
    if value["dataset"]["symbols"] != list(SYMBOLS):
        raise Batch4CountError("batch4 FX8 scope mismatch")
    integrity = value["selection_integrity"]
    if integrity["prior_threshold_direction_symbol_timeframe_or_exit_rescue_allowed"] is not False:
        raise Batch4CountError("prior candidate rescue enabled")
    if integrity["prior_outcomes_used_to_choose_batch4_thresholds"] is not False:
        raise Batch4CountError("prior outcomes used for Batch 4 rules")
    if integrity["batch4_count_or_outcome_viewed_before_freeze"] is not False:
        raise Batch4CountError("batch4 result viewed before freeze")
    if integrity["future_return_familywise_correction_must_include_prior_five_outcome_candidates"] is not True:
        raise Batch4CountError("future cumulative multiplicity boundary missing")
    if value["common_rules"]["forward_outcome_access"] is not False:
        raise Batch4CountError("forward outcome access enabled")
    if value["candidates"]["EXP-P9-MTF-315"]["ties"] != "BREAK_BY_ASCENDING_SYMBOL_NAME_AFTER_SCORE":
        raise Batch4CountError("315 tie rule mismatch")
    if len(value["candidates"]["EXP-P9-MTF-316"]["triangles"]) != 4:
        raise Batch4CountError("316 triangle inventory mismatch")
    expected = {
        "base_count_utility_sha256": (BASE_UTILITY, "2991575f471c19de35d04ae21d276cc25d52d9fb705587a8259f70d43639cdad"),
        "mtf_qc_runner_sha256": (MTF_RUNNER, "09da37be5955dcf142752d70dc21542f21e5ea71835c7f1073e68f52585971cd"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
        "batch1_candidate_contract_sha256": (BATCH1_CONTRACT, "8d832dbf779098d00c731d87547b30ed6944ee2c227d505e540ea95a7efaa1e3"),
        "batch2_candidate_contract_sha256": (BATCH2_CONTRACT, "4fac27599445d7dc28b7cffc99c8c6fdd19c640e2fb0fca1a90b9d5f799bc615"),
        "batch3_candidate_contract_sha256": (BATCH3_CONTRACT, "54b73dcf66ced89abc9a33cc68689af7d3180ee7ed4c0db329ab49f24d7faa7e"),
        "latest_outcome_audit_sha256": (LATEST_OUTCOME_AUDIT, "633f30c3bb621ce000605a0c985e3aa8698f08c4f8d5f912802c22d883766295"),
    }
    for key, (anchor_path, frozen) in expected.items():
        if value["anchors"].get(key) != frozen or sha256_file(anchor_path) != frozen:
            raise Batch4CountError(f"anchor mismatch: {key}")
    if set(value["mechanism_independence"]) != set(CANDIDATES):
        raise Batch4CountError("mechanism independence matrix mismatch")
    return value


def signal(strategy_id: str, symbol: str, direction: str, bars: list[Bar], index: int) -> Signal:
    return Signal(
        strategy_id, symbol, "H1", direction,
        bars[index].timestamp + timedelta(hours=1), bars[index + 1].timestamp, 0,
    )


def scan_313(symbol: str, h1: list[Bar], rules: dict) -> list[Signal]:
    output = []
    closure = timedelta(hours=rules["minimum_market_closure_hours"])
    for index in range(15, len(h1) - 1):
        row, prior = h1[index], h1[index - 1]
        if row.timestamp - prior.timestamp < closure:
            continue
        atr = base.atr_before(h1, index)
        if atr is None:
            continue
        gap = row.open - prior.close
        if abs(gap) < rules["opening_gap_atr_min"] * atr:
            continue
        direction = "SHORT" if gap > 0 else "LONG"
        retrace = row.open - row.close if direction == "SHORT" else row.close - row.open
        if (
            retrace >= rules["same_bar_gap_retrace_fraction_min"] * abs(gap)
            and base.entry_exists(h1, index, "H1")
        ):
            output.append(signal("EXP-P9-MTF-313", symbol, direction, h1, index))
    return output


def scan_314(symbol: str, h1: list[Bar], rules: dict) -> list[Signal]:
    last_date = {}
    for row in h1:
        key = (row.timestamp.year, row.timestamp.month)
        last_date[key] = max(last_date.get(key, row.timestamp.date()), row.timestamp.date())
    lookback = rules["displacement_lookback_hours"]
    output = []
    for index in range(max(15, lookback + 1), len(h1) - 1):
        row = h1[index]
        if row.timestamp.hour != rules["fixed_confirmation_bar_open_hour_utc"]:
            continue
        if row.timestamp.date() != last_date[(row.timestamp.year, row.timestamp.month)]:
            continue
        atr = base.atr_before(h1, index)
        displacement = h1[index - 1].close - h1[index - 1 - lookback].close
        if atr is None or abs(displacement) < rules["displacement_atr_min"] * atr:
            continue
        direction = "SHORT" if displacement > 0 else "LONG"
        retrace = row.open - row.close if direction == "SHORT" else row.close - row.open
        if (
            retrace >= rules["confirmation_retrace_fraction_min"] * abs(displacement)
            and base.entry_exists(h1, index, "H1")
        ):
            output.append(signal("EXP-P9-MTF-314", symbol, direction, h1, index))
    return output


def latest_completed_d1_index(d1: list[Bar], when) -> int:
    available = [row.timestamp + timedelta(days=1) for row in d1]
    return bisect.bisect_right(available, when) - 1


def scan_315(h1_by_symbol: dict[str, list[Bar]], d1_by_symbol: dict[str, list[Bar]], rules: dict) -> list[Signal]:
    h1_maps = {symbol: {row.timestamp: index for index, row in enumerate(rows)} for symbol, rows in h1_by_symbol.items()}
    common_times = set.intersection(*(set(value) for value in h1_maps.values()))
    output = []
    for when in sorted(common_times):
        if when.weekday() != rules["fixed_decision_weekday_utc"] or when.hour != rules["fixed_decision_bar_open_hour_utc"]:
            continue
        scores = []
        valid = True
        for symbol in SYMBOLS:
            d1 = d1_by_symbol[symbol]
            index = latest_completed_d1_index(d1, when)
            if index < max(14, rules["completed_d1_lookback"]) or index + 1 >= len(d1):
                valid = False
                break
            atr = base.atr_before(d1, index + 1)
            if atr is None or atr <= 0:
                valid = False
                break
            change = d1[index].close - d1[index - rules["completed_d1_lookback"]].close
            scores.append((change / atr, symbol))
        if not valid:
            continue
        ranked = sorted(scores, key=lambda item: (item[0], item[1]))
        directions = {
            **{symbol: "SHORT" for _, symbol in ranked[:rules["short_rank_count"]]},
            **{symbol: "LONG" for _, symbol in ranked[-rules["long_rank_count"]:]},
        }
        for symbol, direction in directions.items():
            index = h1_maps[symbol][when]
            bars = h1_by_symbol[symbol]
            if base.entry_exists(bars, index, "H1"):
                output.append(signal("EXP-P9-MTF-315", symbol, direction, bars, index))
    return output


def scan_316(h1_by_symbol: dict[str, list[Bar]], rules: dict) -> list[Signal]:
    maps = {symbol: {row.timestamp: (index, row) for index, row in enumerate(rows)} for symbol, rows in h1_by_symbol.items()}
    common_times = set.intersection(*(set(value) for value in maps.values()))
    histories: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    output = []
    window = rules["rolling_residual_observations"]
    for when in sorted(common_times):
        for triangle in rules["triangles"]:
            direct, leg1, leg2 = triangle["direct"], triangle["leg1"], triangle["leg2"]
            key = (direct, leg1, leg2)
            prices = (maps[direct][when][1].close, maps[leg1][when][1].close, maps[leg2][when][1].close)
            if any(value <= 0 for value in prices):
                raise Batch4CountError("nonpositive triangular price")
            residual = math.log(prices[0]) - math.log(prices[1]) - math.log(prices[2])
            history = histories[key]
            if len(history) >= window:
                sample = history[-window:]
                mean = sum(sample) / window
                variance = sum((value - mean) ** 2 for value in sample) / window
                std = math.sqrt(variance)
                if std >= rules["minimum_residual_standard_deviation"]:
                    zscore = (residual - mean) / std
                    if abs(zscore) >= rules["absolute_residual_zscore_min"]:
                        direct_direction = "SHORT" if zscore > 0 else "LONG"
                        leg_direction = "LONG" if zscore > 0 else "SHORT"
                        for symbol, direction in ((direct, direct_direction), (leg1, leg_direction), (leg2, leg_direction)):
                            index = maps[symbol][when][0]
                            bars = h1_by_symbol[symbol]
                            if base.entry_exists(bars, index, "H1"):
                                output.append(signal("EXP-P9-MTF-316", symbol, direction, bars, index))
            history.append(residual)
    return output


def frequency_result(strategy_id: str, raw: list[Signal], contract: dict) -> dict:
    return v3.frequency_result(strategy_id, raw, contract)


def validate_report(value: dict) -> None:
    if [row["strategy_id"] for row in value["strategy_results"]] != list(CANDIDATES):
        raise Batch4CountError("candidate result order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_frequency_pass"]]
    if value["frequency_pass_candidates"] != expected:
        raise Batch4CountError("passing candidate list mismatch")
    if value["return_calculated"] or value["research_outcomes_calculated"] or value["outcome_fields"]:
        raise Batch4CountError("outcome boundary violated")
    if value["persistent_price_files_after_cleanup"] != 0 or value["formal_phase9_authorization_effect"]:
        raise Batch4CountError("custody or formal boundary violated")
    if value["prior_candidate_rescue_performed"] or value["result_dependent_rule_change"]:
        raise Batch4CountError("research independence boundary violated")
    if value["prior_outcome_tested_candidate_count"] != 5:
        raise Batch4CountError("prior multiplicity count mismatch")
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
        raise Batch4CountError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Batch4CountError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = load_contract(contract_path)
    base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    series = base.load_all_series(work_dir)
    raw: dict[str, list[Signal]] = {candidate: [] for candidate in CANDIDATES}
    h1_by_symbol = {symbol: series[(symbol, "H1")] for symbol in SYMBOLS}
    d1_by_symbol = {symbol: series[(symbol, "D1")] for symbol in SYMBOLS}
    for symbol in SYMBOLS:
        raw["EXP-P9-MTF-313"].extend(scan_313(symbol, h1_by_symbol[symbol], contract["candidates"]["EXP-P9-MTF-313"]))
        raw["EXP-P9-MTF-314"].extend(scan_314(symbol, h1_by_symbol[symbol], contract["candidates"]["EXP-P9-MTF-314"]))
    raw["EXP-P9-MTF-315"].extend(scan_315(h1_by_symbol, d1_by_symbol, contract["candidates"]["EXP-P9-MTF-315"]))
    raw["EXP-P9-MTF-316"].extend(scan_316(h1_by_symbol, contract["candidates"]["EXP-P9-MTF-316"]))
    results = [frequency_result(candidate, raw[candidate], contract) for candidate in CANDIDATES]
    passing = [row["strategy_id"] for row in results if row["exploratory_frequency_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch4-count-only-result-v1.0.0",
        "status": "BLIND_MTF_BATCH4_COUNT_ONLY_COMPLETE_NO_OUTCOME",
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
        "prior_outcome_tested_candidate_count": 5,
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
        raise Batch4CountError("exact Batch 4 Count-only confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise Batch4CountError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
