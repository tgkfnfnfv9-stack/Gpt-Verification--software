#!/usr/bin/env python3
"""Verify the exact price-free public report from the Run #1 Drive inventory."""

from __future__ import annotations

import argparse
from pathlib import Path

from fxcm_drive_vault_common import (
    HEX64,
    VaultError,
    canonical_json_bytes,
    canonical_sha256,
    load_json,
    reject_prohibited_keys,
    sha256_file,
)
from fxcm_drive_vault_run1_read_only_inventory import REPORT_FILES, REPORT_SCHEMA, SOURCE_HEAD_SHA, SOURCE_RUN_ID, YEARS


def verify(report_dir: Path, expected_head_sha: str, expected_run_id: str) -> dict:
    if report_dir.is_symlink() or not report_dir.is_dir():
        raise VaultError("read-only inventory report directory invalid")
    entries = sorted(report_dir.iterdir(), key=lambda path: path.name)
    if [path.name for path in entries] != list(REPORT_FILES):
        raise VaultError("read-only inventory report file set mismatch")
    for path in entries:
        stat = path.lstat()
        if path.is_symlink() or not path.is_file() or stat.st_nlink != 1:
            raise VaultError("read-only inventory report contains unsafe file")
    report_path = report_dir / REPORT_FILES[0]
    if report_path.stat().st_size > 1024 * 1024:
        raise VaultError("read-only inventory report exceeds byte limit")
    report = load_json(report_path)
    if report_path.read_bytes() != canonical_json_bytes(report):
        raise VaultError("read-only inventory report is not canonical JSON")
    reject_prohibited_keys(report)
    serialized = canonical_json_bytes(report).lower()
    forbidden = (
        b"drive_file_id", b"drive_folder_id", b"access_token", b"refresh_token",
        b"client_secret", b"bid_open", b"ask_open", b"timestamp_utc", b"resumable",
    )
    if any(fragment in serialized for fragment in forbidden):
        raise VaultError("read-only inventory report contains private or price-bearing material")
    if (
        report.get("schema_version") != REPORT_SCHEMA
        or report.get("status") != "INVENTORY_COMPLETED_READ_ONLY_METADATA_GETS_ONLY"
        or report.get("inventory_run_id") != expected_run_id
        or report.get("inventory_run_attempt") != 1
        or report.get("inventory_head_sha") != expected_head_sha
        or report.get("source_acquisition_run_id") != SOURCE_RUN_ID
        or report.get("source_acquisition_run_attempt") != 1
        or report.get("source_acquisition_head_sha") != SOURCE_HEAD_SHA
        or report.get("source_acquisition_conclusion") != "failure"
        or report.get("root_owner_only_verified") is not True
        or report.get("year_count") != 14
        or report.get("drive_api_methods") != ["GET"]
        or report.get("drive_mutation_count") != 0
        or report.get("drive_file_content_bytes_read") != 0
        or report.get("fxcm_source_request_count") != 0
        or report.get("price_bytes_read") != 0
        or report.get("credentials_in_public_report") is not False
        or report.get("drive_object_ids_in_public_report") != 0
        or report.get("arbitrary_remote_names_in_public_report") != 0
        or report.get("cleanup_authorized") is not False
        or report.get("recovery_acquisition_authorized") is not False
        or report.get("v2_1_rerun_authorized") is not False
        or report.get("count_only_authorized") is not False
        or report.get("batch6_authorized") is not False
        or report.get("research_statistics_calculated") is not False
        or report.get("formal_phase9_authorization_effect") is not False
    ):
        raise VaultError("read-only inventory report boundary mismatch")
    years = report.get("year_stages")
    if not isinstance(years, list) or [row.get("year") for row in years] != list(YEARS):
        raise VaultError("read-only inventory year order mismatch")
    required_classifications = {
        "COMPLETE_YEAR_STAGE_METADATA_ONLY",
        "PARTIAL_OR_INVALID_YEAR_STAGE_METADATA_ONLY",
        "MISSING_OR_AMBIGUOUS_YEAR_STAGE_METADATA_ONLY",
        "TRANSACTION_UNAVAILABLE_FOR_YEAR_INVENTORY",
    }
    for row in years:
        if (
            row.get("expected_archive_count") != 50
            or row.get("stage_classification") not in required_classifications
            or not isinstance(row.get("stage_metadata_valid"), bool)
            or not isinstance(row.get("year_manifest_metadata_valid"), bool)
            or not isinstance(row.get("valid_archive_metadata_count"), int)
            or not 0 <= row["valid_archive_metadata_count"] <= 50
            or not isinstance(row.get("missing_archive_count"), int)
            or not 0 <= row["missing_archive_count"] <= 50
            or not isinstance(row.get("valid_archive_names_sha256"), str)
            or HEX64.fullmatch(row["valid_archive_names_sha256"]) is None
            or not isinstance(row.get("valid_archive_metadata_sha256"), str)
            or HEX64.fullmatch(row["valid_archive_metadata_sha256"]) is None
        ):
            raise VaultError("read-only inventory year record mismatch")
    if report.get("year_stage_inventory_sha256") != canonical_sha256(years):
        raise VaultError("read-only inventory year digest mismatch")
    complete = [row["year"] for row in years if row["stage_classification"] == "COMPLETE_YEAR_STAGE_METADATA_ONLY"]
    if report.get("complete_year_stage_count") != len(complete) or report.get("complete_years") != complete:
        raise VaultError("read-only inventory complete year summary mismatch")
    if report.get("partial_or_unavailable_years") != [year for year in YEARS if year not in complete]:
        raise VaultError("read-only inventory partial year summary mismatch")
    manifest = (report_dir / REPORT_FILES[1]).read_text(encoding="ascii")
    if manifest != f"{sha256_file(report_path)}  {report_path.name}\n":
        raise VaultError("read-only inventory artifact manifest mismatch")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-run-id", required=True)
    args = parser.parse_args()
    verify(args.report_dir, args.expected_head_sha, args.expected_run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
