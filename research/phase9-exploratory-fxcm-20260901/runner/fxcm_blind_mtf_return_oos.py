#!/usr/bin/env python3
"""One-shot spread-inclusive Return/OOS gate for blind MTF count passers."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import stat
import sys
from statistics import fmean, median


CONFIRMATION = "RUN_EXPLORATORY_FXCM_BLIND_MTF_RETURN_OOS_2017_2018_V1"
USAGE_CONFIRMATION = "I_CONFIRM_PERSONAL_NONCOMMERCIAL_USE_AND_ACCEPT_FXCM_EULA"
SELECTED = ("EXP-P9-MTF-302", "EXP-P9-MTF-304")
OUTPUT = "EXPLORATORY_FXCM_BLIND_MTF_RETURN_OOS.json"
ROOT = Path(__file__).resolve().parents[1]
BLIND_RUNNER = Path(__file__).with_name("fxcm_blind_mtf_count_only.py")
CANDIDATE_CONTRACT = ROOT / "spec/fxcm_blind_mtf_candidates_v1.frozen.json"
COUNT_RESULT = ROOT / "results/run-33580789080/EXPLORATORY_FXCM_BLIND_MTF_COUNT_ONLY.json"
COUNT_AUDIT = ROOT / "results/run-33580789080/BLIND_MTF_COUNT_INDEPENDENT_AUDIT.json"
CANONICAL_MTF = ROOT / "results/run-33508634314/artifact/EXPLORATORY_FXCM_MTF_QC.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


blind = load_module("fxcm_blind_mtf_return_base", BLIND_RUNNER)
SYMBOLS = blind.SYMBOLS


class ReturnGateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Outcome:
    strategy_id: str
    symbol: str
    direction: str
    entry_time: datetime
    r: float


def sha256_file(path: Path) -> str:
    return blind.sha256_file(path)


def load_json(path: Path) -> dict:
    return blind.base.load_json(path)


def validate_contract(path: Path) -> dict:
    value = load_json(path)
    if value.get("schema_version") != "phase9-exploratory-fxcm-blind-mtf-return-oos-v1.0.0":
        raise ReturnGateError("return contract schema mismatch")
    if value.get("status") != "FROZEN_AFTER_COUNT_BEFORE_FIRST_RETURN_OR_OUTCOME":
        raise ReturnGateError("return contract status mismatch")
    if tuple(value["selection_integrity"]["selected_candidates"]) != SELECTED:
        raise ReturnGateError("selected candidate mismatch")
    if value["selection_integrity"]["candidate_return_or_outcome_viewed_before_freeze"] is not False:
        raise ReturnGateError("prior outcome state mismatch")
    if value["split"] != {
        "assignment_key": "ENTRY_TIME_UTC_YEAR",
        "in_sample": "2017",
        "out_of_sample": "2018",
        "oos_used_for_rule_or_threshold_selection": False,
    }:
        raise ReturnGateError("split mismatch")
    expected = {
        "blind_candidate_contract_sha256": (CANDIDATE_CONTRACT, "8d832dbf779098d00c731d87547b30ed6944ee2c227d505e540ea95a7efaa1e3"),
        "blind_count_runner_sha256": (BLIND_RUNNER, "71e5f7a1cf6ea4a4566f7c6bc2d60463ec121a9e4ad33f54c8bd61cbceb1f323"),
        "count_result_sha256": (COUNT_RESULT, "d139955ce607b400c63c31de1f0e8d30269af28175932f0bcef2e9f4841e240a"),
        "count_independent_audit_sha256": (COUNT_AUDIT, "f3bc338f9f1f2f3b5e1c39636f85dc85d30481fdca282884b4289b6cb33b9ecd"),
        "canonical_mtf_report_sha256": (CANONICAL_MTF, "4d7f77caa5333e017742e01606aa869f3845aa4c4f206563e2fd59e02b1e1063"),
    }
    for key, (anchor_path, frozen_sha) in expected.items():
        if value["anchors"].get(key) != frozen_sha or sha256_file(anchor_path) != frozen_sha:
            raise ReturnGateError(f"anchor mismatch: {key}")
    count = load_json(COUNT_RESULT)
    audit = load_json(COUNT_AUDIT)
    if tuple(count.get("frequency_pass_candidates", [])) != SELECTED:
        raise ReturnGateError("count passer mismatch")
    if tuple(audit.get("frequency_pass_candidates", [])) != SELECTED:
        raise ReturnGateError("audit passer mismatch")
    if count.get("return_calculated") is not False or count.get("research_outcomes_calculated") is not False:
        raise ReturnGateError("count result already contains outcomes")
    return value


def read_side(path: Path) -> list[ExecutionBar]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != blind.base.utility.WORKING_HEADER:
            raise ReturnGateError("working side header mismatch")
        output = []
        previous = None
        for row in reader:
            timestamp = blind.base.parse_time(row["timestamp_utc"])
            if previous is not None and timestamp <= previous:
                raise ReturnGateError("side timestamps not strictly increasing")
            previous = timestamp
            values = [float(blind.base.utility.positive_decimal(row[field], field)) for field in ("open", "high", "low", "close")]
            bar = ExecutionBar(timestamp, *values)
            if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close, bar.high):
                raise ReturnGateError("invalid side OHLC geometry")
            output.append(bar)
    if not output:
        raise ReturnGateError("empty execution side")
    return output


def load_h1_execution(work_dir: Path) -> dict[tuple[str, str], list[ExecutionBar]]:
    direct = work_dir / "direct"
    if not direct.is_dir() or work_dir.is_symlink():
        raise ReturnGateError("invalid ephemeral execution tree")
    output = {}
    for symbol in SYMBOLS:
        bid = read_side(direct / f"{symbol}_H1_bid.csv")
        ask = read_side(direct / f"{symbol}_H1_ask.csv")
        if [row.timestamp for row in bid] != [row.timestamp for row in ask]:
            raise ReturnGateError(f"BID/ASK H1 timestamp mismatch: {symbol}")
        if any(a.open < b.open for b, a in zip(bid, ask)):
            raise ReturnGateError(f"crossed H1 open: {symbol}")
        output[(symbol, "BID")] = bid
        output[(symbol, "ASK")] = ask
    return output


def rebuild_locked_episodes(series: dict[tuple[str, str], list]) -> dict[str, list]:
    raw = {candidate: [] for candidate in SELECTED}
    candidate_contract = blind.load_contract(CANDIDATE_CONTRACT)
    for symbol in SYMBOLS:
        raw["EXP-P9-MTF-302"].extend(blind.scan_302(
            symbol, series[(symbol, "H4")], series[(symbol, "H1")],
            candidate_contract["candidates"]["EXP-P9-MTF-302"],
        ))
        raw["EXP-P9-MTF-304"].extend(blind.scan_304(
            symbol, series[(symbol, "H1")], series[(symbol, "H4")], series[(symbol, "D1")],
            candidate_contract["candidates"]["EXP-P9-MTF-304"],
        ))
    contract = load_json(ROOT / "spec/fxcm_blind_mtf_return_oos_v1.frozen.json")
    output = {}
    for candidate in SELECTED:
        episodes = blind.base.primary_episodes(blind.base.utility.collapse_overlaps(raw[candidate]))
        lock = contract["signal_identity_locks"][candidate]
        if len(episodes) != lock["primary_episode_count"] or blind.event_hash(episodes) != lock["primary_episode_identity_sha256"]:
            raise ReturnGateError(f"signal identity mismatch: {candidate}")
        output[candidate] = episodes
    return output


def compute_outcome(signal, mid: list, bid: list[ExecutionBar], ask: list[ExecutionBar], horizon_hours: int) -> Outcome | None:
    mid_index = {row.timestamp: index for index, row in enumerate(mid)}
    bid_map = {row.timestamp: row for row in bid}
    ask_map = {row.timestamp: row for row in ask}
    entry_index = mid_index.get(signal.entry_time)
    exit_time = signal.entry_time + timedelta(hours=horizon_hours)
    if entry_index is None or signal.entry_time not in bid_map or signal.entry_time not in ask_map:
        return None
    if exit_time not in bid_map or exit_time not in ask_map:
        return None
    atr = blind.base.atr_before(mid, entry_index)
    if atr is None or not math.isfinite(atr) or atr <= 0:
        return None
    if signal.direction == "LONG":
        pnl = bid_map[exit_time].open - ask_map[signal.entry_time].open
    elif signal.direction == "SHORT":
        pnl = bid_map[signal.entry_time].open - ask_map[exit_time].open
    else:
        raise ReturnGateError("unknown direction")
    value = pnl / atr
    if not math.isfinite(value):
        raise ReturnGateError("non-finite return")
    return Outcome(signal.strategy_id, signal.symbol, signal.direction, signal.entry_time, value)


def clustered_lower_bound(rows: list[Outcome], resamples: int, alpha: float, seed: int) -> float:
    groups: dict[date, list[float]] = defaultdict(list)
    for row in rows:
        groups[row.entry_time.date()].append(row.r)
    clusters = list(groups.values())
    if not clusters:
        raise ReturnGateError("empty bootstrap input")
    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        total = 0.0
        count = 0
        for _ in clusters:
            sample = clusters[rng.randrange(len(clusters))]
            total += sum(sample)
            count += len(sample)
        estimates.append(total / count)
    estimates.sort()
    index = max(0, min(len(estimates) - 1, math.floor(alpha * len(estimates))))
    return estimates[index]


def max_drawdown(rows: list[Outcome]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for row in sorted(rows, key=lambda value: (value.entry_time, value.symbol, value.direction)):
        cumulative += row.r
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def rounded(value: float) -> float:
    return round(value, 10)


def metrics(rows: list[Outcome]) -> dict:
    if not rows:
        raise ReturnGateError("empty outcome metrics")
    values = [row.r for row in rows]
    positives = sum(value for value in values if value > 0)
    negatives = -sum(value for value in values if value < 0)
    by_instrument = {symbol: [row.r for row in rows if row.symbol == symbol] for symbol in SYMBOLS}
    instrument_means = {symbol: (rounded(fmean(items)) if items else None) for symbol, items in by_instrument.items()}
    by_direction = {direction: [row.r for row in rows if row.direction == direction] for direction in ("LONG", "SHORT")}
    direction_means = {key: (rounded(fmean(items)) if items else None) for key, items in by_direction.items()}
    quarter_groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        quarter = (row.entry_time.month - 1) // 3 + 1
        quarter_groups[f"{row.entry_time.year}-Q{quarter}"].append(row.r)
    quarter_means = {key: rounded(fmean(quarter_groups[key])) for key in sorted(quarter_groups)}
    return {
        "outcome_count": len(rows),
        "mean_r": rounded(fmean(values)),
        "median_r": rounded(median(values)),
        "sum_r": rounded(sum(values)),
        "win_rate": rounded(sum(value > 0 for value in values) / len(values)),
        "profit_factor": rounded(positives / max(negatives, 1e-12)),
        "max_chronological_drawdown_r": rounded(max_drawdown(rows)),
        "means_by_instrument": instrument_means,
        "positive_instrument_count": sum(value is not None and value > 0 for value in instrument_means.values()),
        "means_by_direction": direction_means,
        "means_by_calendar_quarter": quarter_means,
        "positive_calendar_quarter_count": sum(value > 0 for value in quarter_means.values()),
    }


def outcome_identity(rows: list[Outcome]) -> str:
    payload = "".join(
        f"{row.strategy_id}\0{row.symbol}\0{row.direction}\0{blind.base.iso(row.entry_time)}\0{row.r:.17g}\n"
        for row in sorted(rows, key=lambda value: (value.entry_time, value.strategy_id, value.symbol, value.direction))
    )
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def evaluate(candidate: str, signals: list, mid_series: dict, execution: dict, contract: dict) -> dict:
    outcomes = []
    missing = 0
    horizon = contract["execution_model"]["fixed_horizon_hours"]
    for row in signals:
        outcome = compute_outcome(
            row, mid_series[(row.symbol, "H1")],
            execution[(row.symbol, "BID")], execution[(row.symbol, "ASK")], horizon,
        )
        if outcome is None:
            missing += 1
        else:
            outcomes.append(outcome)
    is_rows = [row for row in outcomes if row.entry_time.year == 2017]
    oos_rows = [row for row in outcomes if row.entry_time.year == 2018]
    if len(is_rows) + len(oos_rows) != len(outcomes):
        raise ReturnGateError("outcome outside frozen split")
    is_metrics = metrics(is_rows)
    oos_metrics = metrics(oos_rows)
    alpha = contract["inference"]["bonferroni_one_sided_alpha_each"]
    lower = clustered_lower_bound(
        oos_rows, contract["inference"]["bootstrap_resamples"], alpha,
        contract["inference"]["deterministic_seeds"][candidate],
    )
    gate = contract["candidate_pass_gate"]
    completion = len(outcomes) / len(signals)
    conditions = {
        "minimum_oos_outcomes": len(oos_rows) >= gate["minimum_oos_outcomes"],
        "minimum_outcome_completion_rate": completion >= gate["minimum_outcome_completion_rate"],
        "in_sample_mean_r_strictly_positive": is_metrics["mean_r"] > 0,
        "oos_mean_r_strictly_positive": oos_metrics["mean_r"] > 0,
        "oos_date_cluster_bootstrap_lower_bound_strictly_positive": lower > 0,
        "minimum_oos_profit_factor": oos_metrics["profit_factor"] >= gate["minimum_oos_profit_factor"],
        "minimum_positive_oos_instruments": oos_metrics["positive_instrument_count"] >= gate["minimum_positive_oos_instruments"],
        "minimum_positive_oos_calendar_quarters": oos_metrics["positive_calendar_quarter_count"] >= gate["minimum_positive_oos_calendar_quarters"],
    }
    return {
        "strategy_id": candidate,
        "locked_primary_episode_count": len(signals),
        "completed_outcome_count": len(outcomes),
        "missing_exact_exit_or_atr_count": missing,
        "outcome_completion_rate": rounded(completion),
        "outcome_identity_sha256": outcome_identity(outcomes),
        "in_sample_2017": is_metrics,
        "out_of_sample_2018": oos_metrics,
        "oos_date_cluster_bootstrap": {
            "resamples": contract["inference"]["bootstrap_resamples"],
            "one_sided_alpha": alpha,
            "lower_mean_r": rounded(lower),
            "seed": contract["inference"]["deterministic_seeds"][candidate],
        },
        "gate_conditions": conditions,
        "exploratory_edge_pass": all(conditions.values()),
        "formal_phase9_effect": False,
    }


def validate_report(value: dict) -> None:
    if [row["strategy_id"] for row in value["strategy_results"]] != list(SELECTED):
        raise ReturnGateError("result candidate order mismatch")
    expected = [row["strategy_id"] for row in value["strategy_results"] if row["exploratory_edge_pass"]]
    if value["exploratory_edge_pass_candidates"] != expected:
        raise ReturnGateError("edge passer list mismatch")
    if value["return_calculated"] is not True or value["research_outcomes_calculated"] is not True:
        raise ReturnGateError("outcome state mismatch")
    if value["persistent_price_files_after_cleanup"] != 0:
        raise ReturnGateError("price persistence mismatch")
    if value["trade_rows_in_artifact"] or value["price_values_in_artifact"] or value["signal_or_entry_timestamps_in_artifact"]:
        raise ReturnGateError("artifact disclosure boundary mismatch")
    if value["formal_phase9_authorization_effect"]:
        raise ReturnGateError("formal authorization changed")


def write_artifact(report_dir: Path, report: dict) -> None:
    if report_dir.exists() or report_dir.is_symlink():
        raise FileExistsError("report directory must be new")
    report_dir.mkdir(parents=True, mode=0o700)
    payload = report_dir / OUTPUT
    blind.base.write_new_json(payload, report)
    manifest = report_dir / "artifact_manifest_sha256.txt"
    manifest.write_text(f"{sha256_file(payload)}  {OUTPUT}\n", encoding="utf-8")
    if {path.name for path in report_dir.iterdir()} != {OUTPUT, "artifact_manifest_sha256.txt"}:
        raise ReturnGateError("artifact member mismatch")
    for path in report_dir.iterdir():
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ReturnGateError("artifact member type mismatch")


def run(contract_path: Path, current_mtf: Path, work_dir: Path, report_dir: Path) -> dict:
    contract = validate_contract(contract_path)
    blind.base.utility.validate_mtf_identity(current_mtf, CANONICAL_MTF)
    mid_series = blind.base.load_all_series(work_dir)
    execution = load_h1_execution(work_dir)
    episodes = rebuild_locked_episodes(mid_series)
    results = [evaluate(candidate, episodes[candidate], mid_series, execution, contract) for candidate in SELECTED]
    passing = [row["strategy_id"] for row in results if row["exploratory_edge_pass"]]
    report = {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-return-oos-result-v1.0.0",
        "status": "BLIND_MTF_RETURN_OOS_COMPLETE",
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
        raise ReturnGateError("exact Return/OOS confirmation required")
    if args.usage_confirmation != USAGE_CONFIRMATION:
        raise ReturnGateError("personal non-commercial FXCM EULA confirmation required")
    run(args.contract, args.current_mtf_report, args.work_dir, args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
