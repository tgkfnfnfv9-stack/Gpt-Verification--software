#!/usr/bin/env python3
"""Merge the frozen M15 and H1/H4 Discovery summaries without cherry-picking a timeframe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FAMILIES = ("PRICE_ACTION", "VOLUME_VOLATILITY", "MARKET_REGIME_CROSS_MARKET")


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["evaluated_split"] == "DISCOVERY_ONLY"
    assert value["development_oos_final_holdout_accessed"] is False
    assert len(value["candidates"]) == 15
    return value


def compact(candidate: dict) -> dict:
    return {
        "sample_size": candidate["sample_size"],
        "primary_clock_12h": candidate["primary_clock_12h"],
        "cluster_inference": candidate["cluster_inference"],
        "future_return_mfe_mae": candidate["future_return_mfe_mae"],
        "by_year": candidate["by_year"],
        "by_instrument": candidate["by_instrument"],
        "by_timeframe": candidate["by_timeframe"],
        "parameter_sensitivity": candidate["parameter_sensitivity"],
        "runner_decision": candidate["decision"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m15", type=Path, required=True)
    parser.add_argument("--h1h4", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()

    m15 = load(args.m15)
    h1h4 = load(args.h1h4)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    registered = {item["strategy_id"]: item for item in registry["candidates"]}
    m15_by_id = {item["strategy_id"]: item for item in m15["candidates"]}
    h1h4_by_id = {item["strategy_id"]: item for item in h1h4["candidates"]}
    assert set(registered) == set(m15_by_id) == set(h1h4_by_id)

    merged = []
    for strategy_id, meta in registered.items():
        subruns = {"M15": compact(m15_by_id[strategy_id]), "H1_H4": compact(h1h4_by_id[strategy_id])}
        edges = {
            name: value["cluster_inference"]["episode_weighted_mean_edge_atr"]
            for name, value in subruns.items()
        }
        episodes = {name: value["sample_size"]["unique_episodes"] for name, value in subruns.items()}
        positive_both = all(value is not None and value > 0 for value in edges.values())
        enough_both = all(value >= 50 for value in episodes.values())
        development_both = all(value["runner_decision"] == "DEVELOPMENT" for value in subruns.values())
        if development_both:
            decision = "DEVELOPMENT"
            reasons = ["Both M15 and H1/H4 independently passed the frozen core statistical gate."]
        elif positive_both and enough_both:
            decision = "WATCH"
            reasons = [
                "Episode-weighted mean edge is positive in both M15 and H1/H4 strata.",
                "At least one stratum fails positive 95% CI and/or BH-FDR; no Development promotion.",
            ]
        else:
            decision = "REJECT"
            reasons = ["Cross-timeframe sign/sample gate failed; selecting only the favorable timeframe is prohibited."]
        rank_score = min(edges.values()) if all(value is not None for value in edges.values()) else None
        merged.append({
            "strategy_id": strategy_id,
            "family": meta["family"],
            "hypothesis": meta["hypothesis"],
            "entry_conditions": meta["entry_conditions"],
            "information_available_at_entry": registry["common_information_rule"],
            "targets": meta["targets"],
            "registered_timeframes": meta["timeframes"],
            "sample_size": {
                "M15": subruns["M15"]["sample_size"],
                "H1_H4": subruns["H1_H4"]["sample_size"],
                "cross_stratum_unique_episodes": "NOT_ADDITIVE_BECAUSE_DATES_OVERLAP",
            },
            "matched_control": m15_by_id[strategy_id]["matched_control"],
            "subrun_results": subruns,
            "parameter_sensitivity": {
                "registered_grid": meta["parameter_sensitivity"],
                "M15": subruns["M15"]["parameter_sensitivity"],
                "H1_H4": subruns["H1_H4"]["parameter_sensitivity"],
            },
            "weaknesses": meta["weaknesses"],
            "decision": decision,
            "decision_reasons": reasons,
            "conservative_rank_score": rank_score,
        })

    ranked = {}
    for family in FAMILIES:
        family_rows = [item for item in merged if item["family"] == family]
        ranked[family] = [
            item["strategy_id"]
            for item in sorted(
                family_rows,
                key=lambda item: item["conservative_rank_score"] if item["conservative_rank_score"] is not None else float("-inf"),
                reverse=True,
            )
        ]

    result = {
        "phase": "PHASE8_BLIND_DISCOVERY",
        "decision_scope": "DISCOVERY_CROSS_TIMEFRAME_STRATIFIED",
        "evaluated_period": m15["evaluated_period"],
        "development_oos_final_holdout_accessed": False,
        "run_id": args.run_id,
        "rank_method": "Descending minimum of M15 and H1/H4 episode-weighted mean edge; no favorable-timeframe selection.",
        "ranked_top5_per_family": ranked,
        "decision_counts": {
            decision: sum(item["decision"] == decision for item in merged)
            for decision in ("REJECT", "WATCH", "DEVELOPMENT")
        },
        "candidates": merged,
        "limitations": [
            "M15 and H1/H4 artifacts were clustered separately; unique episodes cannot be added because calendar dates overlap.",
            "A WATCH candidate must undergo one unified episode-level rerun before Development testing.",
            "This is Dukascopy bar screening, not OANDA MT5 tick/cost validation.",
            "Commission, slippage, swap and CFD roll effects are not yet included.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
