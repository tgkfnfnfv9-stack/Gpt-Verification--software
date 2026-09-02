#!/usr/bin/env python3
"""Verify the corrected V2 one-shot libs_3.jnlp identity Gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
V1_VERIFIER_PATH = Path(__file__).with_name(
    "verify_phase9_remote_libs_jnlp_observation.py"
)
GATE = ROOT / "spec/remote_libs_jnlp_observation_gate_v2.frozen.json"
AMENDMENT = ROOT / "JFOREX_REMOTE_LIBS_JNLP_OBSERVATION_REAUTHORIZATION_V2.md"
WORKFLOW = ROOT.parents[1] / ".github/workflows/phase9-remote-libs-jnlp-observation-v2.yml"
STATIC_SCRIPT = Path(__file__).with_name(
    "verify_phase9_remote_libs_jnlp_observation_v2_static.sh"
)
EXPECTED_GATE_SHA256 = "0782f250c9d79bee70a862f590182c52bf550c6d08464d140d61dab39ab74487"
EXPECTED_AMENDMENT_SHA256 = "9789e6da1a8385a48d15a0aac868e88c3c58b4ec455d9d3dca47f79c8b749c20"
EXACT_CONFIRMATION = (
    "OBSERVE_PHASE9_REMOTE_LIBS_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS_V2"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v1 = load_module("phase9_remote_libs_v1_verifier_for_v2", V1_VERIFIER_PATH)
v1.GATE = GATE
v1.AMENDMENT = AMENDMENT
v1.WORKFLOW = WORKFLOW
v1.EXPECTED_GATE_SHA256 = EXPECTED_GATE_SHA256
v1.EXPECTED_AMENDMENT_SHA256 = EXPECTED_AMENDMENT_SHA256
v1.EXACT_CONFIRMATION = EXACT_CONFIRMATION

VerificationError = v1.VerificationError
AUDIT_FILE = v1.AUDIT_FILE


def verify_static() -> dict:
    value = v1.verify_static()
    workflow = WORKFLOW.read_text(encoding="utf-8")
    static_script = STATIC_SCRIPT.read_text(encoding="utf-8")
    if re.search(r"=\s*\+\s*['\"]", workflow):
        raise VerificationError("workflow contains the V1 literal-plus corruption")
    required = (
        "remote_libs_jnlp_observation_gate_v2.frozen.json",
        "verify_phase9_remote_libs_jnlp_observation_v2.py",
        "steps.initialize.outcome == 'success'",
        "id: initialize",
        "command=(",
        "verify_phase9_remote_libs_jnlp_observation_v2_static.sh",
    )
    for snippet in required:
        if snippet not in workflow:
            raise VerificationError(f"V2 workflow missing correction invariant: {snippet}")
    for snippet in (
        'test "$gate_sha" =',
        'test "$allowlist_sha" =',
        'test "$source_audit_sha" =',
        'test "$(git status --porcelain)" = "$status_before"',
    ):
        if snippet not in static_script:
            raise VerificationError(f"V2 static script missing invariant: {snippet}")
    value["schema_version"] = "phase9-remote-libs-jnlp-static-verification-v2.0"
    value["status"] = "STATIC_V2_GATE_PASS_PENDING_NEW_EXACT_MANUAL_APPROVAL"
    value["v1_failed_run_id"] = 33574659277
    value["v1_http_request_count"] = 0
    return value


def verify_audit(path: Path) -> dict:
    return v1.verify_audit(path)


def verify_artifact(directory: Path) -> dict:
    return v1.verify_artifact(directory)


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
