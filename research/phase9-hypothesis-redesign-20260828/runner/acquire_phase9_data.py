#!/usr/bin/env python3
"""Orchestrate four exact JForex Tester acquisitions without date inputs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
MANIFEST_DIR = ROOT / "data_manifest"
START_ISO = "2013-01-01T00:00:00Z"
M15_END_EXCLUSIVE_ISO = "2019-08-28T00:00:00Z"
H1_END_EXCLUSIVE_ISO = "2019-08-01T00:00:00Z"
CONFIRMATION = "ACQUIRE_PHASE9_JFOREX_FROZEN_INTERVALS_ONLY"
TIMEFRAMES = ("M15", "H1")
SIDES = ("bid", "ask")
EXPECTED_MAPPING = {
    "AUDJPY": "AUD/JPY",
    "AUDUSD": "AUD/USD",
    "EURGBP": "EUR/GBP",
    "EURJPY": "EUR/JPY",
    "EURUSD": "EUR/USD",
    "GBPJPY": "GBP/JPY",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "XAUUSD": "XAU/USD",
    "XAGUSD": "XAG/USD",
    "BRENTCMDUSD": "BRENT.CMD/USD",
    "LIGHTCMDUSD": "LIGHT.CMD/USD",
}
JAVA_INJECTION_ENVIRONMENT = (
    "CLASSPATH",
    "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS",
    "JDK_JAVA_OPTIONS",
)


def read_json(name: str) -> dict:
    return json.loads((MANIFEST_DIR / name).read_text(encoding="utf-8"))


def registered_symbols() -> list[tuple[str, str]]:
    mapping = read_json("instrument_mapping.json")
    rows = [
        (row["research_symbol"], row["provider_symbol"])
        for row in mapping["instruments"]
        if row["acquisition_enabled"]
    ]
    if dict(rows) != EXPECTED_MAPPING or len(rows) != 12:
        raise ValueError("JForex instrument mapping differs from the frozen 12-instrument mapping.")
    frozen = json.loads((ROOT / "spec" / "data_requirements.frozen.json").read_text(encoding="utf-8"))
    expected = {
        symbol
        for asset_class in ("FX", "PRECIOUS_METALS", "ENERGY")
        for symbol in frozen["universe"][asset_class]
    }
    if set(EXPECTED_MAPPING) != expected:
        raise ValueError("JForex research symbols differ from the frozen universe.")
    return rows


def assert_frozen_configuration() -> None:
    source = read_json("source_versions.json")
    data = json.loads((ROOT / "spec" / "data_requirements.frozen.json").read_text(encoding="utf-8"))
    policy = json.loads(
        (ROOT / "policy" / "preregistered_research_policy.json").read_text(encoding="utf-8")
    )
    allowed = data["allowed_acquisition"]
    if allowed["start_inclusive"] != START_ISO or allowed["end_exclusive"] != M15_END_EXCLUSIVE_ISO:
        raise ValueError("Frozen acquisition boundary differs from the JForex constants.")
    request = source["request"]
    if request["start_inclusive"] != START_ISO:
        raise ValueError("JForex start boundary differs from the frozen constant.")
    if request["end_exclusive_by_timeframe"] != {
        "M15": M15_END_EXCLUSIVE_ISO,
        "H1": H1_END_EXCLUSIVE_ISO,
    }:
        raise ValueError("JForex timeframe boundaries differ from the frozen amendment.")
    if request["timeframes"] != list(TIMEFRAMES) or request["sides"] != list(SIDES):
        raise ValueError("JForex timeframe or side set differs from the frozen request.")
    if request["expected_processes"] != 4 or request["expected_series"] != 48:
        raise ValueError("JForex process or series count differs from the frozen request.")
    if request["date_inputs_allowed"] is not False or request["derived_h1_from_m15_allowed"] is not False:
        raise ValueError("JForex source manifest does not fail closed.")
    if "acquire only 2013-01-01 inclusive through 2019-08-28 exclusive" not in policy["allowed_next"]:
        raise ValueError("Preregistered policy does not authorize the outer interval.")
    registered_symbols()


def checked_external_dir(value: str, label: str) -> Path:
    output = Path(value).expanduser().resolve()
    if output == REPO_ROOT or REPO_ROOT in output.parents:
        raise ValueError(f"{label} must be outside the repository checkout.")
    return output


def assert_no_java_injection_environment() -> None:
    present = [name for name in JAVA_INJECTION_ENVIRONMENT if os.environ.get(name)]
    if present:
        raise RuntimeError(f"Java injection environment is prohibited: {present}")


def build_plan(output_dir: Path, cache_root: Path, jar_path: Path) -> list[dict]:
    plan = []
    symbols = [research for research, _ in registered_symbols()]
    for timeframe in TIMEFRAMES:
        for side in SIDES:
            cache_dir = cache_root / f"{timeframe}-{side}"
            audit_path = cache_root / "runtime-origin-audit" / f"{timeframe}-{side}.txt"
            command = [
                "java",
                "-Dsun.reflect.inflationThreshold=2147483647",
                f"-javaagent:{jar_path}={audit_path}",
                "-jar",
                str(jar_path),
                "--output-dir",
                str(output_dir),
                "--cache-dir",
                str(cache_dir),
                "--timeframe",
                timeframe,
                "--side",
                side,
            ]
            plan.append(
                {
                    "timeframe": timeframe,
                    "side": side,
                    "start_inclusive": START_ISO,
                    "end_exclusive": (
                        M15_END_EXCLUSIVE_ISO if timeframe == "M15" else H1_END_EXCLUSIVE_ISO
                    ),
                    "output_files": [f"{symbol}_{timeframe}_{side}.csv" for symbol in symbols],
                    "command": command,
                }
            )
    files = [name for row in plan for name in row["output_files"]]
    if len(plan) != 4 or len(files) != 48 or len(set(files)) != 48:
        raise ValueError("JForex plan must contain four processes and 48 unique series.")
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire the frozen Phase 9 intervals through JForex.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-root", required=True)
    parser.add_argument("--jar", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    assert_frozen_configuration()
    output_dir = checked_external_dir(args.output_dir, "Raw output directory")
    cache_root = checked_external_dir(args.cache_root, "JForex cache root")
    jar_path = args.jar.expanduser().resolve()
    plan = build_plan(output_dir, cache_root, jar_path)
    if args.plan_only:
        print(json.dumps({"process_count": 4, "series_count": 48, "plan": plan}, indent=2))
        return

    if os.environ.get("PHASE9_JFOREX_CONFIRM") != CONFIRMATION:
        raise RuntimeError("Exact JForex acquisition confirmation is required.")
    assert_no_java_injection_environment()
    if not jar_path.is_file():
        raise RuntimeError("Pinned Phase 9 JForex acquisition jar is not built.")
    if output_dir.exists() or cache_root.exists():
        raise RuntimeError("Raw output and cache roots must not exist before acquisition.")
    output_dir.mkdir(parents=True)
    (cache_root / "runtime-origin-audit").mkdir(parents=True)
    for row in plan:
        subprocess.run(row["command"], check=True)


if __name__ == "__main__":
    main()
