#!/usr/bin/env python3
"""Price-nonreference verifier for macOS simple-v1.3 FXCM recovery."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from fxcm_drive_vault_common import VaultError, sha256_file


EXPECTED_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.3.0"
EXPECTED_COUNTS = {
    "years": 4,
    "symbols": 25,
    "direct_periodicities": 2,
    "archive_shards": 200,
    "year_manifests": 4,
    "objects_uploaded_and_redownloaded": 204,
    "base_weekly_source_identities": 10400,
    "frozen_present_source_identities": 10084,
    "frozen_known_missing_source_identities": 316,
}
EXPECTED_PER_YEAR = {
    "2022": {"present": 2600, "known_missing": 0, "archives": 50},
    "2023": {"present": 2600, "known_missing": 0, "archives": 50},
    "2024": {"present": 2479, "known_missing": 121, "archives": 50},
    "2025": {"present": 2405, "known_missing": 195, "archives": 50},
}


def verify(contract_path: Path, runner_path: Path, workflow_path: Path) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version") != EXPECTED_SCHEMA
        or contract.get("recovery_version") != "simple-v1.3"
        or contract.get("interval") != {
            "start_inclusive": "2022-01-01T00:00:00Z",
            "end_exclusive": "2026-01-01T00:00:00Z",
            "years": [2022, 2023, 2024, 2025],
        }
        or len(contract.get("symbols", [])) != 25
        or len(set(contract.get("symbols", []))) != 25
        or contract.get("direct_periodicities") != ["m1", "H1"]
        or contract.get("derived_periodicities") != ["M5", "M15", "M30", "H4", "D1", "W1"]
        or contract.get("offer_sides") != ["BID", "ASK"]
        or contract.get("counts") != EXPECTED_COUNTS
        or contract.get("per_year") != EXPECTED_PER_YEAR
        or contract.get("workflow", {}).get("recover_runner_label") != "macos-15"
        or "required_run_number" in contract.get("workflow", {})
        or contract.get("workflow", {}).get("run_number_policy")
        != "NOT_AN_AUTHORIZATION_OR_EXECUTION_GATE"
        or contract.get("workflow", {}).get("preflight_mismatch_action")
        != "EXPLICIT_FAILURE"
        or contract.get("workflow", {}).get("single_use_semantics")
        != "AT_MOST_ONE_DRIVE_WRITING_RECOVERY_LINEAGE"
        or contract.get("provenance", {}).get("drive_app_properties") != {
            "operational_version": "v2.1+simple-v1.3-recovery",
            "recovery_version": "simple-v1.3",
        }
    ):
        raise VaultError("simple-v1.3 scope or execution identity mismatch")
    source = contract.get("source_policy", {})
    network = contract.get("network_transport_revision", {})
    if (
        source.get("request_only_frozen_present") is not True
        or source.get("request_known_missing") is not False
        or source.get("header_only_never_accepted_as_zero_rows") is not True
        or source.get("transport_cache_bust", {}).get(
            "canonical_identity_stored_without_query"
        ) is not True
        or network.get("revision") != "simple-v1.3-macos-network"
        or network.get("canonical_url_identity_unchanged") is not True
        or network.get("direct_periodicities_unchanged") != ["m1", "H1"]
        or network.get("runner_label") != "macos-15"
        or network.get("transport_query_tag") != "simple-v1.3"
        or network.get("user_agent") != "phase9-fxcm-drive-vault/1.3"
        or network.get("price_or_canonical_git_storage") is not False
        or network.get("public_artifact") is not False
    ):
        raise VaultError("simple-v1.3 source or network policy mismatch")

    repository_root = contract_path.resolve().parents[3]
    executed = contract.get("executed_v1_2_anchors", {})
    old_contract = repository_root / str(executed.get("contract_path", ""))
    old_runner = repository_root / str(executed.get("runner_path", ""))
    old_workflow = repository_root / str(executed.get("workflow_snapshot_path", ""))
    if (
        sha256_file(old_contract) != executed.get("contract_sha256")
        or sha256_file(old_runner) != executed.get("runner_sha256")
        or not old_workflow.is_file()
        or sha256_file(old_workflow) != executed.get("workflow_sha256")
        or executed.get("head_sha") != "466519962b553461281a506139f3710f0129fc55"
        or executed.get("run_id") != "33805536160"
        or executed.get("run_number") != 8
        or executed.get("run_attempt") != 1
        or executed.get("preflight_job_id") != "100814989671"
        or executed.get("recovery_job_id") != "100815041380"
        or executed.get("conclusion") != "failure"
        or executed.get("failed_frozen_present_identity") != "2022/AUDCAD/m1/01"
        or executed.get("drive_upload_count") != 0
        or executed.get("drive_write_count") != 0
        or executed.get("public_artifact_count") != 0
        or executed.get("cleanup") != "PASS"
    ):
        raise VaultError("executed simple-v1.2 anchor mismatch")
    failure = contract.get("v1_2_failure_audit", {})
    failure_path = repository_root / str(failure.get("path", ""))
    if not failure_path.is_file() or sha256_file(failure_path) != failure.get("sha256"):
        raise VaultError("simple-v1.2 failure audit mismatch")

    runner = runner_path.read_text(encoding="utf-8")
    for required in (
        "import fxcm_drive_vault_run1_recovery_simple_v1_2 as v12",
        "def load_simple_contract_v1_3(",
        "simple-v1.3-macos-network",
        '"phase9_v": RECOVERY_VERSION',
        '"User-Agent": "phase9-fxcm-drive-vault/1.3"',
        "v12.download_transport = download_transport",
        "v12.v11.OPERATIONAL_VERSION = OPERATIONAL_VERSION",
        "v12.v11.RECOVERY_VERSION = RECOVERY_VERSION",
        "base.acquire_base.download_source = v12.download_source_with_cache_isolation",
        "base.load_simple_contract = load_simple_contract_v1_3",
        "return base.main()",
    ):
        if required not in runner:
            raise VaultError(f"v1.3 runner missing control: {required}")

    workflow = workflow_path.read_text(encoding="utf-8")
    for required in (
        "Validate exact execution inputs",
        "require_equal \"$GITHUB_REPOSITORY\"",
        "require_equal \"$GITHUB_REF\"",
        "require_equal \"$GITHUB_EVENT_NAME\" 'workflow_dispatch'",
        "require_equal \"$GITHUB_RUN_ATTEMPT\" '1'",
        "require_equal \"$INPUT_EXPECTED_HEAD_SHA\" \"$GITHUB_SHA\"",
        "::error title=Invalid dispatch::",
        "Verify macOS recovery runtime without price access",
        "test \"$RUNNER_OS\" = 'macOS'",
        "PHASE9_GDRIVE_OAUTH_CLIENT_ID: ${{ secrets.PHASE9_GDRIVE_OAUTH_CLIENT_ID }}",
        "PHASE9_GDRIVE_OAUTH_CLIENT_SECRET: ${{ secrets.PHASE9_GDRIVE_OAUTH_CLIENT_SECRET }}",
        "PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN: ${{ secrets.PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN }}",
        "fxcm_drive_vault_run1_recovery_simple_v1_3.py",
        "fxcm_drive_vault_run1_recovery_simple_v1_3.frozen.json",
        "verify_fxcm_drive_vault_run1_recovery_simple_v1_3.py",
        "test_fxcm_drive_vault_run1_recovery_simple_v1_3.py",
        "for year in 2022 2023 2024 2025",
        "trap cleanup_current EXIT INT TERM HUP",
        "if: ${{ always() }}",
        "No artifact handoff",
        "needs: preflight",
    ):
        if required not in workflow:
            raise VaultError(f"workflow missing v1.3 control: {required}")
    for forbidden in (
        "github.run_number ==",
        "actions/upload-artifact",
        "actions/download-artifact",
        "pull_request:",
        "push:",
        "PHASE9_GDRIVE_OAUTH_CLIENT_ID='${{ secrets.",
    ):
        if forbidden in workflow:
            raise VaultError(f"workflow contains forbidden trigger or artifact: {forbidden}")
    preflight, recovery = workflow.split("  preflight:\n", 1)[-1].split(
        "  recover-four-years:\n", 1
    )
    if re.search(r"^    if:", preflight, flags=re.MULTILINE):
        raise VaultError("preflight must not use a job-level if gate")
    if "runs-on: ubuntu-24.04" not in preflight or "runs-on: macos-15" not in recovery:
        raise VaultError("workflow runner labels are not frozen as reviewed")
    runtime = recovery.split(
        "      - name: Acquire QC private-upload and re-download four years sequentially",
        1,
    )[0]
    if "python3 --version" not in runtime or "zstd --version" not in runtime:
        raise VaultError("macOS runtime checks must precede price access")

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
            raise VaultError("published v1.3 contract must remain non-self-authorizing")
    return {
        "status": "PASS",
        "contract_sha256": sha256_file(contract_path),
        "runner_sha256": sha256_file(runner_path),
        "workflow_sha256": sha256_file(workflow_path),
        "failure_audit_sha256": sha256_file(failure_path),
        "runner_label": "macos-15",
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
