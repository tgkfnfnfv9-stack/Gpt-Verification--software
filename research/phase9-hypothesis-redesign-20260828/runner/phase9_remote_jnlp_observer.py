#!/usr/bin/env python3
"""Single-use Phase 9 initial JNLP identity observer.

This program performs at most one DNS resolution call, one TCP connect attempt,
and one HTTP GET to the exact frozen initial URL.  It never follows redirects,
fetches referenced resources, writes the response body, or executes code.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import sys
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET
from xml.parsers import expat


EXACT_CONFIRMATION = "OBSERVE_PHASE9_REMOTE_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS"
EXACT_URL = "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp"
EXACT_HOST = "platform.dukascopy.com"
EXACT_PORT = 443
EXACT_PATH = "/demo_3/jforex_3.jnlp"
MAX_BODY_BYTES = 2_097_152
MAX_URL_REFERENCES = 1_024
MAX_URL_CHARS = 4_096
REDIRECT_STATUSES = {300, 301, 302, 303, 307, 308}
SAFE_RESPONSE_HEADERS = {
    "content-type", "content-encoding", "content-length", "etag",
    "last-modified", "location",
}


class ObservationError(RuntimeError):
    """A bounded, non-retryable observation failure."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_regular_file(path: Path, label: str) -> Path:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ObservationError(f"{label} must be a single-link regular file")
    return path.resolve(strict=True)


def validate_gate(path: Path) -> tuple[dict, str]:
    gate_path = require_regular_file(path, "gate")
    raw = gate_path.read_bytes()
    gate = json.loads(raw)
    if gate.get("schema_version") != "phase9-remote-jnlp-initial-observation-gate-v1.0":
        raise ObservationError("unexpected gate schema")
    approval = gate.get("single_use_authorization", {})
    scope = gate.get("exact_scope", {})
    adjacent = gate.get("adjacent_authorizations", {})
    same_run = gate.get("same_run_rules", {})
    artifact = gate.get("artifact_policy", {})
    scientific = gate.get("scientific_state", {})
    required = {
        "user_approved": True,
        "workflow_dispatch_authorized_once": True,
        "required_github_run_number": 1,
        "required_github_run_attempt": 1,
        "retry_authorized": False,
        "replay_authorized": False,
    }
    if any(approval.get(key) != value for key, value in required.items()):
        raise ObservationError("single-use authorization mismatch")
    expected_scope = {
        "initial_url": EXACT_URL,
        "allowed_urls_exact_set": [EXACT_URL],
        "scheme": "https", "host": EXACT_HOST, "port": EXACT_PORT,
        "path": EXACT_PATH, "query": "", "fragment": "", "userinfo": "",
        "method": "GET", "dns_resolution_call_count_max": 1,
        "tcp_connect_attempt_count_max": 1, "http_request_count_max": 1,
        "response_body_bytes_max": MAX_BODY_BYTES, "follow_redirects": False,
        "redirect_location_record_only": True, "recursive_resource_fetch": False,
        "credentials": "NONE", "proxy_use": False,
        "execute_downloaded_code": False,
        "local_jnlp_identity_parse_if_status_200_and_identity_encoding": True,
    }
    if any(scope.get(key) != value for key, value in expected_scope.items()):
        raise ObservationError("exact observation scope mismatch")
    parsed = urlsplit(scope["initial_url"])
    if (parsed.scheme, parsed.hostname, parsed.port, parsed.path, parsed.query,
            parsed.fragment, parsed.username, parsed.password) != (
                "https", EXACT_HOST, EXACT_PORT, EXACT_PATH, "", "", None, None):
        raise ObservationError("exact URL decomposition mismatch")
    if any(value is not False for value in adjacent.values()):
        raise ObservationError("an adjacent authorization is not false")
    if any(same_run.get(key) is not False for key in (
        "observation_may_self_authorize",
        "same_run_integrity_check_is_authoritative_independent_audit",
        "observation_may_freeze_runtime_allowlist",
        "observation_may_authorize_followup_url_requests",
        "observation_may_authorize_jforex_connection",
    )):
        raise ObservationError("same-run prohibition mismatch")
    if artifact.get("raw_jnlp_bytes_may_be_written_to_disk") is not False:
        raise ObservationError("raw-body disk policy mismatch")
    if scientific != {
        "phase9_price_files": 0, "provider_schedule_files": 0,
        "research_outcomes_calculated": False, "outcome_fields": [],
    }:
        raise ObservationError("scientific state mismatch")
    return gate, sha256_bytes(raw)


