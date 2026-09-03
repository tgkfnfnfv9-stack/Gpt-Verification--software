#!/usr/bin/env python3
"""Offline verifier for cache-isolated simple-v1.2 FXCM recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fxcm_drive_vault_common import VaultError, sha256_file


EXPECTED_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.2.0"


def verify(contract_path: Path, runner_path: Path, workflow_path: Path) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version") != EXPECTED_SCHEMA
        or contract.get("recovery_version") != "simple-v1.2"
        or contract.get("interval", {}).get("years") != [2022, 2023, 2024, 2025]
        or len(contract.get("symbols", [])) != 25
        or len(set(contract.get("symbols", []))) != 25
        or contract.get("counts", {}).get("frozen_present_source_identities") != 10084
        or contract.get("counts", {}).get("frozen_known_missing_source_identities") != 316
        or contract.get("counts", {}).get("archive_shards") != 200
        or contract.get("workflow", {}).get("required_run_number") != 5
    ):
        raise VaultError("simple-v1.2 scope or execution identity mismatch")
    cache = contract.get("source_policy", {}).get("transport_cache_bust", {})
    if (
        cache.get("canonical_identity_stored_without_query") is not True
        or cache.get("transport_query_only") is not True
        or cache.get("query_values_nonsecret") is not True
        or cache.get("redirect_action") != "REJECT"
        or cache.get("payload_sha256_required") is not True
    ):
        raise VaultError("simple-v1.2 transport policy mismatch")
    if contract.get("provenance", {}).get("drive_app_properties") != {
        "operational_version": "v2.1+simple-v1.2-recovery",
        "recovery_version": "simple-v1.2",
    }:
        raise VaultError("simple-v1.2 Drive provenance mismatch")

    repository_root = contract_path.resolve().parents[3]
    track = contract_path.parent.parent
    executed = contract.get("executed_v1_1_anchors", {})
    old_contract = track / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1_1.frozen.json"
    old_runner = track / "runner" / "fxcm_drive_vault_run1_recovery_simple_v1_1.py"
    old_workflow = repository_root / str(executed.get("workflow_snapshot_path", ""))
    if (
        sha256_file(old_contract) != executed.get("contract_sha256")
        or sha256_file(old_runner) != executed.get("runner_sha256")
        or not old_workflow.is_file()
        or sha256_file(old_workflow) != executed.get("workflow_sha256")
        or executed.get("run_id") != "33799360214"
        or executed.get("run_number") != 4
        or executed.get("conclusion") != "failure"
        or executed.get("drive_upload_count") != 0
        or executed.get("cleanup") != "PASS"
    ):
        raise VaultError("executed simple-v1.1 anchor mismatch")
    failure = contract.get("v1_1_failure_audit", {})
    failure_path = repository_root / str(failure.get("path", ""))
    if not failure_path.is_file() or sha256_file(failure_path) != failure.get("sha256"):
        raise VaultError("simple-v1.1 failure audit mismatch")

    runner = runner_path.read_text(encoding="utf-8")
    for required in (
        "def transport_url(",
        "phase9_v",
        "integrity_attempt",
        "transport_attempt",
        "Cache-Control",
        "Pragma",
        "source final transport URL mismatch",
        "MAX_SOURCE_GZIP_BYTES",
        "MAX_INTEGRITY_UNCOMPRESSED_BYTES",
        "base.acquire_base.validate_source_url(canonical_url)",
        "base.acquire_base.download_source = download_source_with_cache_isolation",
        "base.load_simple_contract = load_simple_contract_v1_2",
        "v11.OPERATIONAL_VERSION = OPERATIONAL_VERSION",
        "v11.RECOVERY_VERSION = RECOVERY_VERSION",
    ):
        if required not in runner:
            raise VaultError(f"v1.2 runner missing control: {required}")
    if "header_only_never_accepted_as_zero_rows" not in runner:
        raise VaultError("v1.2 header-only fail-closed control missing")

    workflow = workflow_path.read_text(encoding="utf-8")
    for required in (
        "github.run_number == 5",
        "fxcm_drive_vault_run1_recovery_simple_v1_2.py",
        "fxcm_drive_vault_run1_recovery_simple_v1_2.frozen.json",
        "verify_fxcm_drive_vault_run1_recovery_simple_v1_2.py",
        "test_fxcm_drive_vault_run1_recovery_simple_v1_2.py",
        "for year in 2022 2023 2024 2025",
        "trap cleanup_current EXIT INT TERM HUP",
        "if: ${{ always() }}",
        "No artifact handoff",
    ):
        if required not in workflow:
            raise VaultError(f"workflow missing v1.2 control: {required}")
    for forbidden in ("actions/upload-artifact", "actions/download-artifact", "pull_request:", "push:"):
        if forbidden in workflow:
            raise VaultError(f"workflow contains forbidden trigger or artifact: {forbidden}")

    for name in (
        "workflow_dispatch",
        "price_access",
        "oauth_token_exchange",
        "drive_access",
        "drive_write",
        "transaction_finalization",
        "research_use",
    ):
        if contract.get("current_authorization", {}).get(name) is not False:
            raise VaultError("published v1.2 contract must remain non-self-authorizing")
    return {
        "status": "PASS",
        "contract_sha256": sha256_file(contract_path),
        "runner_sha256": sha256_file(runner_path),
        "workflow_sha256": sha256_file(workflow_path),
        "failure_audit_sha256": sha256_file(failure_path),
        "price_access": 0,
        "drive_access": 0,
        "workflow_dispatch": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--workflow", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.contract, args.runner, args.workflow), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
