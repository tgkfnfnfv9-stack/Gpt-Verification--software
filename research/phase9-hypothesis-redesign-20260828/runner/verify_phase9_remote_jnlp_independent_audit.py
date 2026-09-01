#!/usr/bin/env python3
"""Offline verifier for the independently audited remote-JNLP URL inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json"
ALLOWLIST = ROOT / "spec/remote_jnlp_observed_url_allowlist.frozen.json"
EXPECTED_URLS = [
    "https://platform.dukascopy.com/demo_3/",
    "https://platform.dukascopy.com/demo_3/images/logo/dukascopy-sw_48x48.png",
    "https://platform.dukascopy.com/demo_3/jforex_3.jnlp",
    "https://platform.dukascopy.com/demo_3/libs_3.jnlp",
    "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp",
]
EXPECTED = {
    "source_head": "aa9d46a6a42936042a406bdf339f07d378cc79b7",
    "run_id": 33500446289,
    "job_id": 99832303024,
    "artifact_id": 9797466074,
    "artifact_zip_sha256": "5a0339a026ea2ac0a7382b3ad7e0510a303609ab8817d55a268b55108415b8d2",
    "observation_audit_sha256": "d577bfc7e8588de5dcc873393b250a4514d3d0e0ff013e59dcbeabc46d10e1bb",
    "artifact_manifest_sha256": "d8173e584491a4d8190a27ade555385e5c07e17db31371ef4342eec66a237d0f",
    "body_sha256": "4e5adcbb29116e7f17b3babfc4aa47590d06baca50a98745d300d4824a1a70e9",
    "tls_certificate_sha256": "616df88e991b3d1f0ca1183d5155a243d7dfceb0b3f1461cb4f400d43b6003df",
    "url_set_sha256": "72fe580e020440cb273c56eef77b73982b78fb3843b33c1ac32e119b767790ee",
}
FALSE_AUTH_KEYS = {
    "any_url_in_this_file_may_be_requested",
    "extension_jnlp_request_authorized",
    "icon_request_authorized",
    "recursive_resource_request_authorized",
    "downloaded_code_execution_authorized",
    "credentials_may_be_referenced",
    "jforex_connect_authorized",
    "provider_schedule_query_authorized",
    "availability_query_authorized",
    "price_access_authorized",
    "acquisition_authorized",
    "count_only_authorized",
    "outcome_access_authorized",
}
PROHIBITED_RAW_KEYS = {
    "raw_jnlp", "raw_jnlp_bytes", "response_body", "body_base64",
    "jar_bytes", "credentials", "password", "secret",
}


class AuditError(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_regular(path: Path, label: str) -> Path:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise AuditError(f"{label} must be a single-link regular file")
    return path


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def require_sha256(value, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise AuditError(f"{label} is not SHA-256")


def require_int(value, expected: int, label: str) -> None:
    if type(value) is not int or value != expected:
        raise AuditError(f"{label} integer identity mismatch")


def require_exact_keys(value: dict, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        missing = sorted(expected - set(value)) if isinstance(value, dict) else sorted(expected)
        extra = sorted(set(value) - expected) if isinstance(value, dict) else []
        raise AuditError(f"{label} schema mismatch; missing={missing}, extra={extra}")


def load_json(path: Path, label: str) -> dict:
    value = json.loads(require_regular(path, label).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditError(f"{label} root must be an object")
    if PROHIBITED_RAW_KEYS.intersection(walk_keys(value)):
        raise AuditError(f"{label} contains a prohibited raw/secret key")
    return value


def verify_values(audit: dict, allowlist: dict) -> dict:
    for label, value in (("independent audit", audit), ("allowlist", allowlist)):
        if not isinstance(value, dict):
            raise AuditError(f"{label} root must be an object")
        prohibited = PROHIBITED_RAW_KEYS.intersection(walk_keys(value))
        if prohibited:
            raise AuditError(
                f"{label} contains a prohibited raw/secret key: {sorted(prohibited)[0]}"
            )
    require_exact_keys(audit, {
        "schema_version", "status", "audited_at_utc", "implementation",
        "github_actions", "artifact_custody", "observation", "authorization",
        "scientific_state",
    }, "independent audit")
    if audit.get("schema_version") != "phase9-remote-jnlp-independent-audit-v1.0":
        raise AuditError("independent audit schema mismatch")
    if audit.get("status") != "PASS_IDENTITY_ONLY_FOLLOWUP_BLOCKED":
        raise AuditError("independent audit status mismatch")
    if audit.get("audited_at_utc") != "2026-09-01T11:05:00Z":
        raise AuditError("independent audit timestamp mismatch")
    implementation = audit["implementation"]
    require_exact_keys(implementation, {
        "commit_sha", "tree_sha", "parent_sha", "gate_sha256",
    }, "implementation")
    if implementation != {
        "commit_sha": EXPECTED["source_head"],
        "tree_sha": "5a0eb282c45137a6a4d24785651b3a61bff2f441",
        "parent_sha": "84df3eb489dba32a22957165f3bb324f63a7c367",
        "gate_sha256": "c1749720fd6f5a906b8dbcc7a285f88326a6c089ecba0dfa80191e56729c98bc",
    }:
        raise AuditError("implementation identity mismatch")
    actions = audit["github_actions"]
    require_exact_keys(actions, {
        "run_id", "run_number", "run_attempt", "event", "head_sha", "ref",
        "conclusion", "job_id", "job_name", "job_conclusion", "artifact_id",
        "artifact_name", "artifact_size_in_bytes",
        "github_artifact_digest_sha256", "independently_downloaded_zip_sha256",
    }, "GitHub Actions identity")
    expected_actions = {
        "run_id": EXPECTED["run_id"], "run_number": 1, "run_attempt": 1,
        "event": "workflow_dispatch", "head_sha": EXPECTED["source_head"],
        "ref": "refs/heads/main", "conclusion": "success",
        "job_id": EXPECTED["job_id"], "job_name": "observe",
        "job_conclusion": "success", "artifact_id": EXPECTED["artifact_id"],
    }
    if any(actions.get(key) != value for key, value in expected_actions.items()):
        raise AuditError("GitHub Run/Job/Artifact identity mismatch")
    for key, expected in (
        ("run_id", EXPECTED["run_id"]), ("run_number", 1), ("run_attempt", 1),
        ("job_id", EXPECTED["job_id"]), ("artifact_id", EXPECTED["artifact_id"]),
        ("artifact_size_in_bytes", 2285),
    ):
        require_int(actions.get(key), expected, f"GitHub Actions {key}")
    if actions.get("github_artifact_digest_sha256") != EXPECTED["artifact_zip_sha256"]:
        raise AuditError("GitHub Artifact digest mismatch")
    if actions.get("independently_downloaded_zip_sha256") != EXPECTED["artifact_zip_sha256"]:
        raise AuditError("independent ZIP SHA mismatch")
    if actions.get("artifact_name") != (
            "phase9-remote-jnlp-initial-observation-"
            f"{EXPECTED['source_head']}-{EXPECTED['run_id']}-1"):
        raise AuditError("Artifact name mismatch")
    if actions.get("artifact_size_in_bytes") != 2285:
        raise AuditError("Artifact size mismatch")
    custody = audit["artifact_custody"]
    require_exact_keys(custody, {
        "exact_member_count", "exact_members", "observation_audit_sha256",
        "artifact_manifest_sha256", "inner_manifest_verified",
        "raw_jnlp_bytes_present", "jar_present", "market_csv_present",
    }, "Artifact custody")
    if custody.get("exact_members") != [
            "REMOTE_JNLP_INITIAL_OBSERVATION_AUDIT.json", "artifact_manifest_sha256.txt"]:
        raise AuditError("Artifact exact member set mismatch")
    if custody.get("exact_member_count") != 2 or custody.get("inner_manifest_verified") is not True:
        raise AuditError("Artifact custody proof mismatch")
    require_int(custody.get("exact_member_count"), 2, "Artifact member count")
    if custody.get("observation_audit_sha256") != EXPECTED["observation_audit_sha256"]:
        raise AuditError("observation audit SHA mismatch")
    if custody.get("artifact_manifest_sha256") != EXPECTED["artifact_manifest_sha256"]:
        raise AuditError("Artifact manifest SHA mismatch")
    for key in ("raw_jnlp_bytes_present", "jar_present", "market_csv_present"):
        if custody.get(key) is not False:
            raise AuditError(f"prohibited Artifact content flag set: {key}")
    observation = audit["observation"]
    require_exact_keys(observation, {
        "attempt_started_at_utc", "exact_request_url", "method",
        "dns_resolution_call_count", "tcp_connect_attempt_count",
        "http_request_count", "selected_peer_ip", "selected_peer_port",
        "resolved_address_count", "resolved_address_set_sha256", "tls_version",
        "tls_cipher", "tls_peer_certificate_sha256", "response_status",
        "response_content_type", "response_last_modified",
        "response_entity_body_bytes", "response_entity_body_sha256",
        "body_identity_semantics", "redirect_location", "redirect_followed",
        "recursive_resource_fetch_count", "local_jnlp_parse_status",
        "observed_href_reference_count", "observed_href_reference_list_sha256",
    }, "observation")
    expected_observation_identity = {
        "attempt_started_at_utc": "2026-09-01T11:02:39.601283Z",
        "exact_request_url": "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp",
        "method": "GET", "selected_peer_ip": "3.168.2.101",
        "selected_peer_port": 443, "resolved_address_count": 12,
        "resolved_address_set_sha256": "949b7ad26c2a8b4a8815ebd8a47a47dd6fb6350d6147f2a3a2992e7a042c9cc8",
        "tls_version": "TLSv1.3", "tls_cipher": "TLS_AES_128_GCM_SHA256",
        "response_content_type": "application/x-java-jnlp-file",
        "response_last_modified": "Fri, 16 Feb 2024 07:55:13 GMT",
        "body_identity_semantics": "HTTP_ENTITY_BODY_AFTER_TRANSFER_DECODING_BEFORE_CONTENT_DECODING",
        "redirect_location": None,
        "local_jnlp_parse_status": "PARSED_LOCAL_IDENTITY_ONLY",
        "observed_href_reference_list_sha256": "2d11c08d52520447b86147ca9305aa9911851f54d51b039dd30c0e1a2f36c134",
    }
    if any(observation.get(key) != value for key, value in expected_observation_identity.items()):
        raise AuditError("observed response/network identity mismatch")
    if (observation.get("dns_resolution_call_count"), observation.get("tcp_connect_attempt_count"),
            observation.get("http_request_count")) != (1, 1, 1):
        raise AuditError("observation transport count mismatch")
    for key, expected in (
        ("dns_resolution_call_count", 1), ("tcp_connect_attempt_count", 1),
        ("http_request_count", 1), ("selected_peer_port", 443),
        ("resolved_address_count", 12), ("response_status", 200),
        ("response_entity_body_bytes", 2445), ("recursive_resource_fetch_count", 0),
        ("observed_href_reference_count", 3),
    ):
        require_int(observation.get(key), expected, f"observation {key}")
    if observation.get("response_status") != 200 or observation.get("response_entity_body_bytes") != 2445:
        raise AuditError("response identity mismatch")
    if observation.get("response_entity_body_sha256") != EXPECTED["body_sha256"]:
        raise AuditError("response body SHA mismatch")
    if observation.get("tls_peer_certificate_sha256") != EXPECTED["tls_certificate_sha256"]:
        raise AuditError("TLS certificate SHA mismatch")
    if observation.get("redirect_followed") is not False or observation.get("recursive_resource_fetch_count") != 0:
        raise AuditError("redirect or recursive resource access detected")
    if observation.get("observed_href_reference_count") != 3:
        raise AuditError("observed href reference count mismatch")
    auth = audit["authorization"]
    require_exact_keys(auth, {
        "single_use_authorization_consumed",
        "external_jnlp_observation_authorized_after_run", "retry_authorized",
        "replay_authorized", "followup_url_request_authorized",
        "jforex_connect_authorized", "provider_schedule_query_authorized",
        "availability_query_authorized", "price_access_authorized",
        "acquisition_authorized", "count_only_authorized",
        "outcome_access_authorized", "authorization_effect",
    }, "post-run authorization")
    if auth.get("single_use_authorization_consumed") is not True:
        raise AuditError("single-use authorization not consumed")
    for key, value in auth.items():
        if key not in {"single_use_authorization_consumed", "authorization_effect"} and value is not False:
            raise AuditError(f"post-run authorization is not false: {key}")
    if auth.get("authorization_effect") != "NONE":
        raise AuditError("observation has an authorization effect")
    scientific = audit["scientific_state"]
    if scientific != {
        "provider_schedule_files": 0, "phase9_price_files": 0,
        "forbidden_market_period_request_attempted": False,
        "research_outcomes_calculated": False, "outcome_fields": [],
    }:
        raise AuditError("scientific state mismatch")

    require_exact_keys(allowlist, {
        "schema_version", "status", "recorded_at_utc", "source",
        "freeze_separation", "canonical_exact_string_set",
        "canonical_exact_string_set_sha256", "entries", "network_identity_policy",
        "authorization", "scientific_state",
    }, "observed URL allowlist")
    if allowlist.get("schema_version") != "phase9-remote-jnlp-observed-url-allowlist-v1.0":
        raise AuditError("observed URL allowlist schema mismatch")
    if allowlist.get("status") != "FROZEN_EXACT_MATCH_EVIDENCE_ONLY_ALL_FOLLOWUP_REQUESTS_BLOCKED":
        raise AuditError("observed URL allowlist status mismatch")
    if allowlist.get("recorded_at_utc") != "2026-09-01T11:15:11Z":
        raise AuditError("allowlist freeze timestamp mismatch")
    source = allowlist["source"]
    require_exact_keys(source, {
        "observation_head_sha", "run_id", "job_id", "artifact_id",
        "artifact_zip_sha256", "observation_audit_sha256", "independent_audit",
    }, "allowlist source")
    if (source.get("observation_head_sha"), source.get("run_id"), source.get("job_id"),
            source.get("artifact_id"), source.get("artifact_zip_sha256"),
            source.get("observation_audit_sha256")) != (
                EXPECTED["source_head"], EXPECTED["run_id"], EXPECTED["job_id"],
                EXPECTED["artifact_id"], EXPECTED["artifact_zip_sha256"],
                EXPECTED["observation_audit_sha256"]):
        raise AuditError("allowlist source identity mismatch")
    if source.get("independent_audit") != (
            "results/remote-jnlp-run-33500446289/REMOTE_JNLP_INDEPENDENT_AUDIT.json"):
        raise AuditError("allowlist independent audit path mismatch")
    freeze = allowlist["freeze_separation"]
    if freeze != {
        "allowlist_created_in_source_observation_run": False,
        "source_run_self_authorized": False,
        "strictly_later_commit_required": True,
        "required_freeze_parent_sha": EXPECTED["source_head"],
        "source_run_head_must_be_strict_ancestor_of_freeze_commit": True,
        "followup_execution_requires_separate_user_approval": True,
    }:
        raise AuditError("separate-commit freeze rule mismatch")
    urls = allowlist["canonical_exact_string_set"]
    if urls != EXPECTED_URLS or urls != sorted(set(urls)):
        raise AuditError("canonical exact URL set mismatch")
    aggregate = sha256_bytes(("\n".join(sorted(urls)) + "\n").encode("utf-8"))
    if aggregate != EXPECTED["url_set_sha256"] or allowlist.get("canonical_exact_string_set_sha256") != aggregate:
        raise AuditError("canonical exact URL set SHA mismatch")
    entries = allowlist["entries"]
    if not isinstance(entries, list) or len(entries) != 5:
        raise AuditError("allowlist entry count mismatch")
    expected_entries = [
        ("AUTHORIZED_INITIAL_REQUEST_NOW_CONSUMED", EXPECTED_URLS[4],
         "request_scope.url", 1),
        ("OBSERVED_CODEBASE_NOT_REQUESTED", EXPECTED_URLS[0],
         "jnlp_identity.root_codebase", 0),
        ("OBSERVED_ROOT_HREF_NOT_REQUESTED_AS_EXACT_STRING", EXPECTED_URLS[2],
         "jnlp_identity.references[0].resolved_url", 0),
        ("OBSERVED_ICON_HREF_NOT_REQUESTED", EXPECTED_URLS[1],
         "jnlp_identity.references[1].resolved_url", 0),
        ("OBSERVED_EXTENSION_HREF_NOT_REQUESTED", EXPECTED_URLS[3],
         "jnlp_identity.references[2].resolved_url", 0),
    ]
    for row, (kind, url, source_field, request_count) in zip(entries, expected_entries):
        require_exact_keys(row, {
            "kind", "exact_url", "url_sha256", "source_field",
            "request_count_in_source_run", "request_authorized_after_source_run",
        }, "allowlist entry")
        if (row.get("kind"), row.get("exact_url"), row.get("source_field"),
                row.get("request_count_in_source_run")) != (
                    kind, url, source_field, request_count):
            raise AuditError("allowlist entry identity mismatch")
        require_int(row.get("request_count_in_source_run"), request_count,
                    "allowlist entry request count")
    if {row.get("exact_url") for row in entries} != set(urls):
        raise AuditError("allowlist entry URL set mismatch")
    if sum(row.get("request_count_in_source_run", -1) for row in entries) != 1:
        raise AuditError("source request count across entries mismatch")
    for row in entries:
        url = row["exact_url"]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != "platform.dukascopy.com":
            raise AuditError("observed URL scheme/host mismatch")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AuditError("observed URL userinfo/query/fragment prohibited")
        if row.get("url_sha256") != sha256_bytes(url.encode("utf-8")):
            raise AuditError("observed URL SHA mismatch")
        if row.get("request_authorized_after_source_run") is not False:
            raise AuditError("followup request authorization detected")
    authorization = allowlist["authorization"]
    require_exact_keys(authorization, {"initial_observation_authorization_consumed"} | FALSE_AUTH_KEYS,
                       "allowlist authorization")
    if authorization.get("initial_observation_authorization_consumed") is not True:
        raise AuditError("allowlist lost consumed authorization record")
    for key in FALSE_AUTH_KEYS:
        if authorization.get(key) is not False:
            raise AuditError(f"allowlist authorization is not false: {key}")
    if allowlist["network_identity_policy"] != {
        "observed_dns_addresses_are_authoritative_ip_allowlist": False,
        "dns_ip_allowlist_frozen": False,
        "tls_hostname_verification_required_for_any_future_approved_request": True,
        "redirect_following_authorized": False,
    }:
        raise AuditError("network identity policy mismatch")
    if allowlist["scientific_state"] != {
        "provider_schedule_files": 0, "phase9_price_files": 0,
        "research_outcomes_calculated": False, "outcome_fields": [],
    }:
        raise AuditError("allowlist scientific state mismatch")
    return {
        "schema_version": "phase9-remote-jnlp-independent-verification-v1.0",
        "status": "PASS_EXACT_URLS_FROZEN_FOLLOWUP_BLOCKED",
        "source_run_id": EXPECTED["run_id"],
        "source_job_id": EXPECTED["job_id"],
        "source_artifact_id": EXPECTED["artifact_id"],
        "source_artifact_zip_sha256": EXPECTED["artifact_zip_sha256"],
        "canonical_exact_url_count": len(urls),
        "canonical_exact_url_set_sha256": aggregate,
        "followup_request_authorized": False,
        "jforex_connect_authorized": False,
        "provider_schedule_query_authorized": False,
        "price_access_authorized": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def verify(audit_path: Path = AUDIT, allowlist_path: Path = ALLOWLIST) -> dict:
    return verify_values(load_json(audit_path, "independent audit"), load_json(allowlist_path, "allowlist"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST)
    args = parser.parse_args(argv)
    print(json.dumps(verify(args.audit, args.allowlist), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
