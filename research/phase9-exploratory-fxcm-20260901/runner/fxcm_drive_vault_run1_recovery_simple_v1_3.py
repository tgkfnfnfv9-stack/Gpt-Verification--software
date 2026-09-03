#!/usr/bin/env python3
"""Simple-v1.3 recovery on the frozen macOS runner network path."""

from __future__ import annotations

import hashlib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import fxcm_drive_vault_run1_recovery_simple_v1_2 as v12
from fxcm_drive_vault_common import VaultError, load_json, sha256_file


base = v12.base
RECOVERY_VERSION = "simple-v1.3"
OPERATIONAL_VERSION = "v2.1+simple-v1.3-recovery"
EXPECTED_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.3.0"
V12_CONTRACT_SHA256 = "483931a807d5090a66dea63f2c9d8c1058c3203bf22f4c72bda9dcdc981ec604"
V12_RUNNER_SHA256 = "86786460082028a7523a1d9a543b579ba4bf5ddb565602993f1c77468475e0a6"
V12_WORKFLOW_SHA256 = "019bc69d2b5ca3cf2e974943755232374827466fc5f8e3c31edff37e95d6de6e"
V12_FAILURE_AUDIT_SHA256 = "4a9ae9d686c9f211f4813c1949d14d1a484c3ace2112ecba33fbad304a288ed6"
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


def transport_url(
    canonical_url: str,
    integrity_attempt: int,
    transport_attempt: int,
) -> str:
    """Use a V1.3 transport-only cache key for an unchanged canonical URL."""
    base.acquire_base.validate_source_url(canonical_url)
    if integrity_attempt not in range(1, 7) or transport_attempt not in range(1, 5):
        raise VaultError("transport attempt identity outside frozen bounds")
    parsed = urllib.parse.urlsplit(canonical_url)
    query = urllib.parse.urlencode({
        "phase9_v": RECOVERY_VERSION,
        "integrity_attempt": str(integrity_attempt),
        "transport_attempt": str(transport_attempt),
    })
    value = urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        query,
        "",
    ))
    transport = urllib.parse.urlsplit(value)
    if (
        transport.scheme != "https"
        or transport.hostname != "candledata.fxcorporate.com"
        or transport.port not in (None, 443)
        or transport.path != parsed.path
        or transport.fragment
    ):
        raise VaultError("cache-isolated transport URL mismatch")
    return value


def download_transport(
    opener: Any,
    canonical_url: str,
    destination: Path,
    integrity_attempt: int,
) -> tuple[int, str]:
    """Download through the V1.3 cache key without changing stored identity."""
    base.acquire_base.validate_source_url(canonical_url)
    if destination.exists() or destination.is_symlink():
        raise VaultError("source destination must be new")
    for attempt in range(1, 5):
        url = transport_url(canonical_url, integrity_attempt, attempt)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "phase9-fxcm-drive-vault/1.3",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        try:
            with opener.open(request, timeout=90) as response, destination.open("xb") as handle:
                if response.status != 200:
                    raise VaultError("source status is not 200")
                if response.geturl() != url:
                    raise VaultError("source final transport URL mismatch")
                total = 0
                digest = hashlib.sha256()
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > base.acquire_base.MAX_SOURCE_GZIP_BYTES:
                        raise VaultError("source object exceeds compressed byte limit")
                    digest.update(block)
                    handle.write(block)
            if total < 20:
                raise VaultError("source object too small")
            with destination.open("rb") as handle:
                if handle.read(2) != b"\x1f\x8b":
                    raise VaultError("source object is not gzip")
            return total, digest.hexdigest()
        except urllib.error.HTTPError as error:
            destination.unlink(missing_ok=True)
            if error.code in base.acquire_base.RETRYABLE_HTTP and attempt < 4:
                time.sleep(2 ** (attempt - 1))
                continue
            raise VaultError(
                f"missing or unavailable frozen source object: HTTP {error.code}"
            ) from None
        except (
            urllib.error.URLError,
            ssl.SSLError,
            TimeoutError,
            ConnectionError,
        ) as error:
            destination.unlink(missing_ok=True)
            if attempt < 4:
                time.sleep(2 ** (attempt - 1))
                continue
            raise VaultError("source download failed after bounded retries") from error
        except Exception:
            destination.unlink(missing_ok=True)
            raise
    raise AssertionError("unreachable")


