#!/usr/bin/env python3
"""Simple-v1.2 recovery using query-isolated transport for canonical FXCM URLs."""

from __future__ import annotations

import csv
import gzip
import hashlib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import fxcm_drive_vault_run1_recovery_simple_v1_1 as v11
from fxcm_drive_vault_common import VaultError, load_json, sha256_file


base = v11.base
RECOVERY_VERSION = "simple-v1.2"
OPERATIONAL_VERSION = "v2.1+simple-v1.2-recovery"
EXPECTED_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.2.0"
INTEGRITY_DELAYS_SECONDS = v11.INTEGRITY_DELAYS_SECONDS
MAX_INTEGRITY_UNCOMPRESSED_BYTES = v11.MAX_INTEGRITY_UNCOMPRESSED_BYTES
V11_CONTRACT_SHA256 = "69f79eda40092184dc34eb55c79be3a51f90bcf972caa1c716e0f2090af7a141"
V11_RUNNER_SHA256 = "677635dada816a8e9d8d1a44ddc66d4eafbbad7546d7c588736112de1908b33c"
V11_WORKFLOW_SHA256 = "a5e92dc0488a109fa8176182d3889907149737569d33b0fcc96f945baa963ad0"
V11_FAILURE_AUDIT_SHA256 = "6abc1a3d6d0ca10b01c8628a730230b2b4d582b1cab1579ec55ff919d2f9965a"


