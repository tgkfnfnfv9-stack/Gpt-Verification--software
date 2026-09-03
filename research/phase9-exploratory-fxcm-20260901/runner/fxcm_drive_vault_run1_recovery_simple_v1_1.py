#!/usr/bin/env python3
"""Corrective simple-v1.1 entrypoint with delayed FXCM integrity retries."""

from __future__ import annotations

import csv
import gzip
import time
from pathlib import Path
from typing import Any

import fxcm_drive_vault_run1_recovery_simple_v1 as base
from fxcm_drive_vault_common import VaultError, load_json, sha256_file


RECOVERY_VERSION = "simple-v1.1"
INTEGRITY_DELAYS_SECONDS = (0, 5, 15, 30, 60, 120)
EXPECTED_SCHEMA = "phase9-exploratory-fxcm-drive-vault-run1-recovery-simple-v1.1.0"
INCIDENT_AUDIT_SHA256 = "b9d28a6bcb294c8026f2feb8cf7e7e4e94c463307775ee96f0cbe3381b52f416"
EXECUTED_V1_CONTRACT_SHA256 = "d9720058ce7f7261aba20b90f8bc60e3e9a9721fec109fdbbe8ba4f3739be542"
EXECUTED_V1_RUNNER_SHA256 = "24d58cf27bc58925493752df84ea0bc98e16550fcfdbc405a049189e152f8cc3"
EXECUTED_V1_WORKFLOW_SHA256 = "57d9b1bb260d69d11206c555b383a397f92f2410aeba95e081258d1e2f057d71"
OPERATIONAL_VERSION = "v2.1+simple-v1.1-recovery"
BASE_GOOGLE_DRIVE_PRIVATE = base.GoogleDrivePrivate
MAX_INTEGRITY_UNCOMPRESSED_BYTES = base.acquire_base.MAX_SHARD_UNCOMPRESSED_BYTES


def _retryable_integrity_error(error: Exception) -> bool:
    if isinstance(error, (gzip.BadGzipFile, EOFError, UnicodeError)):
        return True
    message = str(error).lower()
    return any(marker in message for marker in (
        "too small", "not gzip", "header-only", "compressed file ended",
        "end-of-stream", "unexpected end",
    ))


def download_source_with_delayed_integrity_retry(
    opener: Any,
    url: str,
    destination: Path,
) -> tuple[int, str]:
    """Retry transient invalid or header-only frozen-present objects, then fail closed."""
    last_error: Exception | None = None
    for attempt, delay_seconds in enumerate(INTEGRITY_DELAYS_SECONDS, start=1):
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            size, digest = base.BASE_DOWNLOAD_SOURCE(opener, url, destination)
            uncompressed_bytes = 0
            with gzip.open(destination, "rb") as stream:
                while True:
                    block = stream.read(1024 * 1024)
                    if not block:
                        break
                    uncompressed_bytes += len(block)
                    if uncompressed_bytes > MAX_INTEGRITY_UNCOMPRESSED_BYTES:
                        raise VaultError("source exceeds integrity uncompressed byte limit")
            with gzip.open(destination, "rt", encoding="utf-8-sig", newline="") as handle:
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
            if not _retryable_integrity_error(error):
                raise VaultError("frozen-present source failed non-retryable integrity validation") from error
            if attempt == len(INTEGRITY_DELAYS_SECONDS):
                raise VaultError(
                    "frozen-present source failed bounded delayed content-integrity retries"
                ) from error
    raise VaultError("delayed source integrity retry exhausted") from last_error


