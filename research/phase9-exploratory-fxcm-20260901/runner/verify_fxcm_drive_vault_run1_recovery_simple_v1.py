#!/usr/bin/env python3
"""Offline verifier for the simplified Run #1 recovery implementation."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from fxcm_drive_vault_common import VaultError, sha256_file


EXPECTED_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.0.0"
EXPECTED_YEARS = [2022, 2023, 2024, 2025]


def verify(contract_path: Path, runner_path: Path, workflow_path: Path) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != EXPECTED_SCHEMA:
        raise VaultError("simple recovery schema mismatch")
    if contract.get("status") != "FROZEN_IMPLEMENTED_NOT_AUTHORIZED_FOR_EXECUTION":
        raise VaultError("simple recovery status mismatch")
    if contract.get("interval", {}).get("years") != EXPECTED_YEARS:
        raise VaultError("simple recovery year scope mismatch")
    if len(contract.get("symbols", [])) != 25 or len(set(contract["symbols"])) != 25:
        raise VaultError("simple recovery symbol scope mismatch")
    counts = contract.get("counts", {})
    if counts != {
        "years": 4,
        "symbols": 25,
        "direct_periodicities": 2,
        "archive_shards": 200,
        "year_manifests": 4,
        "objects_uploaded_and_redownloaded": 204,
        "base_weekly_source_identities": 10400,
        "frozen_present_source_identities": 10084,
        "frozen_known_missing_source_identities": 316,
    }:
        raise VaultError("simple recovery counts mismatch")
    authorization = contract.get("current_authorization", {})
    if not all(authorization.get(name) is True for name in ("implementation", "commit", "push")):
        raise VaultError("implementation authorization mismatch")
    if not all(authorization.get(name) is False for name in (
        "workflow_dispatch", "price_access", "oauth_token_exchange", "drive_access",
        "drive_write", "transaction_finalization", "research_use",
    )):
        raise VaultError("execution authorization must remain false")

    spec_dir = contract_path.parent
    observed = {
        name: sha256_file(spec_dir / name)
        for name in contract["frozen_anchors_sha256"]
    }
    if observed != contract["frozen_anchors_sha256"]:
        raise VaultError("frozen anchor SHA mismatch")
    recovery_schema = contract["recovery_manifest_schema"]
    recovery_schema_path = spec_dir / recovery_schema["path"]
    if sha256_file(recovery_schema_path) != recovery_schema["sha256"]:
        raise VaultError("recovery manifest schema SHA mismatch")
    recovery_schema_value = json.loads(recovery_schema_path.read_text(encoding="utf-8"))

    tree = ast.parse(runner_path.read_text(encoding="utf-8"))
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    required_functions = {
        "derive_qc_simple_v1", "expected_fx_timestamp_inventory", "verify_archive_exact",
        "verify_existing_transaction", "validate_year_manifest", "reconcile_uploaded_stage",
        "recover_year", "load_simple_contract", "verify_frozen_anchors",
    }
    if not required_functions.issubset(functions):
        raise VaultError("runner closure incomplete")
    literal_keys: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        if target in ("record", "year_manifest") and isinstance(value, ast.Dict):
            keys = {key.value for key in value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)}
            literal_keys[target] = keys
    if literal_keys.get("record") != set(recovery_schema_value["shard_exact_keys"]):
        raise VaultError("runner shard keys do not match frozen recovery schema")
    if literal_keys.get("year_manifest") != set(recovery_schema_value["year_manifest_exact_keys"]):
        raise VaultError("runner year manifest keys do not match frozen recovery schema")
    runner_text = runner_path.read_text(encoding="utf-8")
    for required in (
        "dropped_bucket_timestamp_sha256", "completed_bucket_timestamp_sha256",
        "INDEPENDENT_24X5_NEW_YORK_SESSION_EXPECTED_H1_SET", "duplicate archive member",
        "recovery_run_id", "download_verify", "SANITIZED_SUBPROCESS_ENV", "finally:",
    ):
        if required not in runner_text:
            raise VaultError(f"runner missing control: {required}")

    workflow = workflow_path.read_text(encoding="utf-8")
    for required in (
        "workflow_dispatch:", "expected_head_sha", "github.run_number == 1",
        "for year in 2022 2023 2024 2025", "scope_confirmation",
        "trap cleanup_current EXIT INT TERM HUP",
        "if: ${{ always() }}", "No artifact handoff", "git diff --exit-code",
    ):
        if required not in workflow:
            raise VaultError(f"workflow missing control: {required}")
    for forbidden in ("actions/upload-artifact", "actions/download-artifact", "pull_request:", "push:"):
        if forbidden in workflow:
            raise VaultError(f"workflow contains forbidden trigger or artifact: {forbidden}")

    return {
        "status": "PASS",
        "contract_sha256": sha256_file(contract_path),
        "runner_sha256": sha256_file(runner_path),
        "workflow_sha256": sha256_file(workflow_path),
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
