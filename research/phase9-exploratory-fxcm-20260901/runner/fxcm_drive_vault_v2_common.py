#!/usr/bin/env python3
"""Frozen-scope helpers for the availability-backed FXCM Drive vault V2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from fxcm_drive_vault_common import (
    DIRECT_HEADER,
    PUBLIC_AUDIT_FILES,
    ROOT_FOLDER_ID,
    SECRET_NAMES,
    VaultError,
    canonical_sha256,
    load_json,
    sha256_file,
    source_url,
)


YEARS_V2 = tuple(range(2012, 2026))
SYMBOLS_V2 = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY",
    "EURAUD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD", "GBPCAD",
    "GBPCHF", "GBPJPY", "GBPNZD", "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY",
    "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
)
DIRECT_PERIODICITIES_V2 = ("m1", "H1")
WEEKS_V2 = tuple(range(1, 53))
EXPECTED_SHARD_COUNT_V2 = 700
BASE_SOURCE_OBJECT_COUNT_V2 = 36400
PRESENT_SOURCE_OBJECT_COUNT_V2 = 36000
KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2 = 400


def identity_key(year: int, symbol: str, periodicity: str, week: int) -> str:
    return f"{year}/{symbol}/{periodicity}/{week:02d}"


def all_identity_keys() -> list[str]:
    return [
        identity_key(year, symbol, periodicity, week)
        for year in YEARS_V2
        for symbol in SYMBOLS_V2
        for periodicity in DIRECT_PERIODICITIES_V2
        for week in WEEKS_V2
    ]


def missing_identity_set(mask: dict[str, Any]) -> set[str]:
    rows = mask.get("known_missing_identity_keys")
    if not isinstance(rows, list) or any(not isinstance(row, str) for row in rows):
        raise VaultError("V2 availability missing identity list malformed")
    if len(rows) != len(set(rows)):
        raise VaultError("V2 availability missing identity list uniqueness mismatch")
    return set(rows)


def present_weeks(mask: dict[str, Any], year: int, symbol: str, periodicity: str) -> tuple[int, ...]:
    if year not in YEARS_V2 or symbol not in SYMBOLS_V2 or periodicity not in DIRECT_PERIODICITIES_V2:
        raise VaultError("V2 shard outside frozen scope")
    missing = missing_identity_set(mask)
    return tuple(
        week for week in WEEKS_V2
        if identity_key(year, symbol, periodicity, week) not in missing
    )


def known_missing_weeks(mask: dict[str, Any], year: int, symbol: str, periodicity: str) -> tuple[int, ...]:
    present = set(present_weeks(mask, year, symbol, periodicity))
    return tuple(week for week in WEEKS_V2 if week not in present)


def expected_shard_keys_v2() -> list[tuple[int, str, str]]:
    return [
        (year, symbol, periodicity)
        for year in YEARS_V2
        for symbol in SYMBOLS_V2
        for periodicity in DIRECT_PERIODICITIES_V2
    ]


def iter_present_source_identities(
    acquisition: dict[str, Any], mask: dict[str, Any]
) -> Iterable[tuple[int, str, str, int, str]]:
    for year, symbol, periodicity in expected_shard_keys_v2():
        for week in present_weeks(mask, year, symbol, periodicity):
            yield year, symbol, periodicity, week, source_url(acquisition, year, symbol, periodicity, week)


def expected_year_source_count(mask: dict[str, Any], year: int) -> int:
    matches = [row for row in mask["per_year"] if row.get("year") == year]
    if len(matches) != 1:
        raise VaultError("V2 year mask summary mismatch")
    return int(matches[0]["present_source_object_count"])


def partition_for_year_v2(partitions: dict[str, Any], year: int) -> dict[str, Any]:
    matches = [row for row in partitions["partitions"] if year in row["years"]]
    if len(matches) != 1:
        raise VaultError("V2 partition mapping mismatch")
    return matches[0]


def load_v2_contracts(
    acquisition_path: Path,
    partitions_path: Path,
    manifest_schema_path: Path,
    formal_boundary_path: Path,
    availability_mask_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    acquisition = load_json(acquisition_path)
    partitions = load_json(partitions_path)
    manifest = load_json(manifest_schema_path)
    formal = load_json(formal_boundary_path)
    mask = load_json(availability_mask_path)
    checks = (
        (acquisition.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-acquisition-v2.0.0", "acquisition schema"),
        (acquisition.get("status") == "FROZEN_APPROVED_NOT_EXECUTED", "acquisition status"),
        (acquisition.get("vault_version") == "v2", "vault version"),
        (acquisition.get("track") == "EXPLORATORY_FXCM_DRIVE_VAULT_NOT_FORMAL_PHASE9", "track"),
        (acquisition.get("user_scope_decision") == "OPTION_1_FXCM_AVAILABLE_SCOPE", "user scope decision"),
        (acquisition.get("formal_phase9_authorization_effect") is False, "formal authorization"),
        (acquisition.get("target", {}).get("years") == list(YEARS_V2), "years"),
        (acquisition.get("target", {}).get("symbols") == list(SYMBOLS_V2), "symbols"),
        (acquisition.get("target", {}).get("direct_periodicities") == list(DIRECT_PERIODICITIES_V2), "periodicities"),
        (acquisition.get("target", {}).get("expected_shard_count") == EXPECTED_SHARD_COUNT_V2, "shards"),
        (acquisition.get("target", {}).get("base_source_object_count") == BASE_SOURCE_OBJECT_COUNT_V2, "base sources"),
        (acquisition.get("target", {}).get("expected_present_source_object_count") == PRESENT_SOURCE_OBJECT_COUNT_V2, "present sources"),
        (acquisition.get("target", {}).get("known_missing_source_object_count") == KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2, "missing sources"),
        (acquisition.get("target", {}).get("excluded_unavailable_symbols") == ["CHFJPY", "EURCAD", "GBPAUD"], "excluded unavailable symbols"),
        (acquisition.get("direct_schema", {}).get("required_header") == list(DIRECT_HEADER), "direct header"),
        (acquisition.get("drive_custody", {}).get("root_folder_id") == ROOT_FOLDER_ID, "Drive root"),
        (acquisition.get("oauth", {}).get("secret_names") == list(SECRET_NAMES), "OAuth secrets"),
        (acquisition.get("oauth", {}).get("scope") == "https://www.googleapis.com/auth/drive.file", "OAuth scope"),
        (partitions.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-partitions-v2.0.0", "partition schema"),
        (partitions.get("status") == "FROZEN_AFTER_AVAILABILITY_BEFORE_PRICE_ACCESS", "partition status"),
        (manifest.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-manifest-schema-v2.0.0", "manifest schema"),
        (manifest.get("status") == "FROZEN_AFTER_AVAILABILITY_BEFORE_PRICE_ACCESS", "manifest status"),
        (manifest.get("year_manifest", {}).get("exact_shard_count") == 50, "year shards"),
        (manifest.get("vault_manifest", {}).get("exact_shard_count") == EXPECTED_SHARD_COUNT_V2, "vault shards"),
        (manifest.get("vault_manifest", {}).get("exact_present_source_object_count") == PRESENT_SOURCE_OBJECT_COUNT_V2, "vault sources"),
        (manifest.get("public_artifact", {}).get("exact_files") == list(PUBLIC_AUDIT_FILES), "public files"),
        (formal.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-formal-boundary-v2.0.0", "formal schema"),
        (formal.get("status") == "FROZEN_BEFORE_V2_PRICE_ACCESS", "formal status"),
        (formal.get("formal_phase9_authorization_effect") is False, "Formal authorization"),
        (mask.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-availability-mask-v2.0.0", "mask schema"),
        (mask.get("status") == "FROZEN_AFTER_RUN1_AVAILABILITY_BEFORE_PRICE_ACCESS", "mask status"),
    )
    for passed, label in checks:
        if not passed:
            raise VaultError(f"frozen V2 contract mismatch: {label}")
    boundaries = acquisition["research_boundaries"]
    if (
        boundaries.get("price_acquisition_executed") is not False
        or boundaries.get("count_only_authorized") is not False
        or boundaries.get("batch6_authorized") is not False
        or boundaries.get("returns_or_outcomes_authorized") is not False
        or boundaries.get("research_outcomes_calculated") is not False
        or boundaries.get("outcome_fields") != []
        or boundaries.get("confirmed_edge_count") != 0
        or boundaries.get("prior_candidates_301_through_320_rescued") is not False
        or boundaries.get("candidates_321_through_324_count_viewed") is not False
        or boundaries.get("existing_batch6_workflow_may_run") is not False
    ):
        raise VaultError("V2 acquisition research boundary mismatch")
    mask_rules = mask.get("rules", {})
    mask_boundaries = mask.get("research_boundaries", {})
    if (
        mask.get("identity_key_format") != "{year}/{symbol}/{periodicity}/{week_index_zero_padded_2}"
        or mask.get("source_audit") != "../results/run-33627420903/FXCM_DRIVE_VAULT_AVAILABILITY_INDEPENDENT_AUDIT.json"
        or mask.get("source_workflow_run") != {
            "run_id": 33627420903,
            "run_number": 1,
            "run_attempt": 1,
            "head_sha": "182f73dc41c5d6efcb0a5fd0a71bce3bbcffc825",
        }
        or mask_rules.get("download_exact_present_set_only") is not True
        or mask_rules.get("known_missing_requests_allowed") is not False
        or mask_rules.get("newly_appearing_known_missing_object_ignored_until_new_version") is not True
        or mask_rules.get("frozen_present_object_becomes_unavailable_action") != "FAIL_NO_SEAL"
        or mask_rules.get("dynamic_scope_change_allowed") is not False
        or mask_rules.get("forward_fill_allowed") is not False
        or mask_rules.get("interpolation_allowed") is not False
        or mask_boundaries.get("price_response_body_bytes_read_when_frozen") != 0
        or mask_boundaries.get("price_acquisition_executed") is not False
        or mask_boundaries.get("count_only_authorized") is not False
        or mask_boundaries.get("batch6_authorized") is not False
        or mask_boundaries.get("research_outcomes_calculated") is not False
        or mask_boundaries.get("outcome_fields") != []
    ):
        raise VaultError("V2 availability mask provenance or boundary mismatch")
    if acquisition["availability_evidence"]["mask_contract_sha256"] != sha256_file(availability_mask_path):
        raise VaultError("V2 availability mask SHA mismatch")
    scope = mask.get("scope", {})
    if (
        scope.get("years") != list(YEARS_V2)
        or scope.get("symbols") != list(SYMBOLS_V2)
        or scope.get("direct_periodicities") != list(DIRECT_PERIODICITIES_V2)
        or scope.get("endpoint_week_indices") != list(WEEKS_V2)
        or scope.get("base_source_object_count") != BASE_SOURCE_OBJECT_COUNT_V2
        or scope.get("present_source_object_count") != PRESENT_SOURCE_OBJECT_COUNT_V2
        or scope.get("known_missing_source_object_count") != KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2
    ):
        raise VaultError("V2 availability mask scope mismatch")
    all_keys = all_identity_keys()
    missing = missing_identity_set(mask)
    if len(all_keys) != BASE_SOURCE_OBJECT_COUNT_V2 or len(missing) != KNOWN_MISSING_SOURCE_OBJECT_COUNT_V2:
        raise VaultError("V2 availability mask count mismatch")
    if not missing.issubset(set(all_keys)):
        raise VaultError("V2 availability mask contains out-of-scope identity")
    expected_missing_order = [key for key in all_keys if key in missing]
    if mask["known_missing_identity_keys"] != expected_missing_order:
        raise VaultError("V2 availability missing identity grid order mismatch")
    present = [key for key in all_keys if key not in missing]
    if len(present) != PRESENT_SOURCE_OBJECT_COUNT_V2:
        raise VaultError("V2 present identity count mismatch")
    if canonical_sha256(present) != mask.get("present_identity_sha256"):
        raise VaultError("V2 present identity SHA mismatch")
    if canonical_sha256(expected_missing_order) != mask.get("known_missing_identity_sha256"):
        raise VaultError("V2 missing identity SHA mismatch")
    if len(expected_shard_keys_v2()) != EXPECTED_SHARD_COUNT_V2:
        raise VaultError("V2 derived shard count mismatch")
    if sum(1 for _ in iter_present_source_identities(acquisition, mask)) != PRESENT_SOURCE_OBJECT_COUNT_V2:
        raise VaultError("V2 derived present source count mismatch")
    expected_per_year = []
    for year in YEARS_V2:
        present_year = [key for key in present if key.startswith(f"{year}/")]
        missing_year = [key for key in expected_missing_order if key.startswith(f"{year}/")]
        expected_per_year.append({
            "year": year,
            "base_source_object_count": 2600,
            "present_source_object_count": len(present_year),
            "known_missing_source_object_count": len(missing_year),
            "present_identity_sha256": canonical_sha256(present_year),
            "known_missing_identity_sha256": canonical_sha256(missing_year),
        })
    if mask.get("per_year") != expected_per_year:
        raise VaultError("V2 per-year mask summary mismatch")
    previous_end = partitions["outer_interval"]["start_inclusive"]
    all_years: list[int] = []
    for row in partitions["partitions"]:
        if row["start_inclusive"] != previous_end:
            raise VaultError("V2 partition gap or overlap")
        previous_end = row["end_exclusive"]
        all_years.extend(row["years"])
    if previous_end != partitions["outer_interval"]["end_exclusive"] or all_years != list(YEARS_V2):
        raise VaultError("V2 partition coverage mismatch")
    expected_partitions = (
        ("DEVELOPMENT", list(range(2012, 2020)), "prices"),
        ("STRICT_OOS", [2020, 2021], "sealed/oos"),
        ("ROBUSTNESS", [2022, 2023], "sealed/robustness"),
        ("FINAL_HOLDOUT", [2024, 2025], "sealed/final_holdout"),
    )
    if tuple(
        (row.get("id"), row.get("years"), row.get("storage_namespace"))
        for row in partitions["partitions"]
    ) != expected_partitions:
        raise VaultError("V2 partition identity mismatch")
    interval = partitions.get("batch6_compatibility_interval", {})
    if (
        interval.get("start_inclusive") != "2017-01-01T00:00:00Z"
        or interval.get("end_exclusive") != "2018-12-31T00:00:00Z"
        or interval.get("access_authorized") is not False
    ):
        raise VaultError("V2 Batch 6 interval boundary mismatch")
    if acquisition["canonical_and_reference_roles"]["direct_H1"] != "QC_REFERENCE_ONLY_NEVER_FILL_OR_SUBSTITUTE":
        raise VaultError("V2 direct H1 role mismatch")
    if acquisition["canonical_and_reference_roles"]["direct_D1"] != "NOT_IN_V2_SOURCE_SCOPE":
        raise VaultError("V2 direct D1 boundary mismatch")
    if acquisition["derivation"].get("W1_outer_year_boundary_rule") != (
        "Drop any UTC Monday bucket whose seven-day interval is not wholly inside the calendar-year shard."
    ):
        raise VaultError("V2 W1 outer boundary mismatch")
    if formal.get("required_workflow_acknowledgement") != acquisition["workflow"]["formal_acknowledgement"]:
        raise VaultError("V2 Formal acknowledgement mismatch")
    return acquisition, partitions, manifest, formal, mask


def require_v2_confirmations(
    acquisition: dict[str, Any],
    confirmation: str,
    scope_confirmation: str,
    usage_confirmation: str,
    formal_acknowledgement: str,
) -> None:
    workflow = acquisition["workflow"]
    checks = (
        confirmation == workflow["acquisition_confirmation"],
        scope_confirmation == workflow["scope_confirmation"],
        usage_confirmation == workflow["usage_confirmation"],
        formal_acknowledgement == workflow["formal_acknowledgement"],
    )
    if not all(checks):
        raise VaultError("V2 workflow confirmation mismatch")
