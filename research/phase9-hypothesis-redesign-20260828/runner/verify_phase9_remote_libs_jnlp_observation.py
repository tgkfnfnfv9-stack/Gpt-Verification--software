#!/usr/bin/env python3
"""Verify the one-shot libs_3.jnlp identity Gate and price-free evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "spec/remote_libs_jnlp_observation_gate.frozen.json"
AMENDMENT = ROOT / "JFOREX_REMOTE_LIBS_JNLP_OBSERVATION_AMENDMENT.md"
WORKFLOW = ROOT.parents[1] / ".github/workflows/phase9-remote-libs-jnlp-observation.yml"
OBSERVER_PATH = Path(__file__).with_name("phase9_remote_libs_jnlp_observer.py")
BASE_VERIFIER_PATH = Path(__file__).with_name("verify_phase9_remote_jnlp_observation.py")
EXPECTED_GATE_SHA256 = "31c42edf4a5d4e9c16c09f8f8922ffd8e8291ed7bea5714fc896a6205fb9b7e9"
EXPECTED_AMENDMENT_SHA256 = "4a7ead958ed891d7d1a6a65cd865be528d216458cf04a929af7ceaf4e585f53c"
EXACT_CONFIRMATION = "OBSERVE_PHASE9_REMOTE_LIBS_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS"
EXACT_URL = "https://platform.dukascopy.com/demo_3/libs_3.jnlp"
AUDIT_FILE = "REMOTE_LIBS_JNLP_OBSERVATION_AUDIT.json"
ARTIFACT_FILES = {AUDIT_FILE, "artifact_manifest_sha256.txt"}
STATUS_TO_BASE = {
    "LIBS_IDENTITY_OBSERVED_RESOURCE_REQUESTS_BLOCKED":
        "INITIAL_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED",
    "LIBS_REDIRECT_IDENTITY_OBSERVED_BLOCKED":
        "REDIRECT_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED",
    "LIBS_NON_200_IDENTITY_OBSERVED_BLOCKED":
        "NON_200_IDENTITY_OBSERVED_FOLLOWUP_BLOCKED",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observer = load_module("phase9_remote_libs_observer_verify", OBSERVER_PATH)
base = load_module("phase9_initial_jnlp_verifier_utility", BASE_VERIFIER_PATH)


class VerificationError(ValueError):
    pass


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


def configure_base() -> None:
    base.EXPECTED_GATE_SHA256 = EXPECTED_GATE_SHA256
    base.EXACT_CONFIRMATION = EXACT_CONFIRMATION
    base.EXACT_URL = EXACT_URL


def verify_static() -> dict:
    if sha256_file(require_regular(GATE, "gate")) != EXPECTED_GATE_SHA256:
        raise VerificationError("frozen gate SHA mismatch")
    if sha256_file(require_regular(AMENDMENT, "amendment")) != EXPECTED_AMENDMENT_SHA256:
        raise VerificationError("frozen amendment SHA mismatch")
    gate, digest = observer.validate_gate(GATE)
    if digest != EXPECTED_GATE_SHA256:
        raise VerificationError("observer gate SHA mismatch")
    workflow = require_regular(WORKFLOW, "workflow").read_text(encoding="utf-8")
    required = (
        "workflow_dispatch:", "github.run_number == 1", "github.run_attempt == 1",
        "github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'",
        "persist-credentials: false", "ref: ${{ github.sha }}",
        "permissions:\n  contents: read", EXACT_CONFIRMATION,
        "include-hidden-files: false", "retention-days: 14",
        "always() && steps.seal.outcome == 'success'",
    )
    for snippet in required:
        if snippet not in workflow:
            raise VerificationError(f"workflow missing invariant: {snippet}")
    trigger_prefix = workflow.split("permissions:", 1)[0]
    if re.search(r"(?m)^\s*(push|pull_request|schedule):", trigger_prefix):
        raise VerificationError("workflow has non-manual trigger")
    for prohibited in (
        "DUKASCOPY_USERNAME", "DUKASCOPY_PASSWORD", "curl ", "wget ",
        "mvn ", "java ", "getOfflineTimeDomains", "getAvailableInstruments",
    ):
        if prohibited.lower() in workflow.lower():
            raise VerificationError(f"workflow contains prohibited token: {prohibited}")
    return {
        "schema_version": "phase9-remote-libs-jnlp-static-verification-v1.0",
        "status": "STATIC_GATE_PASS_PENDING_EXACT_MANUAL_SINGLE_USE_APPROVAL",
        "gate_sha256": EXPECTED_GATE_SHA256,
        "amendment_sha256": EXPECTED_AMENDMENT_SHA256,
        "exact_url": gate["exact_scope"]["extension_url"],
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def verify_audit_dict(audit: dict) -> dict:
    if audit.get("schema_version") != "phase9-remote-libs-jnlp-observation-audit-v1.0":
        raise VerificationError("audit schema mismatch")
    status = audit.get("status")
    if status not in set(STATUS_TO_BASE) | {"ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED"}:
        raise VerificationError("audit status mismatch")
    translated = copy.deepcopy(audit)
    translated["schema_version"] = "phase9-remote-jnlp-initial-observation-audit-v1.0"
    translated["status"] = STATUS_TO_BASE.get(status, status)
    configure_base()
    try:
        base.verify_audit_dict(translated)
    except Exception as exc:
        raise VerificationError(str(exc)) from exc
    return audit


def verify_audit(path: Path) -> dict:
    return verify_audit_dict(json.loads(require_regular(path, "audit").read_text(encoding="utf-8")))


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
    audit_path = directory / AUDIT_FILE
    audit = verify_audit(audit_path)
    manifest = (directory / "artifact_manifest_sha256.txt").read_text(encoding="utf-8")
    expected = f"{sha256_file(audit_path)}  {AUDIT_FILE}\n"
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
