#!/usr/bin/env python3
"""Offline verifier for the corrective simple-v1.1 recovery entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fxcm_drive_vault_common import VaultError, sha256_file


EXPECTED_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.1.0"
EXPECTED_DELAYS = [0, 5, 15, 30, 60, 120]


def verify(contract_path: Path, runner_path: Path, workflow_path: Path) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != EXPECTED_SCHEMA:
        raise VaultError("simple-v1.1 schema mismatch")
    if contract.get("status") != "FROZEN_IMPLEMENTED_NOT_AUTHORIZED_FOR_EXECUTION":
        raise VaultError("simple-v1.1 status mismatch")
    if contract.get("interval", {}).get("years") != [2022, 2023, 2024, 2025]:
        raise VaultError("simple-v1.1 year scope mismatch")
    if len(contract.get("symbols", [])) != 25 or len(set(contract["symbols"])) != 25:
        raise VaultError("simple-v1.1 symbol scope mismatch")
    counts = contract.get("counts", {})
    if (
        counts.get("archive_shards") != 200
        or counts.get("objects_uploaded_and_redownloaded") != 204
        or counts.get("frozen_present_source_identities") != 10084
        or counts.get("frozen_known_missing_source_identities") != 316
    ):
        raise VaultError("simple-v1.1 counts mismatch")
    source_policy = contract.get("source_policy", {})
    if (
        source_policy.get("content_integrity_attempts") != 6
        or source_policy.get("content_integrity_delays_seconds") != EXPECTED_DELAYS
        or source_policy.get("header_only_never_accepted_as_zero_rows") is not True
    ):
        raise VaultError("delayed retry policy mismatch")

    track = contract_path.parent.parent
    executed = contract.get("executed_v1_anchors", {})
    old_contract = track / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1.frozen.json"
    old_runner = track / "runner" / "fxcm_drive_vault_run1_recovery_simple_v1.py"
    repository_root = track.parents[1]
    old_workflow = repository_root / str(executed.get("workflow_snapshot_path", ""))
    if (
        sha256_file(old_contract) != executed.get("contract_sha256")
        or sha256_file(old_runner) != executed.get("runner_sha256")
        or not old_workflow.is_file()
        or sha256_file(old_workflow) != executed.get("workflow_sha256")
        or executed.get("head_sha") != "b00195915766e13429f0bc6d82a437e82c9f68f9"
        or executed.get("run_id") != "33757903542"
        or executed.get("conclusion") != "failure"
        or executed.get("drive_upload_count") != 0
        or executed.get("cleanup") != "PASS"
    ):
        raise VaultError("executed simple-v1 anchor mismatch")
    incident = contract.get("incident_audit", {})
    incident_path = repository_root / str(incident.get("path", ""))
    if not incident_path.is_file() or sha256_file(incident_path) != incident.get("sha256"):
        raise VaultError("incident audit SHA mismatch")

    runner = runner_path.read_text(encoding="utf-8")
    for required in (
        "INTEGRITY_DELAYS_SECONDS = (0, 5, 15, 30, 60, 120)",
        "header-only frozen source object",
        "MAX_INTEGRITY_UNCOMPRESSED_BYTES = base.acquire_base.MAX_SHARD_UNCOMPRESSED_BYTES",
        "source exceeds integrity uncompressed byte limit",
        "bounded delayed content-integrity retries",
        "destination.unlink(missing_ok=True)",
        "base.acquire_base.download_source = download_source_with_delayed_integrity_retry",
        "base.RECOVERY_VERSION = RECOVERY_VERSION",
        "base.load_simple_contract = load_simple_contract_v1_1",
        "properties[\"operational_version\"] = OPERATIONAL_VERSION",
        "properties[\"recovery_version\"] = RECOVERY_VERSION",
        "base.GoogleDrivePrivate = VersionedGoogleDrivePrivate",
        "base._validate_recovered_stage = validate_recovered_stage_v1_1",
        "base.reconcile_uploaded_stage = reconcile_uploaded_stage_v1_1",
    ):
        if required not in runner:
            raise VaultError(f"corrective runner missing control: {required}")
    for forbidden in (
        "PRESERVE_SOURCE_BYTES_AND_SHA256_WITH_ROW_COUNT_ZERO",
        "process_direct_shard_preserve_header_only",
    ):
        if forbidden in runner:
            raise VaultError(f"corrective runner contains forbidden header-only acceptance: {forbidden}")

    workflow = workflow_path.read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:",
        "github.run_number == 4",
        "RUN_FXCM_2022_2025_RECOVERY_QC_PRIVATE_UPLOAD_CORRECTIVE_ONCE",
        "fxcm_drive_vault_run1_recovery_simple_v1_1.py",
        "fxcm_drive_vault_run1_recovery_simple_v1_1.frozen.json",
        "for year in 2022 2023 2024 2025",
        "trap cleanup_current EXIT INT TERM HUP",
        "if: ${{ always() }}",
        "No artifact handoff",
        "git diff --exit-code",
    ):
        if required not in workflow:
            raise VaultError(f"workflow missing corrective control: {required}")
    for forbidden in ("actions/upload-artifact", "actions/download-artifact", "pull_request:", "push:"):
        if forbidden in workflow:
            raise VaultError(f"workflow contains forbidden trigger or artifact: {forbidden}")

    authorization = contract.get("current_authorization", {})
    if contract.get("provenance", {}).get("drive_app_properties") != {
        "operational_version": "v2.1+simple-v1.1-recovery",
        "recovery_version": "simple-v1.1",
    }:
        raise VaultError("v1.1 Drive appProperties provenance mismatch")
    for name in (
        "workflow_dispatch", "price_access", "oauth_token_exchange", "drive_access",
        "drive_write", "transaction_finalization", "research_use",
    ):
        if authorization.get(name) is not False:
            raise VaultError("published corrective contract must remain non-self-authorizing")

    return {
        "status": "PASS",
        "contract_sha256": sha256_file(contract_path),
        "runner_sha256": sha256_file(runner_path),
        "workflow_sha256": sha256_file(workflow_path),
        "incident_audit_sha256": sha256_file(incident_path),
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
