#!/usr/bin/env python3
"""Offline verifier for the frozen V2.2 Run #1 recovery design.

This verifier intentionally has no network, OAuth, FXCM, or Google Drive client
surface.  It validates repository-local design and pre-audit evidence only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_RECOVERY_YEARS = [2022, 2023, 2024, 2025]
EXPECTED_PRESERVED_YEARS = list(range(2012, 2022))
EXPECTED_STATUS = (
    "FROZEN_DESIGN_AND_PREAUDIT_ONLY_NOT_AUTHORIZED_FOR_IMPLEMENTATION_OR_EXECUTION"
)

ANCHOR_FILES = {
    "acquisition_v2_sha256": "spec/fxcm_drive_vault_acquisition_v2.frozen.json",
    "partitions_v2_sha256": "spec/fxcm_drive_vault_partitions_v2.frozen.json",
    "manifest_schema_v2_sha256": "spec/fxcm_drive_vault_manifest_schema_v2.frozen.json",
    "formal_boundary_v2_sha256": "spec/fxcm_drive_vault_formal_boundary_amendment_v2.frozen.json",
    "availability_mask_v2_sha256": "spec/fxcm_drive_vault_availability_mask_v2.frozen.json",
    "operational_hardening_v2_1_sha256": "spec/fxcm_drive_vault_operational_hardening_v2_1.frozen.json",
    "read_only_inventory_contract_v2_1_sha256": "spec/fxcm_drive_vault_run1_read_only_inventory_v2_1.frozen.json",
    "read_only_inventory_independent_audit_sha256": (
        "results/run-33732233208/FXCM_DRIVE_VAULT_RUN1_READ_ONLY_INDEPENDENT_AUDIT.json"
    ),
}

FORBIDDEN_EXECUTABLE_PATHS = (
    ".github/workflows/phase9-exploratory-fxcm-drive-vault-run1-recovery-v2-2.yml",
    ".github/workflows/phase9-exploratory-fxcm-drive-vault-run1-recovery-audit-v2-2.yml",
    ".github/workflows/phase9-exploratory-fxcm-drive-vault-run1-finalize-v2-2.yml",
    "research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_run1_recovery_v2_2.py",
    "research/phase9-exploratory-fxcm-20260901/runner/fxcm_drive_vault_run1_finalize_v2_2.py",
)


class VerificationError(ValueError):
    """Raised when a frozen recovery-design invariant is violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(contract_path: Path, repository_root: Path) -> dict[str, Any]:
    project_root = repository_root / "research/phase9-exploratory-fxcm-20260901"
    contract = load_json(contract_path)

    require(
        contract.get("schema")
        == "phase9-exploratory-fxcm-drive-vault-run1-recovery-v2.2.0",
        "unexpected recovery-design schema",
    )
    require(contract.get("status") == EXPECTED_STATUS, "design is not frozen and execution-disabled")

    scope = contract["scope"]
    require(scope["recovery_years"] == EXPECTED_RECOVERY_YEARS, "recovery scope must be 2022-2025 only")
    require(scope["preserved_years"] == EXPECTED_PRESERVED_YEARS, "preserved years must be 2012-2021")
    require(scope["symbols"] == 25, "symbol count changed")
    require(scope["direct_periodicities"] == ["m1", "H1"], "direct periodicities changed")
    require(scope["recovery_archive_shards"] == 4 * 25 * 2, "recovery archive count is not 200")
    require(scope["recovery_year_manifests"] == 4, "recovery manifest count is not 4")
    require(
        scope["base_weekly_source_identities"]
        == scope["frozen_present_source_identities"] + scope["frozen_known_missing_source_identities"],
        "frozen-present and frozen-missing identities do not partition the recovery scope",
    )
    require(scope["base_weekly_source_identities"] == 10400, "base weekly source count changed")
    require(scope["frozen_present_source_identities"] == 10084, "frozen-present source count changed")
    require(scope["frozen_known_missing_source_identities"] == 316, "frozen-missing source count changed")

    anchors = contract["frozen_anchors"]
    for field, relative_path in ANCHOR_FILES.items():
        anchor_path = project_root / relative_path
        require(anchor_path.is_file(), f"missing frozen anchor: {relative_path}")
        require(sha256_file(anchor_path) == anchors[field], f"frozen anchor digest mismatch: {field}")

    audit_path = project_root / ANCHOR_FILES["read_only_inventory_independent_audit_sha256"]
    audit = load_json(audit_path)
    source = contract["source_transaction_anchor"]
    require(source["workflow_run_id"] == audit["source_acquisition_run"]["run_id"], "source run mismatch")
    require(source["workflow_run_attempt"] == audit["source_acquisition_run"]["run_attempt"], "source attempt mismatch")
    require(source["head_sha"] == audit["source_acquisition_run"]["head_sha"], "source SHA mismatch")
    require(source["transaction_state"] == "ACQUIRING", "transaction must remain uncommitted")
    require(source["canonical_v2_folder_count"] == 0, "canonical v2 must remain absent")
    require(source["valid_uncommitted_transaction_count"] == 1, "expected exactly one transaction")

    inventory = audit["inventory_result"]
    observed = contract["preaudit_observed_state"]
    require(observed["inventory_run_id"] == audit["workflow_run"]["run_id"], "inventory run mismatch")
    require(observed["inventory_run_attempt"] == audit["workflow_run"]["run_attempt"], "inventory attempt mismatch")
    require(observed["inventory_head_sha"] == audit["workflow_run"]["head_sha"], "inventory SHA mismatch")
    require(
        anchors["read_only_inventory_year_digest_sha256"] == inventory["year_stage_inventory_sha256"],
        "year inventory digest mismatch",
    )

    preserved = observed["preserved_complete_years"]
    require(preserved["years"] == inventory["complete_years"] == EXPECTED_PRESERVED_YEARS, "preserved years mismatch")
    require(preserved["archive_count"] == inventory["valid_archive_metadata_count"] == 500, "preserved archive count mismatch")
    require(preserved["manifest_count"] == inventory["valid_year_manifest_count"] == 10, "preserved manifest count mismatch")
    require(preserved["archive_bytes"] == inventory["valid_archive_total_bytes"] == 2548863404, "preserved byte count mismatch")
    require(preserved["required_invariant"] == "UNCHANGED_BY_ALL_RECOVERY_GATES", "preserved state is not immutable")

    incomplete = observed["incomplete_empty_years"]
    require(incomplete["years"] == inventory["empty_incomplete_years"] == EXPECTED_RECOVERY_YEARS, "empty years mismatch")
    require(incomplete["archive_count"] == 0, "recovery stages are not recorded as empty")
    require(incomplete["manifest_count"] == 0, "recovery manifests are not recorded as absent")
    require(incomplete["missing_archive_count"] == inventory["missing_archive_count"] == 200, "missing archive count mismatch")
    require(incomplete["missing_manifest_count"] == 4, "missing manifest count mismatch")

    boundary = audit["read_only_boundary"]
    access = observed["inventory_access_counts"]
    require(boundary["drive_mutation_count"] == access["drive_mutation"] == 0, "preaudit mutated Drive")
    require(boundary["drive_file_content_bytes_read"] == access["drive_file_content_get"] == 0, "preaudit read Drive file content")
    require(boundary["fxcm_source_request_count"] == access["fxcm_request"] == 0, "preaudit requested FXCM")
    require(boundary["price_bytes_read"] == access["price_content_bytes"] == 0, "preaudit read price content")

    design = contract["versioned_recovery_design"]
    r1 = design["gate_r1_recovery_acquisition"]
    r2 = design["gate_r2_full_transaction_read_only_audit"]
    r3 = design["gate_r3_canonical_publication"]
    require(r1["years"] == EXPECTED_RECOVERY_YEARS, "R1 years escaped the recovery scope")
    require("10084" in r1["source_policy"] and "316" in r1["source_policy"], "R1 frozen mask policy is incomplete")
    require("BEFORE_ANY_OAUTH_TOKEN_EXCHANGE_OR_DRIVE_ACCESS" in r1["local_first_policy"], "R1 is not local-first")
    require(
        design["provenance_policy"]["preserved_2012_2021"]
        == "KEEP_ORIGINAL_RUN_33705800232_AND_HEAD_SHA_PROVENANCE_UNCHANGED",
        "preserved provenance is not explicit",
    )
    require(r2["drive_access"] == "METADATA_GET_ONLY", "R2 is not metadata-only")
    require(r2["drive_mutation"] == "FORBIDDEN", "R2 permits Drive mutation")
    require(r3["fxcm_access"] == "FORBIDDEN", "R3 permits FXCM access")
    for gate_name, gate in (("R1", r1), ("R2", r2), ("R3", r3)):
        require(gate["cleanup"] == "FORBIDDEN", f"{gate_name} permits cleanup")

    authorization = contract["current_authorization"]
    require(authorization, "authorization map is empty")
    require(all(value is False for value in authorization.values()), "at least one operation is authorized")
    require(authorization["cleanup"] is False, "cleanup is authorized")
    require(authorization["drive_access"] is False, "Drive access is authorized")
    require(authorization["fxcm_price_acquisition"] is False, "price acquisition is authorized")

    outputs = contract["current_gate_outputs"]
    require("EXECUTABLE_RECOVERY_WORKFLOW" in outputs["forbidden"], "executable workflow is not forbidden")
    require("CLEANUP" in outputs["forbidden"], "cleanup output is not forbidden")
    for relative_path in FORBIDDEN_EXECUTABLE_PATHS:
        require(not (repository_root / relative_path).exists(), f"forbidden executable path exists: {relative_path}")

    return {
        "schema": "phase9-exploratory-fxcm-drive-vault-run1-recovery-design-verification-v1.0.0",
        "status": "PASS",
        "contract_sha256": sha256_file(contract_path),
        "recovery_years": EXPECTED_RECOVERY_YEARS,
        "preserved_years": EXPECTED_PRESERVED_YEARS,
        "planned_recovery_archives": 200,
        "planned_recovery_manifests": 4,
        "executable_recovery_paths_present": 0,
        "network_access_performed": 0,
        "oauth_token_exchanges_performed": 0,
        "fxcm_requests_performed": 0,
        "drive_accesses_performed": 0,
        "drive_mutations_performed": 0,
        "cleanup_operations_performed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.contract.resolve(), args.repository_root.resolve())
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
