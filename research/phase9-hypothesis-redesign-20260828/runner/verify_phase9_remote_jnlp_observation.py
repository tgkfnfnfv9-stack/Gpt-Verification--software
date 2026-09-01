#!/usr/bin/env python3
"""Verify the frozen remote-JNLP one-shot gate and its identity-only evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "spec/remote_jnlp_initial_observation_gate.frozen.json"
PROPOSAL = ROOT / "spec/remote_jnlp_observation_amendment.frozen.json"
WORKFLOW = ROOT.parents[1] / ".github/workflows/phase9-remote-jnlp-initial-observation.yml"
EXPECTED_GATE_SHA256 = "c1749720fd6f5a906b8dbcc7a285f88326a6c089ecba0dfa80191e56729c98bc"
EXPECTED_PROPOSAL_SHA256 = "26ddd52dc4bde39b9822a159c85a303477103f388703b99f338abf5634851631"
EXACT_CONFIRMATION = "OBSERVE_PHASE9_REMOTE_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS"
EXACT_URL = "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp"
ARTIFACT_FILES = {
    "REMOTE_JNLP_INITIAL_OBSERVATION_AUDIT.json",
    "artifact_manifest_sha256.txt",
}
FALSE_PROHIBITED = {
    "credentials_referenced", "jforex_connect_invoked",
    "provider_schedule_request_attempted", "availability_request_attempted",
    "market_price_request_attempted", "forbidden_market_period_request_attempted",
    "market_cache_persisted", "research_outcomes_calculated",
}
OUTCOME_KEYS = {
    "return", "return_sign", "mfe", "mae", "edge", "win", "loss",
    "win_rate", "profit_factor", "drawdown", "cumulative_r", "p_value",
    "confidence_interval", "ranking", "outcome_chart",
}
TOP_KEYS = {
    "schema_version", "attempt_started_at_utc", "status", "authorization",
    "github_identity", "request_scope", "transport", "response",
    "jnlp_identity", "prohibited_activity", "authorization_effect",
    "same_run_allowlist_frozen", "error_stage", "error_type",
}
AUTH_KEYS = {
    "exact_confirmation_matched", "single_use_authorization_consumed",
    "external_jnlp_observation_authorized_after_run", "retry_authorized",
    "replay_authorized", "gate_sha256",
}
GITHUB_KEYS = {
    "event_name", "ref", "head_sha", "run_id", "run_number", "run_attempt",
    "job_name",
}
REQUEST_SCOPE_KEYS = {
    "url", "method", "response_body_bytes_max", "credentials", "proxy_used",
    "redirect_followed", "recursive_resource_fetch_count",
    "downloaded_code_executed",
}
TRANSPORT_KEYS = {
    "dns_resolution_call_count", "tcp_connect_attempt_count", "http_request_count",
    "resolved_addresses", "selected_address", "peer", "tls_version",
    "tls_cipher", "tls_peer_certificate_sha256",
}
RESPONSE_KEYS = {
    "status", "reason", "safe_headers", "redirect_location",
    "body_bytes_if_status_200", "body_sha256_if_status_200",
    "body_identity_semantics",
}
PROHIBITED_KEYS = FALSE_PROHIBITED | {
    "phase9_price_files_acquired", "provider_schedule_files_acquired", "outcome_fields",
}
ADDRESS_KEYS = {"family", "address", "port", "scope_id"}
REFERENCE_KEYS = {
    "ordinal", "element_local_name", "raw_href", "resolved_url", "url_sha256",
    "fetched", "authorization_status",
}


class VerificationError(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_regular(path: Path, label: str) -> Path:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise VerificationError(f"{label} must be a single-link regular file")
    return path


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def require_exact_keys(value: dict, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise VerificationError(f"{label} keys mismatch")


def require_sha256(value, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise VerificationError(f"{label} is not SHA-256")


def verify_address(value: dict, label: str) -> None:
    require_exact_keys(value, ADDRESS_KEYS, label)
    if value["family"] not in {"AF_INET", "AF_INET6"}:
        raise VerificationError(f"{label} family invalid")
    try:
        import ipaddress
        parsed = ipaddress.ip_address(value["address"])
    except ValueError as exc:
        raise VerificationError(f"{label} address invalid") from exc
    if (parsed.version == 4) != (value["family"] == "AF_INET"):
        raise VerificationError(f"{label} family/address mismatch")
    if value["port"] != 443 or not isinstance(value["scope_id"], int) or value["scope_id"] < 0:
        raise VerificationError(f"{label} port/scope invalid")


def verify_static() -> dict:
    if sha256_file(require_regular(GATE, "gate")) != EXPECTED_GATE_SHA256:
        raise VerificationError("frozen gate SHA-256 mismatch")
    if sha256_file(require_regular(PROPOSAL, "proposal")) != EXPECTED_PROPOSAL_SHA256:
        raise VerificationError("original proposal changed")
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    if gate["approval_context"]["exact_confirmation"] != EXACT_CONFIRMATION:
        raise VerificationError("approval token mismatch")
    if gate["exact_scope"]["allowed_urls_exact_set"] != [EXACT_URL]:
        raise VerificationError("exact URL set mismatch")
    if gate["single_use_authorization"] != {
        "user_approved": True,
        "workflow_dispatch_authorized_once": True,
        "authorization_consumed_on": "FIRST_WORKFLOW_DISPATCH_REGARDLESS_OF_RESULT",
        "required_github_run_number": 1,
        "required_github_run_attempt": 1,
        "retry_authorized": False,
        "replay_authorized": False,
    }:
        raise VerificationError("single-use policy mismatch")
    if any(gate["adjacent_authorizations"].values()):
        raise VerificationError("adjacent authorization enabled")
    workflow = require_regular(WORKFLOW, "workflow").read_text(encoding="utf-8")
    required_snippets = (
        "workflow_dispatch:", "github.run_number == 1", "github.run_attempt == 1",
        "github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
        "persist-credentials: false", "ref: ${{ github.sha }}",
        "permissions:\n  contents: read", EXACT_CONFIRMATION,
        "include-hidden-files: false", "retention-days: 14",
        "id: seal", "always() && steps.seal.outcome == 'success'",
    )
    for snippet in required_snippets:
        if snippet not in workflow:
            raise VerificationError(f"workflow missing invariant: {snippet}")
    trigger_prefix = workflow.split("permissions:", 1)[0]
    if re.search(r"(?m)^\s*(push|pull_request|schedule):", trigger_prefix):
        raise VerificationError("workflow has a non-manual trigger")
    for prohibited in ("DUKASCOPY_USERNAME", "DUKASCOPY_PASSWORD", "curl ", "wget ",
                       "jforex", "mvn ", "java "):
        if prohibited.lower() in workflow.lower() and prohibited != "jforex":
            raise VerificationError(f"workflow contains prohibited execution token: {prohibited}")
    return {
        "schema_version": "phase9-remote-jnlp-static-verification-v1.0",
        "status": "STATIC_GATE_PASS_SINGLE_USE_PENDING_OR_CONSUMED",
        "gate_sha256": EXPECTED_GATE_SHA256,
        "proposal_sha256": EXPECTED_PROPOSAL_SHA256,
        "workflow_dispatch_only": True,
        "run_number_one_only": True,
        "run_attempt_one_only": True,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def verify_audit_dict(audit: dict) -> dict:
    require_exact_keys(audit, TOP_KEYS, "audit")
    if audit.get("schema_version") != "phase9-remote-jnlp-initial-observation-audit-v1.0":
        raise VerificationError("audit schema mismatch")
    if not isinstance(audit["attempt_started_at_utc"], str) or not re.fullmatch(
            r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z", audit["attempt_started_at_utc"]):
        raise VerificationError("audit timestamp invalid")
    auth = audit["authorization"]
    require_exact_keys(auth, AUTH_KEYS, "authorization")
    if auth != {
        "exact_confirmation_matched": True,
        "single_use_authorization_consumed": True,
        "external_jnlp_observation_authorized_after_run": False,
        "retry_authorized": False,
        "replay_authorized": False,
        "gate_sha256": EXPECTED_GATE_SHA256,
    }:
        raise VerificationError("audit authorization mismatch")
    identity = audit["github_identity"]
    require_exact_keys(identity, GITHUB_KEYS, "github identity")
    if identity["event_name"] != "workflow_dispatch" or identity["ref"] != "refs/heads/main":
        raise VerificationError("audit workflow identity mismatch")
    if identity["run_number"] != "1" or identity["run_attempt"] != "1":
        raise VerificationError("audit is not the authorized first attempt")
    if not re.fullmatch(r"[0-9a-f]{40}", identity["head_sha"]):
        raise VerificationError("audit head SHA invalid")
    if not isinstance(identity["run_id"], str) or not re.fullmatch(r"[1-9][0-9]*", identity["run_id"]):
        raise VerificationError("audit run ID invalid")
    if identity["job_name"] != "observe":
        raise VerificationError("audit logical job name invalid")
    scope = audit["request_scope"]
    require_exact_keys(scope, REQUEST_SCOPE_KEYS, "request scope")
    if scope != {
        "url": EXACT_URL,
        "method": "GET",
        "response_body_bytes_max": 2_097_152,
        "credentials": "NONE",
        "proxy_used": False,
        "redirect_followed": False,
        "recursive_resource_fetch_count": 0,
        "downloaded_code_executed": False,
    }:
        raise VerificationError("audit request scope mismatch")
    transport = audit["transport"]
    require_exact_keys(transport, TRANSPORT_KEYS, "transport")
    for key in ("dns_resolution_call_count", "tcp_connect_attempt_count", "http_request_count"):
        if transport[key] not in (0, 1):
            raise VerificationError(f"audit count exceeds one: {key}")
    dns_count = transport["dns_resolution_call_count"]
    tcp_count = transport["tcp_connect_attempt_count"]
    http_count = transport["http_request_count"]
    if not (dns_count >= tcp_count >= http_count):
        raise VerificationError("transport counter order invalid")
    resolved = transport["resolved_addresses"]
    if not isinstance(resolved, list) or len(resolved) > 64:
        raise VerificationError("resolved address list invalid")
    for index, address in enumerate(resolved):
        verify_address(address, f"resolved address {index}")
    if dns_count == 0 and resolved:
        raise VerificationError("addresses present without DNS call")
    selected = transport["selected_address"]
    if tcp_count:
        if selected is None:
            raise VerificationError("selected address missing")
        verify_address(selected, "selected address")
        if selected not in resolved:
            raise VerificationError("selected address absent from DNS set")
    elif selected is not None:
        raise VerificationError("selected address present without TCP attempt")
    peer = transport["peer"]
    tls_fields = (transport["tls_version"], transport["tls_cipher"],
                  transport["tls_peer_certificate_sha256"])
    if http_count:
        if peer is None or selected is None:
            raise VerificationError("HTTP request lacks peer identity")
        require_exact_keys(peer, {"address", "port"}, "peer")
        if peer != {"address": selected["address"], "port": 443}:
            raise VerificationError("peer differs from selected address")
        if not isinstance(transport["tls_version"], str) or not transport["tls_version"].startswith("TLSv1."):
            raise VerificationError("TLS version invalid")
        cipher = transport["tls_cipher"]
        if (not isinstance(cipher, list) or len(cipher) != 3
                or not isinstance(cipher[0], str) or not isinstance(cipher[1], str)
                or not isinstance(cipher[2], int)):
            raise VerificationError("TLS cipher invalid")
        require_sha256(transport["tls_peer_certificate_sha256"], "TLS certificate")
    elif peer is not None or any(value is not None for value in tls_fields):
        raise VerificationError("TLS identity present without HTTP request")
    if audit["authorization_effect"] != "NONE" or audit["same_run_allowlist_frozen"] is not False:
        raise VerificationError("same-run authorization effect present")
    prohibited = audit["prohibited_activity"]
    require_exact_keys(prohibited, PROHIBITED_KEYS, "prohibited activity")
    for key in FALSE_PROHIBITED:
        if prohibited.get(key) is not False:
            raise VerificationError(f"prohibited activity flag set: {key}")
    if prohibited["phase9_price_files_acquired"] != 0:
        raise VerificationError("Phase 9 price file count is nonzero")
    if prohibited["provider_schedule_files_acquired"] != 0:
        raise VerificationError("provider schedule file count is nonzero")
    if prohibited["outcome_fields"] != []:
        raise VerificationError("outcome fields are nonempty")
    if OUTCOME_KEYS.intersection(walk_keys(audit)):
        raise VerificationError("outcome key present")
    response = audit["response"]
    require_exact_keys(response, RESPONSE_KEYS, "response")
    if response["body_identity_semantics"] != "HTTP_ENTITY_BODY_AFTER_TRANSFER_DECODING_BEFORE_CONTENT_DECODING":
        raise VerificationError("body identity semantics mismatch")
    if response["reason"] is not None and (
            not isinstance(response["reason"], str) or not response["reason"].isascii()
            or len(response["reason"]) > 128):
        raise VerificationError("HTTP reason invalid")
    safe_headers = response["safe_headers"]
    if not isinstance(safe_headers, dict) or not set(safe_headers).issubset({
            "content-type", "content-encoding", "content-length", "etag", "last-modified", "location"}):
        raise VerificationError("safe response headers invalid")
    for name, values in safe_headers.items():
        if not isinstance(values, list) or not 1 <= len(values) <= 8:
            raise VerificationError(f"safe header list invalid: {name}")
        if any(not isinstance(value, str) or len(value) > 4096 for value in values):
            raise VerificationError(f"safe header value invalid: {name}")
    status = response["status"]
    if status is not None and (not isinstance(status, int) or not 100 <= status <= 599):
        raise VerificationError("HTTP response status invalid")
    if status is not None and http_count != 1:
        raise VerificationError("response present without one HTTP request")
    if status == 200:
        body_bytes = response["body_bytes_if_status_200"]
        body_sha = response["body_sha256_if_status_200"]
        if body_bytes is None and body_sha is None:
            if audit["status"] != "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED" or audit["error_stage"] not in {
                    "http_response", "response_body"}:
                raise VerificationError("200 response lacks body identity")
        else:
            if not isinstance(body_bytes, int) or not 0 <= body_bytes <= 2_097_152:
                raise VerificationError("200 body byte count invalid")
            require_sha256(body_sha, "200 body")
        if response["redirect_location"] is not None:
            raise VerificationError("200 response contains redirect Location")
        content_lengths = safe_headers.get("content-length", [])
        if body_bytes is not None and content_lengths and (
                len(content_lengths) != 1 or content_lengths[0] != str(body_bytes)):
            raise VerificationError("200 Content-Length/body count mismatch")
    elif response["body_bytes_if_status_200"] is not None or response["body_sha256_if_status_200"] is not None:
        raise VerificationError("non-200 contains body identity")
    if status in {300, 301, 302, 303, 307, 308}:
        location = response["redirect_location"]
        if location is not None and (not isinstance(location, str) or len(location) > 4096):
            raise VerificationError("redirect Location invalid")
        if set(safe_headers) - {"location"}:
            raise VerificationError("redirect contains non-Location headers")
    elif response["redirect_location"] is not None:
        raise VerificationError("non-redirect contains redirect Location")

    jnlp = audit["jnlp_identity"]
    common_jnlp_keys = {"status", "reference_count", "references", "reference_list_sha256"}
    if jnlp.get("status") == "PARSED_LOCAL_IDENTITY_ONLY":
        require_exact_keys(jnlp, common_jnlp_keys | {"root_codebase", "root_href"}, "JNLP identity")
        if status != 200:
            raise VerificationError("parsed JNLP without 200 response")
        for name in ("root_codebase", "root_href"):
            if not isinstance(jnlp[name], str) or len(jnlp[name]) > 4096:
                raise VerificationError(f"JNLP {name} invalid")
    elif jnlp.get("status") in {"NOT_PARSED", "SKIPPED_NON_IDENTITY_CONTENT_ENCODING"}:
        require_exact_keys(jnlp, common_jnlp_keys, "JNLP identity")
        if jnlp["status"] == "SKIPPED_NON_IDENTITY_CONTENT_ENCODING" and status != 200:
            raise VerificationError("content-encoding skip without 200 response")
    else:
        raise VerificationError("JNLP parse status invalid")
    references = jnlp["references"]
    if not isinstance(references, list) or len(references) > 1024 or jnlp["reference_count"] != len(references):
        raise VerificationError("JNLP reference count invalid")
    for index, reference in enumerate(references):
        require_exact_keys(reference, REFERENCE_KEYS, f"JNLP reference {index}")
        if reference["ordinal"] != index or reference["fetched"] is not False:
            raise VerificationError("JNLP reference order/fetch flag invalid")
        if reference["authorization_status"] != "OBSERVED_ONLY_NOT_ALLOWED":
            raise VerificationError("JNLP reference authorization invalid")
        for name in ("element_local_name", "raw_href", "resolved_url"):
            if not isinstance(reference[name], str) or len(reference[name]) > 4096:
                raise VerificationError(f"JNLP reference {name} invalid")
        require_sha256(reference["url_sha256"], "JNLP URL")
        if reference["url_sha256"] != sha256_bytes(reference["resolved_url"].encode("utf-8")):
            raise VerificationError("JNLP URL SHA mismatch")
    require_sha256(jnlp["reference_list_sha256"], "JNLP reference list")
    canonical = json.dumps(references, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    if jnlp["reference_list_sha256"] != sha256_bytes(canonical):
        raise VerificationError("JNLP reference list SHA mismatch")

    successful = {
        "INITIAL_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED": 200,
        "REDIRECT_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED": "redirect",
        "NON_200_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED": "non200",
    }
    if audit["status"] in successful:
        if audit["error_stage"] is not None or audit["error_type"] is not None:
            raise VerificationError("successful audit contains error")
        if (dns_count, tcp_count, http_count) != (1, 1, 1):
            raise VerificationError("successful audit transport counts invalid")
        expected = successful[audit["status"]]
        if expected == 200 and status != 200:
            raise VerificationError("success status/HTTP mismatch")
        if expected == "redirect" and status not in {300, 301, 302, 303, 307, 308}:
            raise VerificationError("redirect status/HTTP mismatch")
        if expected == "non200" and (status is None or status == 200 or status in {300, 301, 302, 303, 307, 308}):
            raise VerificationError("non-200 status/HTTP mismatch")
    elif audit["status"] == "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED":
        if audit["error_stage"] not in {
                "preflight", "dns", "tcp_connect", "tls", "http_request",
                "http_response", "response_body", "local_parse"}:
            raise VerificationError("terminal audit lacks bounded error identity")
        if not isinstance(audit["error_type"], str) or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]{0,127}", audit["error_type"]):
            raise VerificationError("terminal audit error type invalid")
        allowed_counts = {
            "preflight": {(0, 0, 0)},
            "dns": {(1, 0, 0)},
            "tcp_connect": {(1, 0, 0), (1, 1, 0)},
            "tls": {(1, 1, 0)},
            "http_request": {(1, 1, 1)},
            "http_response": {(1, 1, 1)},
            "response_body": {(1, 1, 1)},
            "local_parse": {(1, 1, 1)},
        }
        if (dns_count, tcp_count, http_count) not in allowed_counts[audit["error_stage"]]:
            raise VerificationError("terminal stage/count mismatch")
    else:
        raise VerificationError("audit status invalid")
    return audit


def verify_audit(path: Path) -> dict:
    audit = json.loads(require_regular(path, "audit").read_text(encoding="utf-8"))
    return verify_audit_dict(audit)


def verify_artifact(directory: Path) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        raise VerificationError("artifact path must be a real directory")
    members = {path.name for path in directory.iterdir()}
    if members != ARTIFACT_FILES:
        raise VerificationError(f"artifact member mismatch: {sorted(members)}")
    for path in directory.iterdir():
        require_regular(path, "artifact member")
        if path.suffix.lower() in {".jnlp", ".jar", ".csv"}:
            raise VerificationError("prohibited artifact suffix")
    audit_path = directory / "REMOTE_JNLP_INITIAL_OBSERVATION_AUDIT.json"
    audit = verify_audit(audit_path)
    manifest = (directory / "artifact_manifest_sha256.txt").read_text(encoding="utf-8")
    expected = f"{sha256_file(audit_path)}  REMOTE_JNLP_INITIAL_OBSERVATION_AUDIT.json\n"
    if manifest != expected:
        raise VerificationError("artifact manifest mismatch")
    return audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("static")
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--audit", type=Path, required=True)
    artifact_parser = sub.add_parser("artifact")
    artifact_parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "static":
        value = verify_static()
    elif args.command == "audit":
        value = verify_audit(args.audit)
    else:
        value = verify_artifact(args.directory)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
