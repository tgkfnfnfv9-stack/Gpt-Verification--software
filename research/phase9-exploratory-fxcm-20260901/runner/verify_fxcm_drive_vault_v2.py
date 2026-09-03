#!/usr/bin/env python3
"""Verify the exact price-free public Artifact from V2 finalization."""

from __future__ import annotations

import argparse
from pathlib import Path

from fxcm_drive_vault_common import VaultError, assert_hex64, validate_public_report_tree


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-mask-sha256", required=True)
    parser.add_argument("--expected-amendment-sha256", required=True)
    args = parser.parse_args()
    value = validate_public_report_tree(args.report_dir)
    expected_keys = {
        "schema_version", "status", "vault_version", "run_id", "run_attempt", "head_sha",
        "year_count", "symbol_count", "direct_periodicity_count", "shard_count",
        "base_source_object_count", "source_object_count", "known_missing_source_object_count",
        "availability_mask_sha256", "vault_manifest_sha256", "vault_seal_sha256",
        "all_uploads_redownload_sha256_verified", "batch6_compatibility_passed",
        "full_provider_schedule_qc_claimed", "formal_phase9_authorization_effect",
        "count_only_authorized", "batch6_authorized", "research_outcomes_calculated",
        "outcome_fields", "public_price_files", "public_drive_identifiers",
        "operational_version", "operational_amendment_sha256",
        "transactional_publication_committed",
    }
    if set(value) != expected_keys:
        raise VaultError("V2 public audit key set mismatch")
    checks = (
        value.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-price-free-audit-v2.1.0",
        value.get("status") == "PRIVATE_VAULT_TRANSACTIONALLY_COMMITTED_PRICE_FREE_PUBLIC_AUDIT",
        value.get("vault_version") == "v2",
        value.get("operational_version") == "v2.1",
        value.get("head_sha") == args.expected_head_sha,
        value.get("run_id") == args.expected_run_id,
        type(value.get("run_attempt")) is int and value.get("run_attempt") == 1,
        type(value.get("year_count")) is int and value.get("year_count") == 14,
        type(value.get("symbol_count")) is int and value.get("symbol_count") == 25,
        type(value.get("direct_periodicity_count")) is int and value.get("direct_periodicity_count") == 2,
        type(value.get("shard_count")) is int and value.get("shard_count") == 700,
        type(value.get("base_source_object_count")) is int and value.get("base_source_object_count") == 36400,
        type(value.get("source_object_count")) is int and value.get("source_object_count") == 36000,
        type(value.get("known_missing_source_object_count")) is int and value.get("known_missing_source_object_count") == 400,
        value.get("availability_mask_sha256") == args.expected_mask_sha256,
        value.get("operational_amendment_sha256") == args.expected_amendment_sha256,
        value.get("all_uploads_redownload_sha256_verified") is True,
        value.get("transactional_publication_committed") is True,
        value.get("batch6_compatibility_passed") is False,
        value.get("full_provider_schedule_qc_claimed") is False,
        value.get("formal_phase9_authorization_effect") is False,
        value.get("count_only_authorized") is False,
        value.get("batch6_authorized") is False,
        value.get("research_outcomes_calculated") is False,
        value.get("outcome_fields") == [],
        type(value.get("public_price_files")) is int and value.get("public_price_files") == 0,
        type(value.get("public_drive_identifiers")) is int and value.get("public_drive_identifiers") == 0,
    )
    if not all(checks):
        raise VaultError("V2 public audit state mismatch")
    for field in (
        "availability_mask_sha256",
        "operational_amendment_sha256",
        "vault_manifest_sha256",
        "vault_seal_sha256",
    ):
        assert_hex64(value.get(field), f"V2.1 public audit {field}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