def load_simple_contract_v1_3(path: Path) -> dict[str, Any]:
    """Validate V1.3 and the immutable, zero-write V1.2 execution anchors."""
    contract = load_json(path)
    source_policy = contract.get("source_policy", {})
    workflow = contract.get("workflow", {})
    authorization = contract.get("current_authorization", {})
    network = contract.get("network_transport_revision", {})
    if (
        contract.get("schema_version") != EXPECTED_SCHEMA
        or contract.get("recovery_version") != RECOVERY_VERSION
        or contract.get("status") != "FROZEN_IMPLEMENTED_NOT_AUTHORIZED_FOR_EXECUTION"
        or contract.get("interval") != {
            "start_inclusive": "2022-01-01T00:00:00Z",
            "end_exclusive": "2026-01-01T00:00:00Z",
            "years": list(base.RECOVERY_YEARS),
        }
        or contract.get("symbols") != list(base.SYMBOLS_V2)
        or contract.get("direct_periodicities") != list(base.DIRECT_PERIODICITIES_V2)
        or contract.get("derived_periodicities") != ["M5", "M15", "M30", "H4", "D1", "W1"]
        or contract.get("offer_sides") != ["BID", "ASK"]
        or contract.get("counts") != EXPECTED_COUNTS
        or contract.get("per_year") != EXPECTED_PER_YEAR
        or contract.get("existing_transaction", {}).get(
            "read_only_inventory_year_digest_sha256"
        ) != base.PRESERVED_INVENTORY_SHA256
        or source_policy.get("request_only_frozen_present") is not True
        or source_policy.get("request_known_missing") is not False
        or source_policy.get("content_integrity_delays_seconds")
        != list(v12.INTEGRITY_DELAYS_SECONDS)
        or source_policy.get("header_only_never_accepted_as_zero_rows") is not True
        or source_policy.get("transport_cache_bust", {}).get(
            "canonical_identity_stored_without_query"
        ) is not True
        or "required_run_number" in workflow
        or workflow.get("run_number_policy")
        != "NOT_AN_AUTHORIZATION_OR_EXECUTION_GATE"
        or workflow.get("preflight_mismatch_action") != "EXPLICIT_FAILURE"
        or workflow.get("single_use_semantics")
        != "AT_MOST_ONE_DRIVE_WRITING_RECOVERY_LINEAGE"
        or workflow.get("run_attempt") != 1
        or workflow.get("recover_runner_label") != "macos-15"
        or contract.get("provenance", {}).get("drive_app_properties") != {
            "operational_version": OPERATIONAL_VERSION,
            "recovery_version": RECOVERY_VERSION,
        }
        or network.get("revision") != "simple-v1.3-macos-network"
        or network.get("provider") != "FXCM CandleData"
        or network.get("canonical_url_identity_unchanged") is not True
        or network.get("runner_label") != "macos-15"
        or network.get("transport_query_tag") != RECOVERY_VERSION
        or network.get("user_agent") != "phase9-fxcm-drive-vault/1.3"
        or network.get("price_or_canonical_git_storage") is not False
        or network.get("public_artifact") is not False
        or authorization.get("workflow_dispatch") is not False
        or authorization.get("price_access") is not False
        or authorization.get("drive_write") is not False
    ):
        raise VaultError("simple-v1.3 recovery contract mismatch")

    repository_root = path.resolve().parents[3]
    track = path.resolve().parent.parent
    executed = contract.get("executed_v1_2_anchors", {})
    old_contract = repository_root / str(executed.get("contract_path", ""))
    old_runner = repository_root / str(executed.get("runner_path", ""))
    old_workflow = repository_root / str(executed.get("workflow_snapshot_path", ""))
    if (
        executed.get("contract_sha256") != V12_CONTRACT_SHA256
        or executed.get("runner_sha256") != V12_RUNNER_SHA256
        or executed.get("workflow_sha256") != V12_WORKFLOW_SHA256
        or old_contract != track / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1_2.frozen.json"
        or old_runner != track / "runner" / "fxcm_drive_vault_run1_recovery_simple_v1_2.py"
        or sha256_file(old_contract) != V12_CONTRACT_SHA256
        or sha256_file(old_runner) != V12_RUNNER_SHA256
        or not old_workflow.is_file()
        or sha256_file(old_workflow) != V12_WORKFLOW_SHA256
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
        raise VaultError("executed simple-v1.2 provenance anchor mismatch")
    failure = contract.get("v1_2_failure_audit", {})
    failure_path = repository_root / str(failure.get("path", ""))
    if (
        failure.get("sha256") != V12_FAILURE_AUDIT_SHA256
        or not failure_path.is_file()
        or sha256_file(failure_path) != V12_FAILURE_AUDIT_SHA256
    ):
        raise VaultError("simple-v1.2 failure audit anchor mismatch")
    return contract


# Keep all acquisition, QC, private upload, re-download verification, and
# cleanup behavior byte-for-byte inherited from V1.2. Only the workflow runner
# network and recovered-object version metadata change in V1.3.
v12.RECOVERY_VERSION = RECOVERY_VERSION
v12.OPERATIONAL_VERSION = OPERATIONAL_VERSION
v12.v11.RECOVERY_VERSION = RECOVERY_VERSION
v12.v11.OPERATIONAL_VERSION = OPERATIONAL_VERSION
base.RECOVERY_VERSION = RECOVERY_VERSION
# V1.2's integrity/QC loop is retained while its transport request builder is
# replaced with the V1.3-only cache key and User-Agent above.
v12.download_transport = download_transport
base.acquire_base.download_source = v12.download_source_with_cache_isolation
base.load_simple_contract = load_simple_contract_v1_3


def main() -> int:
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