def normalize_addresses(rows: list[tuple]) -> list[dict]:
    output: dict[tuple[int, str, int, int], dict] = {}
    for family, socktype, proto, _canonname, sockaddr in rows:
        if socktype != socket.SOCK_STREAM or family not in (socket.AF_INET, socket.AF_INET6):
            continue
        address = str(ipaddress.ip_address(sockaddr[0]))
        port = int(sockaddr[1])
        scope_id = int(sockaddr[3]) if family == socket.AF_INET6 else 0
        key = (family, address, port, scope_id)
        output[key] = {
            "family": "AF_INET" if family == socket.AF_INET else "AF_INET6",
            "address": address,
            "port": port,
            "scope_id": scope_id,
            "socket_family": family,
            "protocol": proto,
            "sockaddr": sockaddr,
        }
    values = list(output.values())
    values.sort(key=lambda row: (row["family"] != "AF_INET", row["address"], row["scope_id"]))
    if not values or any(row["port"] != EXACT_PORT for row in values):
        raise ObservationError("DNS resolution did not yield an exact-port address")
    return values


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_jnlp_identity(body: bytes, content_encoding: str) -> dict:
    if content_encoding.lower().strip() not in ("", "identity"):
        return {
            "status": "SKIPPED_NON_IDENTITY_CONTENT_ENCODING",
            "reference_count": 0,
            "references": [],
            "reference_list_sha256": sha256_bytes(b"[]\n"),
        }
    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ObservationError("DTD or entity declaration prohibited")
    hardened = expat.ParserCreate()
    def reject_xml_feature(*_args):
        raise ObservationError("active XML feature prohibited")
    hardened.StartDoctypeDeclHandler = reject_xml_feature
    hardened.EntityDeclHandler = reject_xml_feature
    hardened.ExternalEntityRefHandler = reject_xml_feature
    hardened.SkippedEntityHandler = reject_xml_feature
    hardened.ProcessingInstructionHandler = reject_xml_feature
    try:
        hardened.Parse(body, True)
    except expat.ExpatError as exc:
        raise ObservationError("response body is not well-formed XML") from exc
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ObservationError("response body is not well-formed XML") from exc
    if _local_name(root.tag) != "jnlp":
        raise ObservationError("response XML root is not jnlp")
    for element in root.iter():
        namespace = element.tag[1:].split("}", 1)[0] if element.tag.startswith("{") else ""
        if namespace == "http://www.w3.org/2001/XInclude":
            raise ObservationError("XInclude prohibited")
    codebase = root.attrib.get("codebase", "")
    root_href = root.attrib.get("href", "")
    for value in (codebase, root_href):
        if len(value) > MAX_URL_CHARS:
            raise ObservationError("JNLP URL attribute too long")
    base = urljoin(EXACT_URL, codebase) if codebase else EXACT_URL
    references: list[dict] = []
    for element in root.iter():
        if "href" not in element.attrib:
            continue
        raw_href = element.attrib["href"]
        if len(raw_href) > MAX_URL_CHARS:
            raise ObservationError("JNLP href too long")
        resolved = urljoin(base, raw_href)
        if len(resolved) > MAX_URL_CHARS:
            raise ObservationError("resolved JNLP URL too long")
        references.append({
            "ordinal": len(references),
            "element_local_name": _local_name(element.tag),
            "raw_href": raw_href,
            "resolved_url": resolved,
            "url_sha256": sha256_bytes(resolved.encode("utf-8")),
            "fetched": False,
            "authorization_status": "OBSERVED_ONLY_NOT_ALLOWED",
        })
        if len(references) > MAX_URL_REFERENCES:
            raise ObservationError("too many JNLP URL references")
    canonical = json.dumps(references, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8") + b"\n"
    return {
        "status": "PARSED_LOCAL_IDENTITY_ONLY",
        "root_codebase": codebase,
        "root_href": root_href,
        "reference_count": len(references),
        "references": references,
        "reference_list_sha256": sha256_bytes(canonical),
    }


def safe_headers(response: http.client.HTTPResponse) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for name in sorted(SAFE_RESPONSE_HEADERS):
        values = response.headers.get_all(name, [])
        if values:
            if any(len(value) > MAX_URL_CHARS for value in values) or len(values) > 8:
                raise ObservationError("response header bounds exceeded")
            output[name] = values
    return output


def read_status_200_body(response: http.client.HTTPResponse) -> bytes:
    lengths = response.headers.get_all("Content-Length", [])
    if len(lengths) > 1:
        raise ObservationError("multiple Content-Length headers prohibited")
    if lengths:
        try:
            declared = int(lengths[0], 10)
        except ValueError as exc:
            raise ObservationError("invalid Content-Length") from exc
        if declared < 0 or declared > MAX_BODY_BYTES:
            raise ObservationError("declared response body exceeds cap")
    transfers = response.headers.get_all("Transfer-Encoding", [])
    if transfers and lengths:
        raise ObservationError("Transfer-Encoding with Content-Length prohibited")
    if transfers and (len(transfers) != 1 or transfers[0].strip().lower() != "chunked"):
        raise ObservationError("unsupported Transfer-Encoding")
    body = response.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        raise ObservationError("response body exceeds cap")
    if lengths and len(body) != int(lengths[0], 10):
        raise ObservationError("response body length mismatch")
    return body


def base_audit(gate_sha256: str, args: argparse.Namespace) -> dict:
    return {
        "schema_version": "phase9-remote-jnlp-initial-observation-audit-v1.0",
        "attempt_started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED",
        "authorization": {
            "exact_confirmation_matched": args.confirmation == EXACT_CONFIRMATION,
            "single_use_authorization_consumed": True,
            "external_jnlp_observation_authorized_after_run": False,
            "retry_authorized": False,
            "replay_authorized": False,
            "gate_sha256": gate_sha256,
        },
        "github_identity": {
            "event_name": args.github_event_name,
            "ref": args.github_ref,
            "head_sha": args.github_sha,
            "run_id": args.github_run_id,
            "run_number": args.github_run_number,
            "run_attempt": args.github_run_attempt,
            "job_name": args.github_job,
        },
        "request_scope": {
            "url": EXACT_URL, "method": "GET",
            "response_body_bytes_max": MAX_BODY_BYTES,
            "credentials": "NONE", "proxy_used": False,
            "redirect_followed": False, "recursive_resource_fetch_count": 0,
            "downloaded_code_executed": False,
        },
        "transport": {
            "dns_resolution_call_count": 0,
            "tcp_connect_attempt_count": 0,
            "http_request_count": 0,
            "resolved_addresses": [],
            "selected_address": None,
            "peer": None,
            "tls_version": None,
            "tls_cipher": None,
            "tls_peer_certificate_sha256": None,
        },
        "response": {
            "status": None, "reason": None, "safe_headers": {},
            "redirect_location": None, "body_bytes_if_status_200": None,
            "body_sha256_if_status_200": None,
            "body_identity_semantics": "HTTP_ENTITY_BODY_AFTER_TRANSFER_DECODING_BEFORE_CONTENT_DECODING",
        },
        "jnlp_identity": {
            "status": "NOT_PARSED", "reference_count": 0,
            "references": [], "reference_list_sha256": sha256_bytes(b"[]\n"),
        },
        "prohibited_activity": {
            "credentials_referenced": False,
            "jforex_connect_invoked": False,
            "provider_schedule_request_attempted": False,
            "availability_request_attempted": False,
            "market_price_request_attempted": False,
            "forbidden_market_period_request_attempted": False,
            "market_cache_persisted": False,
            "phase9_price_files_acquired": 0,
            "provider_schedule_files_acquired": 0,
            "research_outcomes_calculated": False,
            "outcome_fields": [],
        },
        "authorization_effect": "NONE",
        "same_run_allowlist_frozen": False,
        "error_stage": None,
        "error_type": None,
    }


def observe(args: argparse.Namespace, gate_sha256: str) -> dict:
    audit = base_audit(gate_sha256, args)
    stage = "preflight"
    try:
        if args.confirmation != EXACT_CONFIRMATION:
            raise ObservationError("exact confirmation mismatch")
        if args.github_event_name != "workflow_dispatch" or args.github_ref != "refs/heads/main":
            raise ObservationError("workflow identity mismatch")
        if args.github_run_number != "1" or args.github_run_attempt != "1":
            raise ObservationError("single-use workflow identity mismatch")
        if len(args.github_sha) != 40 or any(ch not in "0123456789abcdef" for ch in args.github_sha):
            raise ObservationError("invalid GitHub head SHA")

        stage = "dns"
        audit["transport"]["dns_resolution_call_count"] = 1
        rows = socket.getaddrinfo(EXACT_HOST, EXACT_PORT, type=socket.SOCK_STREAM)
        addresses = normalize_addresses(rows)
        public_addresses = [
            {key: row[key] for key in ("family", "address", "port", "scope_id")}
            for row in addresses
        ]
        audit["transport"]["resolved_addresses"] = public_addresses
        selected = addresses[0]

        stage = "tcp_connect"
        raw_sock = socket.socket(selected["socket_family"], socket.SOCK_STREAM, selected["protocol"])
        try:
            raw_sock.settimeout(args.timeout_seconds)
            audit["transport"]["selected_address"] = public_addresses[0]
            audit["transport"]["tcp_connect_attempt_count"] = 1
            raw_sock.connect(selected["sockaddr"])
            stage = "tls"
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            context.keylog_filename = None
            with context.wrap_socket(raw_sock, server_hostname=EXACT_HOST) as tls_sock:
                peer = tls_sock.getpeername()
                peer_identity = {
                    "address": str(ipaddress.ip_address(peer[0])), "port": int(peer[1])
                }
                if peer_identity["address"] != selected["address"] or int(peer[1]) != EXACT_PORT:
                    raise ObservationError("TLS peer differs from selected address")
                certificate = tls_sock.getpeercert(binary_form=True)
                if not certificate:
                    raise ObservationError("TLS peer certificate unavailable")
                tls_version = tls_sock.version()
                cipher = tls_sock.cipher()
                if not tls_version or not cipher:
                    raise ObservationError("TLS negotiated identity unavailable")
                audit["transport"]["peer"] = peer_identity
                audit["transport"]["tls_peer_certificate_sha256"] = sha256_bytes(certificate)
                audit["transport"]["tls_version"] = tls_version
                audit["transport"]["tls_cipher"] = list(cipher)

                stage = "http_request"
                request = (
                    f"GET {EXACT_PATH} HTTP/1.1\r\n"
                    f"Host: {EXACT_HOST}:{EXACT_PORT}\r\n"
                    "User-Agent: Phase9-JNLP-Identity-Observer/1.0\r\n"
                    "Accept: application/x-java-jnlp-file, application/xml, text/xml\r\n"
                    "Accept-Encoding: identity\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
                audit["transport"]["http_request_count"] = 1
                tls_sock.sendall(request)

                stage = "http_response"
                response = http.client.HTTPResponse(tls_sock)
                response.begin()
                audit["response"]["status"] = response.status
                reason = response.reason or ""
                audit["response"]["reason"] = reason[:128] if reason.isascii() else None
                locations = response.headers.get_all("Location", [])
                if len(locations) > 1:
                    raise ObservationError("multiple Location headers prohibited")
                if response.status in REDIRECT_STATUSES:
                    audit["response"]["redirect_location"] = locations[0] if locations else None
                    audit["response"]["safe_headers"] = ({"location": locations} if locations else {})
                    audit["status"] = "REDIRECT_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED"
                elif response.status == 200:
                    audit["response"]["safe_headers"] = safe_headers(response)
                    stage = "response_body"
                    body = read_status_200_body(response)
                    audit["response"]["body_bytes_if_status_200"] = len(body)
                    audit["response"]["body_sha256_if_status_200"] = sha256_bytes(body)
                    encodings = response.headers.get_all("Content-Encoding", [])
                    if len(encodings) > 1:
                        raise ObservationError("multiple Content-Encoding headers prohibited")
                    encoding = encodings[0] if encodings else ""
                    stage = "local_parse"
                    audit["jnlp_identity"] = parse_jnlp_identity(body, encoding)
                    audit["status"] = "INITIAL_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED"
                else:
                    audit["status"] = "NON_200_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED"
        finally:
            raw_sock.close()
    except Exception as exc:  # evidence must survive any terminal first attempt
        audit["status"] = "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED"
        audit["error_stage"] = stage
        audit["error_type"] = type(exc).__name__
    return audit


def write_new_json(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        raise ObservationError("output path must not exist")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--github-event-name", required=True)
    parser.add_argument("--github-ref", required=True)
    parser.add_argument("--github-sha", required=True)
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--github-run-number", required=True)
    parser.add_argument("--github-run-attempt", required=True)
    parser.add_argument("--github-job", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args(argv)
    if not 1.0 <= args.timeout_seconds <= 30.0:
        parser.error("timeout must be between 1 and 30 seconds")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _gate, gate_sha256 = validate_gate(args.gate)
    audit = observe(args, gate_sha256)
    write_new_json(args.output, audit)
    print(json.dumps({
        "status": audit["status"],
        "http_request_count": audit["transport"]["http_request_count"],
        "response_status": audit["response"]["status"],
        "raw_body_persisted": False,
        "followup_authorized": False,
    }, sort_keys=True))
    return 0 if audit["error_type"] is None else 1


if __name__ == "__main__":
    sys.exit(main())
