#!/usr/bin/env python3
"""Verify Run 33577505327 and its frozen price-free identity inventory."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/remote-libs-jnlp-run-33577505327"
AUDIT_PATH = RESULTS / "REMOTE_LIBS_JNLP_OBSERVATION_AUDIT.json"
MANIFEST_PATH = RESULTS / "artifact_manifest_sha256.txt"
INDEPENDENT_PATH = RESULTS / "REMOTE_LIBS_JNLP_INDEPENDENT_AUDIT.json"
ALLOWLIST_PATH = ROOT / "spec/remote_libs_jnlp_observed_url_allowlist.frozen.json"
V2_VERIFIER_PATH = Path(__file__).with_name(
    "verify_phase9_remote_libs_jnlp_observation_v2.py"
)
EXPECTED = {
    "audit": "d6d59fe9ad976470e1d16debdb7b6d5a9698728c7eeba7d6c4bd977987f26286",
    "manifest": "fb439cee70851dfec847ba3e96060225f1f8d492ced04085a09afac31363ec20",
    "independent": "eef647aea28924804846d6b419c1e09d19f59e84e627978c85391a6500f14357",
    "allowlist": "8cf549593cadeb329e2745421186007ee8e108bdfca3f1c2739c43b52310dee6",
    "artifact_zip": "1611851b165cf126c4feaecf1789f913c556cfdd2bc7f8501c45c13ad352d548",
}


class VerificationError(ValueError):
    pass


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v2 = load_module("phase9_remote_libs_v2_verifier_for_independent", V2_VERIFIER_PATH)


def require_regular(path: Path, label: str) -> Path:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise VerificationError(f"{label} must be a single-link regular file")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_checked(path: Path, expected: str, label: str) -> dict:
    require_regular(path, label)
    if sha256_file(path) != expected:
        raise VerificationError(f"{label} SHA mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_dicts(audit: dict, allowlist: dict, independent: dict) -> dict:
    try:
        v2.v1.verify_audit_dict(audit)
    except Exception as exc:
        raise VerificationError(str(exc)) from exc
    identity = audit["github_identity"]
    if identity != {
        "event_name": "workflow_dispatch",
        "head_sha": "b219af912b4fd5bb195fa9762e4b2a719086a02d",
        "job_name": "observe",
        "ref": "refs/heads/main",
        "run_attempt": "1",
        "run_id": "33577505327",
        "run_number": "1",
    }:
        raise VerificationError("GitHub identity mismatch")
    counts = audit["transport"]
    if tuple(counts[key] for key in (
        "dns_resolution_call_count", "tcp_connect_attempt_count", "http_request_count"
    )) != (1, 1, 1):
        raise VerificationError("transport count mismatch")
    if audit["response"]["status"] != 200:
        raise VerificationError("response status mismatch")
    references = audit["jnlp_identity"]["references"]
    if len(references) != 36 or any(row["fetched"] for row in references):
        raise VerificationError("reference inventory mismatch")
    entries = allowlist.get("entries")
    projected = [
        {key: row[key] for key in (
            "ordinal", "element_local_name", "raw_href", "resolved_url",
            "url_sha256", "fetched", "authorization_status",
        )}
        for row in references
    ]
    if entries != projected:
        raise VerificationError("allowlist entries differ from observed references")
    if allowlist.get("authorization") != {
        "acquisition_authorized": False,
        "any_observed_url_request_authorized": False,
        "availability_query_authorized": False,
        "count_only_authorized": False,
        "downloaded_code_execution_authorized": False,
        "jar_or_resource_request_authorized": False,
        "jforex_connect_authorized": False,
        "jnlp_request_authorized": False,
        "outcome_access_authorized": False,
        "price_access_authorized": False,
        "provider_schedule_query_authorized": False,
        "same_run_allowlist_frozen": False,
    }:
        raise VerificationError("allowlist authorization mismatch")
    if independent["artifact"]["downloaded_zip_sha256"] != EXPECTED["artifact_zip"]:
        raise VerificationError("artifact ZIP mismatch")
    if independent["observation"]["reference_count"] != len(references):
        raise VerificationError("independent reference count mismatch")
    prohibited = independent["prohibited_activity"]
    if prohibited["phase9_price_files_acquired"] != 0:
        raise VerificationError("price file count mismatch")
    if prohibited["research_outcomes_calculated"] or prohibited["outcome_fields"]:
        raise VerificationError("research outcome boundary violated")
    if any(independent["authorization"][key] for key in (
        "retry_authorized", "replay_authorized", "same_run_allowlist_frozen",
        "observed_url_request_authorized", "jar_or_resource_request_authorized",
        "jforex_connect_authorized", "price_acquisition_authorized",
        "count_only_authorized", "outcome_access_authorized",
    )):
        raise VerificationError("downstream authorization unexpectedly enabled")
    return {
        "schema_version": "phase9-remote-libs-jnlp-independent-verification-v1.0",
        "status": "PASS_IDENTITY_INVENTORY_FROZEN_REQUESTS_BLOCKED",
        "run_id": 33577505327,
        "artifact_id": 9827163991,
        "http_request_count": 1,
        "reference_count": 36,
        "all_references_fetched_false": True,
        "phase9_price_files": 0,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def verify() -> dict:
    audit = load_checked(AUDIT_PATH, EXPECTED["audit"], "observation audit")
    allowlist = load_checked(ALLOWLIST_PATH, EXPECTED["allowlist"], "observed URL allowlist")
    independent = load_checked(INDEPENDENT_PATH, EXPECTED["independent"], "independent audit")
    require_regular(MANIFEST_PATH, "artifact manifest")
    if sha256_file(MANIFEST_PATH) != EXPECTED["manifest"]:
        raise VerificationError("artifact manifest SHA mismatch")
    expected_manifest = f"{EXPECTED['audit']}  {AUDIT_PATH.name}\n"
    if MANIFEST_PATH.read_text(encoding="utf-8") != expected_manifest:
        raise VerificationError("artifact manifest content mismatch")
    return verify_dicts(audit, allowlist, independent)


def main() -> int:
    print(json.dumps(verify(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
