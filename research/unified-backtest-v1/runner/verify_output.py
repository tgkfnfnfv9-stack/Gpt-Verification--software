#!/usr/bin/env python3
"""Fail-closed verifier for unified backtest result directories."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import sys

from unified_backtest import BacktestError, sha256_file, strict_json, validate_phase1


SAFE_PHASE1 = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.json$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
MAX_FILES = 100
MAX_TOTAL_BYTES = 1_500_000_000
SUMMARY_KEYS = {
    "schema_version", "status", "dataset", "configuration", "data_qc", "strategies",
    "contains_market_prices", "contains_return_metrics", "contains_signal_frequency_results",
    "contains_individual_trade_rows", "phase1_contains_market_prices",
    "phase1_contains_individual_trade_results",
}
DATASET_KEYS = {"dataset_id", "manifest_sha256", "instrument_count", "input_file_count"}
CONFIGURATION_KEYS = {
    "config_sha256", "registry_sha256", "primary_horizon", "diagnostic_horizons",
    "spread_included", "additional_commission_price", "slippage_price", "financing_included",
    "familywise_method", "familywise_alpha", "prior_outcome_tested_candidate_count",
    "current_candidate_count", "per_candidate_alpha",
}


def verify(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise BacktestError("result root must be real directory")
    files = []
    for path in root.rglob("*"):
        info = path.lstat()
        if path.is_symlink():
            raise BacktestError("result symlink rejected")
        if path.is_dir():
            continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BacktestError("result must contain regular single-link files only")
        files.append(path)
    if not files or len(files) > MAX_FILES or sum(path.stat().st_size for path in files) > MAX_TOTAL_BYTES:
        raise BacktestError("result resource limit exceeded")
    relatives = {path.relative_to(root).as_posix() for path in files}
    required = {"BACKTEST_SUMMARY.json", "artifact_manifest_sha256.txt"}
    if not required.issubset(relatives):
        raise BacktestError("required result files missing")
    for relative in relatives - required:
        pure = PurePosixPath(relative)
        if len(pure.parts) != 2 or pure.parts[0] != "phase1" or not SAFE_PHASE1.fullmatch(pure.parts[1]):
            raise BacktestError(f"unexpected result file: {relative}")
    summary = strict_json(root / "BACKTEST_SUMMARY.json")
    if set(summary) != SUMMARY_KEYS:
        raise BacktestError("summary root key mismatch")
    if summary["schema_version"] != "unified-backtest-summary-v1.0.0" or summary["status"] != "COMPLETE":
        raise BacktestError("summary version/status mismatch")
    if not isinstance(summary["dataset"], dict) or set(summary["dataset"]) != DATASET_KEYS:
        raise BacktestError("summary dataset key mismatch")
    if not SAFE_ID.fullmatch(summary["dataset"].get("dataset_id", "")):
        raise BacktestError("summary dataset_id mismatch")
    if not isinstance(summary["configuration"], dict) or set(summary["configuration"]) != CONFIGURATION_KEYS:
        raise BacktestError("summary configuration key mismatch")
    expected_classification = {
        "contains_market_prices": False,
        "contains_return_metrics": True,
        "contains_signal_frequency_results": True,
        "contains_individual_trade_rows": False,
    }
    if any(summary.get(key) is not value for key, value in expected_classification.items()):
        raise BacktestError("summary information classification mismatch")
    phase1_files = sorted(relative for relative in relatives if relative.startswith("phase1/"))
    if summary.get("phase1_contains_market_prices") is not bool(phase1_files) or summary.get("phase1_contains_individual_trade_results") is not bool(phase1_files):
        raise BacktestError("Phase 1 information classification mismatch")
    for relative in phase1_files:
        validate_phase1(strict_json(root / relative))
    expected_lines = [
        f"{sha256_file(root / relative)}  {relative}"
        for relative in sorted(relatives - {"artifact_manifest_sha256.txt"})
    ]
    try:
        actual_lines = (root / "artifact_manifest_sha256.txt").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BacktestError("invalid artifact manifest") from exc
    if actual_lines != expected_lines:
        raise BacktestError("artifact manifest mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    try:
        verify(Path(args.root))
    except BacktestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("Unified result verification PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