def transport_url(
    canonical_url: str,
    integrity_attempt: int,
    transport_attempt: int,
) -> str:
    """Create a non-secret cache key without changing the canonical identity."""
    base.acquire_base.validate_source_url(canonical_url)
    if integrity_attempt not in range(1, 7) or transport_attempt not in range(1, 5):
        raise VaultError("transport attempt identity outside frozen bounds")
    parsed = urllib.parse.urlsplit(canonical_url)
    query = urllib.parse.urlencode({
        "phase9_v": "simple-v1.2",
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
    """Download one canonical identity through a deterministic cache-isolated URL."""
    base.acquire_base.validate_source_url(canonical_url)
    if destination.exists() or destination.is_symlink():
        raise VaultError("source destination must be new")
    for attempt in range(1, 5):
        url = transport_url(canonical_url, integrity_attempt, attempt)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "phase9-fxcm-drive-vault/1.2",
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


def download_source_with_cache_isolation(
    opener: Any,
    canonical_url: str,
    destination: Path,
) -> tuple[int, str]:
    """Retry invalid payloads through unique transport queries and fail closed."""
    last_error: Exception | None = None
    for integrity_attempt, delay_seconds in enumerate(INTEGRITY_DELAYS_SECONDS, start=1):
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            size, digest = download_transport(
                opener, canonical_url, destination, integrity_attempt
            )
            uncompressed_bytes = 0
            with gzip.open(destination, "rb") as stream:
                while True:
                    block = stream.read(1024 * 1024)
                    if not block:
                        break
                    uncompressed_bytes += len(block)
                    if uncompressed_bytes > MAX_INTEGRITY_UNCOMPRESSED_BYTES:
                        raise VaultError("source exceeds integrity uncompressed byte limit")
            with gzip.open(
                destination, "rt", encoding="utf-8-sig", newline=""
            ) as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
                first_row = next(reader, None)
            allowed_headers = (
                base.acquire_base.DIRECT_HEADER,
                base.acquire_base.DIRECT_HEADER + ("Volume",),
            )
            if tuple(header or ()) not in allowed_headers:
                raise VaultError("unexpected frozen source header")
            if first_row is None:
                raise VaultError("header-only frozen source object")
            return size, digest
        except (VaultError, gzip.BadGzipFile, EOFError, UnicodeError) as error:
            last_error = error
            destination.unlink(missing_ok=True)
            if not v11._retryable_integrity_error(error):
                raise VaultError(
                    "frozen-present source failed non-retryable integrity validation"
                ) from error
            if integrity_attempt == len(INTEGRITY_DELAYS_SECONDS):
                raise VaultError(
                    "frozen-present source failed cache-isolated integrity retries"
                ) from error
    raise VaultError("cache-isolated source integrity retry exhausted") from last_error


def load_simple_contract_v1_2(path: Path) -> dict[str, Any]:
    contract = load_json(path)
    source_policy = contract.get("source_policy", {})
    workflow = contract.get("workflow", {})
    authorization = contract.get("current_authorization", {})
    if (
        contract.get("schema_version") != EXPECTED_SCHEMA
        or contract.get("recovery_version") != RECOVERY_VERSION
        or contract.get("status") != "FROZEN_IMPLEMENTED_NOT_AUTHORIZED_FOR_EXECUTION"
        or contract.get("interval", {}).get("years") != list(base.RECOVERY_YEARS)
        or contract.get("symbols") != list(base.SYMBOLS_V2)
        or contract.get("direct_periodicities") != list(base.DIRECT_PERIODICITIES_V2)
        or contract.get("counts", {}).get("archive_shards") != 200
        or contract.get("counts", {}).get("frozen_present_source_identities") != 10084
        or contract.get("counts", {}).get("frozen_known_missing_source_identities") != 316
        or contract.get("existing_transaction", {}).get(
            "read_only_inventory_year_digest_sha256"
        ) != base.PRESERVED_INVENTORY_SHA256
        or source_policy.get("content_integrity_delays_seconds")
        != list(INTEGRITY_DELAYS_SECONDS)
        or source_policy.get("header_only_never_accepted_as_zero_rows") is not True
        or source_policy.get("transport_cache_bust", {}).get(
            "canonical_identity_stored_without_query"
        ) is not True
        or workflow.get("required_run_number") != 5
        or workflow.get("run_attempt") != 1
        or contract.get("provenance", {}).get("drive_app_properties") != {
            "operational_version": OPERATIONAL_VERSION,
            "recovery_version": RECOVERY_VERSION,
        }
        or authorization.get("workflow_dispatch") is not False
        or authorization.get("price_access") is not False
        or authorization.get("drive_write") is not False
    ):
        raise VaultError("simple-v1.2 recovery contract mismatch")

    repository_root = path.resolve().parents[3]
    track = path.parent.parent
    executed = contract.get("executed_v1_1_anchors", {})
    old_contract = track / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1_1.frozen.json"
    old_runner = track / "runner" / "fxcm_drive_vault_run1_recovery_simple_v1_1.py"
    old_workflow = repository_root / str(executed.get("workflow_snapshot_path", ""))
    if (
        executed.get("contract_sha256") != V11_CONTRACT_SHA256
        or executed.get("runner_sha256") != V11_RUNNER_SHA256
        or executed.get("workflow_sha256") != V11_WORKFLOW_SHA256
        or sha256_file(old_contract) != V11_CONTRACT_SHA256
        or sha256_file(old_runner) != V11_RUNNER_SHA256
        or not old_workflow.is_file()
        or sha256_file(old_workflow) != V11_WORKFLOW_SHA256
        or executed.get("run_id") != "33799360214"
        or executed.get("drive_upload_count") != 0
        or executed.get("cleanup") != "PASS"
    ):
        raise VaultError("executed simple-v1.1 provenance anchor mismatch")
    failure = contract.get("v1_1_failure_audit", {})
    failure_path = repository_root / str(failure.get("path", ""))
    if (
        failure.get("sha256") != V11_FAILURE_AUDIT_SHA256
        or not failure_path.is_file()
        or sha256_file(failure_path) != V11_FAILURE_AUDIT_SHA256
    ):
        raise VaultError("simple-v1.1 failure audit anchor mismatch")
    return contract


v11.RECOVERY_VERSION = RECOVERY_VERSION
v11.OPERATIONAL_VERSION = OPERATIONAL_VERSION
base.RECOVERY_VERSION = RECOVERY_VERSION
base.acquire_base.download_source = download_source_with_cache_isolation
base.load_simple_contract = load_simple_contract_v1_2


def main() -> int:
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
