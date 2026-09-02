#!/usr/bin/env python3
"""One-shot identity observer for the exact previously observed libs_3.jnlp URL."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
UTILITY_PATH = Path(__file__).with_name("phase9_remote_jnlp_observer.py")
SPEC = importlib.util.spec_from_file_location("phase9_initial_jnlp_utility", UTILITY_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load initial JNLP observation utility")
utility = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = utility
SPEC.loader.exec_module(utility)

EXACT_CONFIRMATION = "OBSERVE_PHASE9_REMOTE_LIBS_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS"
EXACT_CONFIRMATION_V2 = (
    "OBSERVE_PHASE9_REMOTE_LIBS_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS_V2"
)
EXACT_URL = "https://platform.dukascopy.com/demo_3/libs_3.jnlp"
EXACT_HOST = "platform.dukascopy.com"
EXACT_PORT = 443
EXACT_PATH = "/demo_3/libs_3.jnlp"
MAX_BODY_BYTES = 2_097_152
SOURCE_ALLOWLIST = ROOT / "spec/remote_jnlp_observed_url_allowlist.frozen.json"
SOURCE_AUDIT = ROOT / "results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json"
EXPECTED_SOURCE_ALLOWLIST_SHA256 = "926c7fe3f2531e8bba1c43e1faef4efc7f69baca3ac3fff9ed22d36535c1e970"
EXPECTED_SOURCE_ALLOWLIST_BLOB = "099514e0a7ff4b63fe3a965c7c49e694f68302df"
EXPECTED_SOURCE_AUDIT_SHA256 = "802aa78553f7937c191996082e0037250352df6abf4cff8e11de08e511bb6d8d"

STATUS_MAP = {
    "INITIAL_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED":
        "LIBS_IDENTITY_OBSERVED_RESOURCE_REQUESTS_BLOCKED",
    "REDIRECT_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED":
        "LIBS_REDIRECT_IDENTITY_OBSERVED_BLOCKED",
    "NON_200_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED":
        "LIBS_NON_200_IDENTITY_OBSERVED_BLOCKED",
}


class ObservationError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_blob_sha(value: bytes) -> str:
    return hashlib.sha1(f"blob {len(value)}\0".encode("ascii") + value).hexdigest()


def configure_utility(confirmation: str = EXACT_CONFIRMATION) -> None:
    utility.EXACT_CONFIRMATION = confirmation
    utility.EXACT_URL = EXACT_URL
    utility.EXACT_HOST = EXACT_HOST
    utility.EXACT_PORT = EXACT_PORT
    utility.EXACT_PATH = EXACT_PATH
    utility.MAX_BODY_BYTES = MAX_BODY_BYTES


def validate_source_evidence(gate: dict) -> None:
    allowlist_raw = utility.require_regular_file(SOURCE_ALLOWLIST, "source allowlist").read_bytes()
    audit_raw = utility.require_regular_file(SOURCE_AUDIT, "source audit").read_bytes()
    if sha256_bytes(allowlist_raw) != EXPECTED_SOURCE_ALLOWLIST_SHA256:
        raise ObservationError("source allowlist SHA mismatch")
    if git_blob_sha(allowlist_raw) != EXPECTED_SOURCE_ALLOWLIST_BLOB:
        raise ObservationError("source allowlist blob mismatch")
    if sha256_bytes(audit_raw) != EXPECTED_SOURCE_AUDIT_SHA256:
        raise ObservationError("source audit SHA mismatch")
    allowlist = json.loads(allowlist_raw)
    rows = [
        row for row in allowlist.get("entries", [])
        if row.get("exact_url") == EXACT_URL
    ]
    if len(rows) != 1 or rows[0].get("kind") != "OBSERVED_EXTENSION_HREF_NOT_REQUESTED":
        raise ObservationError("exact extension URL was not independently observed")
    if rows[0].get("request_count_in_source_run") != 0:
        raise ObservationError("source run already requested extension URL")
    if allowlist.get("authorization", {}).get("extension_jnlp_request_authorized") is not False:
        raise ObservationError("source allowlist unexpectedly authorized request")
    source = gate.get("source_evidence", {})
    expected = {
        "observed_url_allowlist_path":
            "research/phase9-hypothesis-redesign-20260828/spec/remote_jnlp_observed_url_allowlist.frozen.json",
        "observed_url_allowlist_git_blob_sha": EXPECTED_SOURCE_ALLOWLIST_BLOB,
        "observed_url_allowlist_sha256": EXPECTED_SOURCE_ALLOWLIST_SHA256,
        "independent_audit_path":
            "research/phase9-hypothesis-redesign-20260828/results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json",
        "independent_audit_sha256": EXPECTED_SOURCE_AUDIT_SHA256,
        "source_run_id": 33500446289,
        "source_head_sha": "aa9d46a6a42936042a406bdf339f07d378cc79b7",
        "source_request_count_for_exact_url": 0,
        "source_entry_kind": "OBSERVED_EXTENSION_HREF_NOT_REQUESTED",
    }
    if source != expected:
        raise ObservationError("source evidence contract mismatch")


def validate_gate(path: Path) -> tuple[dict, str]:
    raw = utility.require_regular_file(path, "gate").read_bytes()
    gate = json.loads(raw)
    schema = gate.get("schema_version")
    if schema not in {
        "phase9-remote-libs-jnlp-observation-gate-v1.0",
        "phase9-remote-libs-jnlp-observation-gate-v2.0",
    }:
        raise ObservationError("unexpected gate schema")
    approval = gate.get("single_use_authorization", {})
    expected_confirmation = EXACT_CONFIRMATION
    expected_approval = {
        "user_approved": True,
        "approval_is_effective_only_after_exact_manual_confirmation": True,
        "workflow_dispatch_authorized_once": True,
        "authorization_consumed_on": "FIRST_WORKFLOW_DISPATCH_REGARDLESS_OF_RESULT",
        "required_github_run_number": 1,
        "required_github_run_attempt": 1,
        "retry_authorized": False,
        "replay_authorized": False,
    }
    if schema == "phase9-remote-libs-jnlp-observation-gate-v2.0":
        expected_confirmation = EXACT_CONFIRMATION_V2
        expected_approval = {
            "repository_preapproval": False,
            "exact_manual_dispatch_is_approval": True,
            "workflow_dispatch_authorized_once": True,
            "authorization_consumed_on": "FIRST_WORKFLOW_DISPATCH_REGARDLESS_OF_RESULT",
            "required_github_run_number": 1,
            "required_github_run_attempt": 1,
            "retry_authorized": False,
            "replay_authorized": False,
        }
    if approval != expected_approval:
        raise ObservationError("single-use authorization mismatch")
    scope = gate.get("exact_scope", {})
    expected_scope = {
        "extension_url": EXACT_URL,
        "allowed_urls_exact_set": [EXACT_URL],
        "scheme": "https", "host": EXACT_HOST, "port": EXACT_PORT,
        "explicit_port_in_url": False, "path": EXACT_PATH, "query": "",
        "fragment": "", "userinfo": "", "method": "GET",
        "dns_resolution_call_count_max": 1, "tcp_connect_attempt_count_max": 1,
        "http_request_count_max": 1, "response_body_bytes_max": MAX_BODY_BYTES,
        "follow_redirects": False, "redirect_location_record_only": True,
        "recursive_resource_fetch": False, "credentials": "NONE",
        "proxy_use": False, "execute_downloaded_code": False,
        "local_jnlp_identity_parse_if_status_200_and_identity_encoding": True,
    }
    if scope != expected_scope:
        raise ObservationError("exact observation scope mismatch")
    parsed = urlsplit(EXACT_URL)
    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path, parsed.query,
            parsed.fragment, parsed.username, parsed.password) != (
                "https", EXACT_HOST, None, EXACT_PATH, "", "", None, None):
        raise ObservationError("exact URL decomposition mismatch")
    if gate.get("approval_context", {}).get("exact_confirmation") != expected_confirmation:
        raise ObservationError("approval confirmation mismatch")
    if any(value is not False for value in gate.get("adjacent_authorizations", {}).values()):
        raise ObservationError("adjacent authorization enabled")
    same_run = gate.get("same_run_rules", {})
    if any(same_run.get(key) is not False for key in (
        "observation_may_self_authorize",
        "same_run_integrity_check_is_authoritative_independent_audit",
        "observation_may_freeze_runtime_allowlist",
        "observation_may_authorize_resource_requests",
        "observation_may_authorize_jforex_connection",
    )):
        raise ObservationError("same-run prohibition mismatch")
    artifact = gate.get("artifact_policy", {})
    if artifact != {
        "raw_jnlp_bytes_may_be_written_to_disk": False,
        "raw_jnlp_bytes_may_be_uploaded": False,
        "raw_jnlp_bytes_may_be_committed": False,
        "identity_audit_filename": "REMOTE_LIBS_JNLP_OBSERVATION_AUDIT.json",
        "manifest_filename": "artifact_manifest_sha256.txt",
        "exact_artifact_file_count": 2,
    }:
        raise ObservationError("artifact policy mismatch")
    if gate.get("scientific_state") != {
        "phase9_price_files": 0, "provider_schedule_files": 0,
        "research_outcomes_calculated": False, "outcome_fields": [],
    }:
        raise ObservationError("scientific state mismatch")
    validate_source_evidence(gate)
    configure_utility(expected_confirmation)
    return gate, sha256_bytes(raw)


def observe(
    args: argparse.Namespace,
    gate_sha256: str,
    expected_confirmation: str = EXACT_CONFIRMATION,
) -> dict:
    configure_utility(expected_confirmation)
    audit = utility.observe(args, gate_sha256)
    audit["schema_version"] = "phase9-remote-libs-jnlp-observation-audit-v1.0"
    audit["status"] = STATUS_MAP.get(audit["status"], audit["status"])
    return audit


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return utility.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    gate, gate_sha256 = validate_gate(args.gate)
    expected_confirmation = gate["approval_context"]["exact_confirmation"]
    audit = observe(args, gate_sha256, expected_confirmation)
    utility.write_new_json(args.output, audit)
    print(json.dumps({
        "status": audit["status"],
        "http_request_count": audit["transport"]["http_request_count"],
        "response_status": audit["response"]["status"],
        "raw_body_persisted": False,
        "resource_request_authorized": False,
    }, sort_keys=True))
    return 0 if audit["error_type"] is None else 1


if __name__ == "__main__":
    sys.exit(main())
