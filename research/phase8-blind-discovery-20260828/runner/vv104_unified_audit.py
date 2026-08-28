#!/usr/bin/env python3
"""Final Discovery audit for STRAT-VV-104 with globally unified episodes.

All 15 frozen candidates are recomputed only to obtain valid BH-FDR p-values.
Only STRAT-VV-104 is eligible for a new decision. No candidate definition,
instrument, timeframe, split, or parameter is changed by this audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import blind_discovery as core


AUDIT_ID = "PHASE8_VV104_UNIFIED_EPISODE_FINAL_AUDIT"
TARGET_ID = "STRAT-VV-104"
FAMILIES = ("PRICE_ACTION", "VOLUME_VOLATILITY", "MARKET_REGIME_CROSS_MARKET")


def episode_map(rows: list[dict]) -> dict[tuple[str, str], float]:
    """One equal-weight value per UTC calendar-day and hypothetical side."""
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["dt"].date().isoformat(), row["side"])].append(row["edge_primary"])
    return {key: statistics.mean(values) for key, values in grouped.items()}


def episode_summary(rows: list[dict], seed_label: str) -> dict:
    values = list(episode_map(rows).values())
    if not values:
        return {
            "unique_episodes": 0,
            "episode_weighted_mean_edge_atr": None,
            "bootstrap_95ci": [None, None],
            "one_sided_p": None,
        }
    stats = core.cluster_stats(rows, seed_label)
    return stats


def combined_sensitivity(reports: dict[str, dict]) -> dict:
    combined = {}
    for variant in ("loose", "base", "strict"):
        count = sum(value[variant]["signals"] for value in reports.values())
        weighted_sum = sum(
            value[variant]["signals"] * value[variant]["raw_mean_return_atr"]
            for value in reports.values()
            if value[variant]["signals"] and value[variant]["raw_mean_return_atr"] is not None
        )
        combined[variant] = {
            "signals": count,
            "raw_mean_return_atr": weighted_sum / count if count else None,
        }
    base = combined["base"]["raw_mean_return_atr"]
    same_sign = []
    for variant in ("loose", "base", "strict"):
        value = combined[variant]["raw_mean_return_atr"]
        same_sign.append(value is not None and base is not None and value * base > 0)
    return {"joint_loose_base_strict": combined, "same_sign_ratio": sum(same_sign) / 3}


def summarize_partition(rows: list[dict]) -> dict:
    descriptive = core.aggregate_records(rows)
    return {
        "matched_signals": descriptive.get("matched_signals", 0),
        "signal_weighted_mean_edge_atr": descriptive.get("mean_edge_atr"),
        "episode_weighted_mean_edge_atr": core.episode_weighted_effect(rows),
        "future_return_mfe_mae": descriptive.get("horizons", {}),
    }


def leave_out_tests(rows: list[dict]) -> dict:
    full = episode_map(rows)

    def mean_without(predicate) -> float | None:
        values = episode_map([row for row in rows if predicate(row)])
        return statistics.mean(values.values()) if values else None

    by_market = {
        symbol: mean_without(lambda row, symbol=symbol: row["symbol"] != symbol)
        for symbol in sorted({row["symbol"] for row in rows})
    }
    by_timeframe = {
        timeframe: mean_without(lambda row, timeframe=timeframe: row["timeframe"] != timeframe)
        for timeframe in sorted({row["timeframe"] for row in rows})
    }
    by_year = {
        str(year): mean_without(lambda row, year=year: row["dt"].year != year)
        for year in sorted({row["dt"].year for row in rows})
    }
    ordered = sorted(full.items(), key=lambda item: abs(item[1]), reverse=True)
    one_percent = max(1, math.ceil(len(ordered) * 0.01)) if ordered else 0

    def trimmed(remove: int) -> float | None:
        values = [value for _, value in ordered[remove:]]
        return statistics.mean(values) if values else None

    return {
        "leave_one_market_out_edge_atr": by_market,
        "leave_one_timeframe_out_edge_atr": by_timeframe,
        "leave_one_year_out_edge_atr": by_year,
        "top_1_percent_absolute_episodes_removed_edge_atr": trimmed(one_percent),
        "top_5_absolute_episodes_removed_edge_atr": trimmed(min(5, len(ordered))),
    }


def final_decision(gates: dict[str, bool]) -> str:
    return "DEVELOPMENT" if all(gates.values()) else "REJECT_FOR_DEVELOPMENT"


def build_series(data_dir: Path) -> dict[tuple[str, str], core.Series]:
    result = {}
    for symbol in core.ALL_SYMBOLS:
        m15 = core.load_pair(data_dir, symbol, "M15")
        h1 = core.load_pair(data_dir, symbol, "H1")
        result[(symbol, "M15")] = core.build_series(symbol, "M15", m15)
        result[(symbol, "H1")] = core.build_series(symbol, "H1", h1)
        result[(symbol, "H4")] = core.build_series(symbol, "H4", core.aggregate(h1, 4))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    registry_path = Path(__file__).resolve().parents[1] / "spec" / "candidate_registry.json"
    registry_bytes = registry_path.read_bytes()
    registry = json.loads(registry_bytes)
    candidate_meta = {item["strategy_id"]: item for item in registry["candidates"]}
    assert len(candidate_meta) == 15 and TARGET_ID in candidate_meta

    series_map = build_series(args.data_dir)
    local_ids = [f"STRAT-PA-{n}" for n in range(101, 106)] + [f"STRAT-VV-{n}" for n in range(101, 106)]
    cross_ids = [f"STRAT-MR-{n}" for n in range(101, 106)]
    all_base_signals = []
    sensitivity: dict[str, dict[str, dict]] = {}
    raw_counts = {}

    for candidate_id in local_ids + cross_ids:
        sensitivity[candidate_id] = {}
        for level, variant in ((-1, "loose"), (0, "base"), (1, "strict")):
            signals = []
            for (symbol, timeframe), series in series_map.items():
                if timeframe not in candidate_meta[candidate_id]["timeframes"]:
                    continue
                if candidate_id in local_ids:
                    signals.extend(core.detect_local(candidate_id, series, level))
                else:
                    context = {sym: value for (sym, tf), value in series_map.items() if tf == timeframe}
                    signals.extend(core.detect_cross(candidate_id, series, context, level))
            returns = []
            for signal in signals:
                value = core.outcome(series_map[(signal.symbol, signal.timeframe)], signal)
                if value:
                    returns.append(value[core.PRIMARY]["return"])
            sensitivity[candidate_id][variant] = {
                "signals": len(returns),
                "raw_mean_return_atr": statistics.mean(returns) if returns else None,
            }
            if level == 0:
                all_base_signals.extend(signals)
                raw_counts[candidate_id] = len(returns)

    matched = core.control_pairs(all_base_signals, series_map)
    rows_by_candidate = {
        candidate_id: [row for row in matched if row["candidate_id"] == candidate_id]
        for candidate_id in candidate_meta
    }
    cluster_by_candidate = {
        candidate_id: episode_summary(rows, candidate_id + "|UNIFIED")
        for candidate_id, rows in rows_by_candidate.items()
    }
    adjusted = core.bh_adjust([
        (candidate_id, stats["one_sided_p"] if stats["one_sided_p"] is not None else 1.0)
        for candidate_id, stats in cluster_by_candidate.items()
    ])

    target_rows = rows_by_candidate[TARGET_ID]
    target_cluster = cluster_by_candidate[TARGET_ID]
    target_cluster["bh_fdr_adjusted_p"] = adjusted[TARGET_ID]
    overall = core.aggregate_records(target_rows)
    market_effects = {
        symbol: core.episode_weighted_effect([row for row in target_rows if row["symbol"] == symbol])
        for symbol in sorted({row["symbol"] for row in target_rows})
    }
    timeframe_effects = {
        timeframe: core.episode_weighted_effect([row for row in target_rows if row["timeframe"] == timeframe])
        for timeframe in sorted({row["timeframe"] for row in target_rows})
    }
    positive_market_ratio = sum(value > 0 for value in market_effects.values()) / len(market_effects)
    positive_timeframe_ratio = sum(value > 0 for value in timeframe_effects.values()) / len(timeframe_effects)
    sensitivity_result = combined_sensitivity({"ALL_TIMEFRAMES": sensitivity[TARGET_ID]})
    ci = target_cluster["bootstrap_95ci"]
    gates = {
        "matched_episodes_gte_100": target_cluster["unique_episodes"] >= 100,
        "primary_edge_atr_gte_0_05": target_cluster["episode_weighted_mean_edge_atr"] >= 0.05,
        "bootstrap_ci_lower_gt_0": ci[0] is not None and ci[0] > 0,
        "bh_fdr_lte_0_10": adjusted[TARGET_ID] <= 0.10,
        "positive_market_ratio_gte_0_60": positive_market_ratio >= 0.60,
        "positive_timeframe_ratio_gte_0_67": positive_timeframe_ratio >= 0.67,
        "sensitivity_same_sign_ratio_gte_0_67": sensitivity_result["same_sign_ratio"] >= 0.67,
    }
    decision = final_decision(gates)

    report = {
        "audit_id": AUDIT_ID,
        "strategy_id": TARGET_ID,
        "audit_scope": "FINAL_DISCOVERY_ACCOUNTING_AUDIT_ONLY",
        "evaluated_split": "DISCOVERY_ONLY",
        "evaluated_period": [core.DISCOVERY_START.isoformat(), core.DISCOVERY_END.isoformat()],
        "development_oos_final_holdout_accessed": False,
        "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
        "candidate_definition_changed": False,
        "instrument_or_timeframe_selection_changed": False,
        "selection_note": "All 15 frozen candidates were recomputed only for unified BH-FDR. Only STRAT-VV-104 receives a final decision.",
        "hypothesis": candidate_meta[TARGET_ID]["hypothesis"],
        "entry_conditions": candidate_meta[TARGET_ID]["entry_conditions"],
        "information_available_at_entry": registry["common_information_rule"],
        "targets": candidate_meta[TARGET_ID]["targets"],
        "registered_timeframes": candidate_meta[TARGET_ID]["timeframes"],
        "sample_size": {
            "raw_signals_with_primary_outcome": raw_counts[TARGET_ID],
            "matched_signals": overall.get("matched_signals", 0),
            "globally_unified_unique_episodes": target_cluster["unique_episodes"],
        },
        "episode_definition": "strategy_id + UTC calendar day + hypothetical side; all instruments and M15/H1/H4 share maximum total episode weight 1",
        "matched_control": "Same candidate/instrument/timeframe/split/hypothetical side/year/UTC4h; nearest prior-only ATR/trend/spread/volume deciles within +/-90d; 5 requested, 3 minimum, reuse cap 3.",
        "primary_clock_12h": overall,
        "globally_unified_cluster_inference": target_cluster,
        "future_return_mfe_mae": overall.get("horizons", {}),
        "by_year": {
            str(year): summarize_partition([row for row in target_rows if row["dt"].year == year])
            for year in sorted({row["dt"].year for row in target_rows})
        },
        "by_instrument": {
            symbol: summarize_partition([row for row in target_rows if row["symbol"] == symbol])
            for symbol in market_effects
        },
        "by_timeframe": {
            timeframe: summarize_partition([row for row in target_rows if row["timeframe"] == timeframe])
            for timeframe in timeframe_effects
        },
        "parameter_sensitivity": {
            "registered_grid": candidate_meta[TARGET_ID]["parameter_sensitivity"],
            **sensitivity_result,
        },
        "leave_out_robustness": leave_out_tests(target_rows),
        "decision_inputs": {
            "positive_market_ratio": positive_market_ratio,
            "positive_timeframe_ratio": positive_timeframe_ratio,
            "market_episode_edges_atr": market_effects,
            "timeframe_episode_edges_atr": timeframe_effects,
        },
        "multiplicity_reference": [
            {
                "strategy_id": candidate_id,
                "unified_one_sided_p": cluster_by_candidate[candidate_id]["one_sided_p"],
                "bh_fdr_adjusted_p": adjusted[candidate_id],
                "unified_episode_edge_atr": cluster_by_candidate[candidate_id]["episode_weighted_mean_edge_atr"],
                "unified_episodes": cluster_by_candidate[candidate_id]["unique_episodes"],
            }
            for candidate_id in candidate_meta
        ],
        "development_gates": gates,
        "failed_gates": [name for name, passed in gates.items() if not passed],
        "decision": decision,
        "decision_rule": "This is the one allowed final Discovery accounting audit. Failure of any frozen Development gate resolves WATCH to REJECT_FOR_DEVELOPMENT; no retuning or additional Discovery reuse.",
        "weaknesses": candidate_meta[TARGET_ID]["weaknesses"] + [
            "Dukascopy tick volume is not true centralized traded volume.",
            "This screen does not include OANDA-specific slippage, commission, swap, or CFD roll effects.",
        ],
        "data_manifest": {
            "series": [
                {
                    "symbol": series.symbol,
                    "timeframe": series.timeframe,
                    "rows": len(series.bars),
                    "first": series.bars[0].dt.isoformat(),
                    "last": series.bars[-1].dt.isoformat(),
                }
                for series in series_map.values()
            ]
        },
    }
    output = args.output_dir / "VV104_unified_episode_final_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "strategy_id": TARGET_ID,
        "matched_signals": report["sample_size"]["matched_signals"],
        "unified_episodes": report["sample_size"]["globally_unified_unique_episodes"],
        "edge_atr": target_cluster["episode_weighted_mean_edge_atr"],
        "ci": ci,
        "bh_fdr": adjusted[TARGET_ID],
        "failed_gates": report["failed_gates"],
        "decision": decision,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