def load_simple_contract_v1_1(path: Path) -> dict[str, Any]:
    contract = load_json(path)
    source_policy = contract.get("source_policy", {})
    workflow = contract.get("workflow", {})
    authorization = contract.get("current_authorization", {})
    if (
        contract.get("schema_version") != EXPECTED_SCHEMA
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
        or source_policy.get("content_integrity_delays_seconds") != list(INTEGRITY_DELAYS_SECONDS)
        or source_policy.get("header_only_never_accepted_as_zero_rows") is not True
        or workflow.get("required_run_number") != 2
        or workflow.get("run_attempt") != 1
        or contract.get("provenance", {}).get("drive_app_properties") != {
            "operational_version": OPERATIONAL_VERSION,
            "recovery_version": RECOVERY_VERSION,
        }
        or authorization.get("workflow_dispatch") is not False
        or authorization.get("price_access") is not False
        or authorization.get("drive_write") is not False
    ):
        raise VaultError("simple-v1.1 recovery contract mismatch")

    repository_root = path.resolve().parents[3]
    incident = contract.get("incident_audit", {})
    incident_path = repository_root / str(incident.get("path", ""))
    if (
        incident.get("sha256") != INCIDENT_AUDIT_SHA256
        or not incident_path.is_file()
        or sha256_file(incident_path) != INCIDENT_AUDIT_SHA256
    ):
        raise VaultError("Run #1 incident audit anchor mismatch")

    track = path.parent.parent
    executed = contract.get("executed_v1_anchors", {})
    old_contract = track / "spec" / "fxcm_drive_vault_run1_recovery_simple_v1.frozen.json"
    old_runner = track / "runner" / "fxcm_drive_vault_run1_recovery_simple_v1.py"
    old_workflow = repository_root / str(executed.get("workflow_snapshot_path", ""))
    if (
        executed.get("contract_sha256") != EXECUTED_V1_CONTRACT_SHA256
        or executed.get("runner_sha256") != EXECUTED_V1_RUNNER_SHA256
        or executed.get("workflow_sha256") != EXECUTED_V1_WORKFLOW_SHA256
        or sha256_file(old_contract) != EXECUTED_V1_CONTRACT_SHA256
        or sha256_file(old_runner) != EXECUTED_V1_RUNNER_SHA256
        or not old_workflow.is_file()
        or sha256_file(old_workflow) != EXECUTED_V1_WORKFLOW_SHA256
        or executed.get("run_id") != "33757903542"
        or executed.get("drive_upload_count") != 0
        or executed.get("cleanup") != "PASS"
    ):
        raise VaultError("executed simple-v1 provenance anchor mismatch")
    return contract


class VersionedGoogleDrivePrivate(BASE_GOOGLE_DRIVE_PRIVATE):
    """Attach the corrective implementation version to every recovered file."""

    def upload_file_new(
        self,
        parent_id: str,
        path: Path,
        remote_name: str,
        mime_type: str,
        app_properties: dict[str, str],
    ) -> dict[str, Any]:
        properties = dict(app_properties)
        if properties.get("operational_version") != "v2.1+simple-v1-recovery":
            raise VaultError("unexpected base recovery operational version")
        properties["operational_version"] = OPERATIONAL_VERSION
        properties["recovery_version"] = RECOVERY_VERSION
        return super().upload_file_new(
            parent_id, path, remote_name, mime_type, properties
        )


def validate_recovered_stage_v1_1(
    drive: Any,
    stage: dict[str, Any],
    year: int,
    recovery_run_id: str,
    recovery_head_sha: str,
) -> None:
    base._validate_stage_folder(stage, year)
    children = drive.list_children(stage["id"])
    names = [row.get("name") for row in children]
    expected_archives = base._archive_names(year)
    expected_names = set(expected_archives + ["YEAR_MANIFEST.json"])
    if len(names) != 51 or len(names) != len(set(names)) or set(names) != expected_names:
        raise VaultError("previous v1.1 recovered year exact inventory mismatch")
    common = {
        "vault_version": "v2",
        "operational_version": OPERATIONAL_VERSION,
        "recovery_version": RECOVERY_VERSION,
        "run_id": base.SOURCE_RUN_ID,
        "head_sha": base.SOURCE_HEAD_SHA,
        "recovery_run_id": recovery_run_id,
        "recovery_run_attempt": "1",
        "recovery_head_sha": recovery_head_sha,
        "year": str(year),
    }
    for name in expected_archives:
        row = next(item for item in children if item.get("name") == name)
        symbol, periodicity = name[len("fxcm-v2-") : -len(".tar.zst")].rsplit("-", 2)[0::2]
        properties = dict(row.get("appProperties") or {})
        digest = properties.pop("sha256", None)
        expected = {
            **common,
            "symbol": symbol,
            "periodicity": periodicity,
            "partition": base._partition_name(year),
            "state": "UNSEALED",
        }
        if (
            row.get("mimeType") != "application/zstd"
            or not isinstance(digest, str)
            or not base.HEX64.fullmatch(digest)
            or properties != expected
        ):
            raise VaultError("previous v1.1 recovered archive metadata mismatch")
    manifest = next(item for item in children if item.get("name") == "YEAR_MANIFEST.json")
    properties = dict(manifest.get("appProperties") or {})
    digest = properties.pop("sha256", None)
    if (
        manifest.get("mimeType") != "application/json"
        or not isinstance(digest, str)
        or not base.HEX64.fullmatch(digest)
        or properties != {**common, "state": "YEAR_COMPLETE_UNSEALED"}
    ):
        raise VaultError("previous v1.1 recovered manifest metadata mismatch")


def reconcile_uploaded_stage_v1_1(
    drive: Any,
    stage: dict[str, Any],
    shards: list[dict[str, Any]],
    manifest_id: str | None = None,
    manifest_sha256: str | None = None,
) -> None:
    children = drive.list_children(stage["id"])
    expected_names = {row["archive_name"] for row in shards}
    if manifest_id is not None:
        expected_names.add("YEAR_MANIFEST.json")
    names = [row.get("name") for row in children]
    if (
        len(names) != len(expected_names)
        or len(names) != len(set(names))
        or set(names) != expected_names
    ):
        raise VaultError("post-upload v1.1 stage exact inventory mismatch")
    for shard in shards:
        row = next(item for item in children if item.get("name") == shard["archive_name"])
        try:
            size = int(row.get("size"))
        except (TypeError, ValueError):
            size = -1
        expected_properties = {
            "vault_version": "v2",
            "operational_version": OPERATIONAL_VERSION,
            "recovery_version": RECOVERY_VERSION,
            "run_id": base.SOURCE_RUN_ID,
            "head_sha": base.SOURCE_HEAD_SHA,
            "recovery_run_id": shard["recovery_run_id"],
            "recovery_run_attempt": str(shard["recovery_run_attempt"]),
            "recovery_head_sha": shard["recovery_head_sha"],
            "year": str(shard["year"]),
            "symbol": shard["symbol"],
            "periodicity": shard["periodicity"],
            "sha256": shard["archive_sha256"],
            "partition": shard["partition_id"],
            "state": "UNSEALED",
        }
        if (
            row.get("id") != shard["drive_file_id"]
            or row.get("mimeType") != "application/zstd"
            or size != shard["archive_bytes"]
            or row.get("appProperties") != expected_properties
        ):
            raise VaultError("post-upload v1.1 archive metadata mismatch")
    if manifest_id is not None:
        row = next(item for item in children if item.get("name") == "YEAR_MANIFEST.json")
        expected_properties = {
            "vault_version": "v2",
            "operational_version": OPERATIONAL_VERSION,
            "recovery_version": RECOVERY_VERSION,
            "run_id": base.SOURCE_RUN_ID,
            "head_sha": base.SOURCE_HEAD_SHA,
            "recovery_run_id": shards[0]["recovery_run_id"],
            "recovery_run_attempt": str(shards[0]["recovery_run_attempt"]),
            "recovery_head_sha": shards[0]["recovery_head_sha"],
            "year": str(shards[0]["year"]),
            "sha256": manifest_sha256,
            "state": "YEAR_COMPLETE_UNSEALED",
        }
        if (
            row.get("id") != manifest_id
            or row.get("mimeType") != "application/json"
            or row.get("appProperties") != expected_properties
        ):
            raise VaultError("post-upload v1.1 year manifest metadata mismatch")


base.RECOVERY_VERSION = RECOVERY_VERSION
base.acquire_base.download_source = download_source_with_delayed_integrity_retry
base.load_simple_contract = load_simple_contract_v1_1
base.GoogleDrivePrivate = VersionedGoogleDrivePrivate
base._validate_recovered_stage = validate_recovered_stage_v1_1
base.reconcile_uploaded_stage = reconcile_uploaded_stage_v1_1


def main() -> int:
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
