from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "data_manifest/runtime_mapping_allowlist.run33451221995.json"
EXPECTED_ALLOWLIST_SHA256 = "43a7a0e43302daed8f5ad97c63c3da1a618f16d4d07a43a1de88c49e8ec26bc3"
EXPECTED_SOURCE = {
    "run_id": 33451221995,
    "run_attempt": 1,
    "job_id": 99681326258,
    "head_sha": "9699c64b9133482caf22cef07dc9b3bc2fe33a1a",
    "artifact_id": 9779840519,
    "artifact_name": "phase9-gate-c1-runtime-inventory-9699c64b9133482caf22cef07dc9b3bc2fe33a1a-33451221995-1",
    "artifact_size_bytes": 1041038,
    "artifact_zip_sha256": "d5ea84805732209e85340376de98788f897eba411a3170b300600767252d60f0",
    "artifact_manifest_sha256": "c66b968c1b9eee2897ce02995d08a3f65f054a150cfffc262585d9f1905944d5",
    "runtime_observation_sha256": "0cc0f2eaff9c5e5a3508abd24992075072cd30e3620fb8ff8a0fabe235e3fa99",
    "shaded_runner_inventory_sha256": "45c94ddfd3cf7d02938a3fb8be68c0edce64546be9470c0503a0a97f36f64c46",
    "authorization_state_sha256": "0d4ac3efcfa44b3de32099668986e5598e178192fcb45d00945325be849ea07d",
    "runtime_identity_sha256": "cf6fec16e2e5e0c140a953ca1b09b3184246d022a2f7f317b2d59a3a6bea863d",
    "syscall_trace_sha256": "bc3f3da963a8502f474d54a075cf86bb315f827b344e9a6c05a82adc9db2a24b",
}
EXPECTED_ARTIFACT_PAYLOAD_SHA256 = {
    "authorization_state.json": "0d4ac3efcfa44b3de32099668986e5598e178192fcb45d00945325be849ea07d",
    "effective_mount_inventory.txt": "0ec234641d3c081ba0a289556fda70f7ed57afcb8c393618362fbf89e43f1f2c",
    "maven_build_artifact_sha256.txt": "94838ee9280ba2f02adb456129c01bb32bd7e17d4909ac3e43a1556f74c8964c",
    "maven_prefetch_audit.json": "fbcdb4b60ffd895a25742970c0b57d43ec5f2091cb12cb877416a6fdfcd5f673",
    "maven_repository_sha256.txt": "94838ee9280ba2f02adb456129c01bb32bd7e17d4909ac3e43a1556f74c8964c",
    "mount_inventory.txt": "d69aeb7a0975fc9b6c5775af3f6896d49f58e820fa95ef3dc92e8665b83bdf61",
    "network_namespace.txt": "0482bc32379f20ed556330b18102806d090f0551b6921e2981d527d40fe4f6ce",
    "probe_proc_maps.txt": "7f979e6c9d90852cd822b841b6179270ff8d2eea391b537d9d96e92fcc71152d",
    "probe_stderr.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "probe_stdout.txt": "7f2fda8cdb595d7eefdb9d626df919f6b633949a2d6d4fe0505ef92c323051f5",
    "raw_mountinfo.txt": "f1fb2431271e7ba31c2331d5ed906f7f37bfd48110fddc20e8eb4e5cc5d18119",
    "runtime_identity.txt": "cf6fec16e2e5e0c140a953ca1b09b3184246d022a2f7f317b2d59a3a6bea863d",
    "runtime_observation.json": "0cc0f2eaff9c5e5a3508abd24992075072cd30e3620fb8ff8a0fabe235e3fa99",
    "sandbox_evidence_manifest.txt": "55bc602cbb01153fc933d6ea5b3002f6e5e26a25348ec1bfbb7ceaf903495a9b",
    "shaded_runner_inventory.json": "45c94ddfd3cf7d02938a3fb8be68c0edce64546be9470c0503a0a97f36f64c46",
    "supervisor_identity.txt": "8f593b60f766b1665039d193a75b4073a68840ffb4e382da0a5577d51c55b0af",
    "syscall_trace.txt": "bc3f3da963a8502f474d54a075cf86bb315f827b344e9a6c05a82adc9db2a24b",
}
EXPECTED_SIGNATURES = [
    "connect:AF_UNIX:FAILURE:COUNT_6",
    "getsockname:FAMILY_NOT_VISIBLE:FAILURE:COUNT_1",
    "socket:AF_INET6:SOCK_STREAM:IPPROTO_IP:SUCCESS:COUNT_1",
    "socket:AF_UNIX:SOCK_CLOEXEC+SOCK_NONBLOCK+SOCK_STREAM:PROTOCOL_0:SUCCESS:COUNT_6",
    "socketpair:AF_UNIX:SOCK_STREAM:PROTOCOL_0:SUCCESS:COUNT_1",
]
FALSE_FIELDS = {
    "acquisition_authorized", "count_only_authorized", "outcomes_authorized",
    "runtime_code_closure_verified", "remote_jnlp_locked",
    "acquisition_egress_allowlist_enforced", "actual_market_data_full_quality_gate_passed",
    "raw_custody_approved", "credentials_referenced", "external_jnlp_request_attempted",
    "availability_request_attempted", "same_run_inventory_may_authorize",
    "jforex_connect_invoked", "market_price_request_attempted",
    "forbidden_market_period_request_attempted", "research_outcomes_calculated",
}


class GateC2Error(ValueError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_relative(value: str) -> None:
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or str(path) != value or ".." in path.parts:
        raise GateC2Error(f"Unsafe relative mapping path: {value!r}")


def parse_manifest(value: str) -> dict[str, str]:
    output: dict[str, str] = {}
    folded: set[str] = set()
    for line in value.splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise GateC2Error("Malformed artifact manifest")
        digest, name = parts
        safe_relative(name)
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise GateC2Error("Malformed artifact manifest SHA-256")
        if name in output or name.casefold() in folded:
            raise GateC2Error("Duplicate or case-colliding artifact manifest path")
        output[name] = digest
        folded.add(name.casefold())
    return output


def parse_identity(value: bytes) -> dict[str, str]:
    output: dict[str, str] = {}
    for line in value.decode("utf-8").splitlines():
        if "=" not in line:
            raise GateC2Error("Malformed Gate C1 runtime identity")
        key, item = line.split("=", 1)
        if not key or not item or key in output:
            raise GateC2Error("Duplicate or empty Gate C1 runtime identity field")
        output[key] = item
    return output


def cross_check_artifact_payloads(payloads: dict[str, bytes], allowlist: dict[str, Any]) -> None:
    runtime = json.loads(payloads["runtime_observation.json"].decode("utf-8"))
    authorization = json.loads(payloads["authorization_state.json"].decode("utf-8"))
    shaded = json.loads(payloads["shaded_runner_inventory.json"].decode("utf-8"))
    identity = parse_identity(payloads["runtime_identity.txt"])
    expected_runtime_mappings = [
        {"path": row["observed_path"], "sha256": row["sha256"], "bytes": row["bytes"]}
        for row in allowlist["executable_file_mappings"]
    ]
    if runtime.get("executable_file_mapping_count") != 15:
        raise GateC2Error("Gate C1 runtime mapping count differs from Gate C2")
    if runtime.get("executable_file_mappings") != expected_runtime_mappings:
        raise GateC2Error("Gate C1 runtime mappings differ from Gate C2 exact allowlist")
    if runtime.get("observed_inert_network_syscall_signatures") != allowlist["observed_inert_network_syscall_signatures"]:
        raise GateC2Error("Gate C1 inert syscall signatures differ from Gate C2")
    for field, expected in (
        ("child_process_spawned", False),
        ("external_network_io_succeeded", False),
        ("acquisition_authorized", False),
        ("count_only_authorized", False),
        ("outcomes_authorized", False),
        ("phase9_price_files_acquired", 0),
        ("outcome_fields", []),
        ("same_run_runtime_inventory_may_authorize", False),
    ):
        if runtime.get(field) != expected:
            raise GateC2Error(f"Gate C1 runtime safety field mismatch: {field}")
    for field in FALSE_FIELDS:
        if field in authorization and authorization[field] is not False:
            raise GateC2Error(f"Gate C1 authorization field changed: {field}")
    for field, expected in (
        ("acquisition_authorized", False),
        ("count_only_authorized", False),
        ("outcomes_authorized", False),
        ("phase9_price_files_acquired", 0),
        ("outcome_fields", []),
        ("same_run_inventory_may_authorize", False),
    ):
        if authorization.get(field) != expected:
            raise GateC2Error(f"Gate C1 authorization payload mismatch: {field}")
    if shaded.get("runner_sha256") != allowlist["scope"]["shaded_runner_sha256"]:
        raise GateC2Error("Gate C1 shaded runner SHA-256 differs from Gate C2")
    for field, expected in (
        ("acquisition_authorized", False),
        ("phase9_price_files_acquired", 0),
        ("outcome_fields", []),
        ("same_run_inventory_may_authorize", False),
    ):
        if shaded.get(field) != expected:
            raise GateC2Error(f"Gate C1 shaded inventory safety mismatch: {field}")
    java_mappings = [
        row for row in expected_runtime_mappings
        if row["path"] == allowlist["scope"]["java_home"] + "/bin/java"
    ]
    if len(java_mappings) != 1:
        raise GateC2Error("Gate C2 must contain exactly one pinned Java executable")
    expected_identity = {
        "git_sha": str(EXPECTED_SOURCE["head_sha"]),
        "run_id": str(EXPECTED_SOURCE["run_id"]),
        "run_attempt": str(EXPECTED_SOURCE["run_attempt"]),
        "runner_os": "Linux",
        "runner_arch": "X64",
        "image_os": allowlist["scope"]["runner_image_os"],
        "image_version": allowlist["scope"]["runner_image_version"],
        "java_home": allowlist["scope"]["java_home"],
        "java_sha256": java_mappings[0]["sha256"],
    }
    if identity != expected_identity:
        raise GateC2Error("Gate C1 runtime identity differs from Gate C2 source anchors")


def validate_artifact_zip(path: Path, allowlist: dict[str, Any] | None = None) -> None:
    if sha256_file(path) != EXPECTED_SOURCE["artifact_zip_sha256"]:
        raise GateC2Error("Gate C1 Artifact ZIP SHA-256 mismatch")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        expected_names = set(EXPECTED_ARTIFACT_PAYLOAD_SHA256) | {"artifact_manifest_sha256.txt"}
        if len(names) != len(expected_names) or set(names) != expected_names:
            raise GateC2Error("Gate C1 Artifact ZIP filename mismatch")
        if len({name.casefold() for name in names}) != len(names):
            raise GateC2Error("Gate C1 Artifact ZIP case collision")
        for item in infos:
            safe_relative(item.filename)
            mode = item.external_attr >> 16
            if item.is_dir() or item.flag_bits & 1 or (mode and not stat.S_ISREG(mode)):
                raise GateC2Error("Unsafe Gate C1 Artifact ZIP entry")
        raw_manifest = archive.read("artifact_manifest_sha256.txt")
        if sha256_bytes(raw_manifest) != EXPECTED_SOURCE["artifact_manifest_sha256"]:
            raise GateC2Error("Gate C1 artifact manifest SHA-256 mismatch")
        manifest = parse_manifest(raw_manifest.decode("utf-8"))
        if manifest != EXPECTED_ARTIFACT_PAYLOAD_SHA256:
            raise GateC2Error("Gate C1 artifact payload manifest mismatch")
        payloads = {name: archive.read(name) for name in manifest}
        for name, expected in manifest.items():
            if sha256_bytes(payloads[name]) != expected:
                raise GateC2Error(f"Gate C1 ZIP payload mismatch: {name}")
        if allowlist is None:
            allowlist = json.loads(DEFAULT_ALLOWLIST.read_text(encoding="utf-8"))
        cross_check_artifact_payloads(payloads, allowlist)


def validate_allowlist(path: Path = DEFAULT_ALLOWLIST, artifact_zip: Path | None = None) -> dict[str, Any]:
    if sha256_file(path) != EXPECTED_ALLOWLIST_SHA256:
        raise GateC2Error("Gate C2 allowlist differs from the reviewed frozen bytes")
    value = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version", "status", "frozen_at", "source_evidence", "scope",
        "observed_inert_network_syscall_signatures", "fail_closed_rules",
        "executable_file_mappings", "authorization_state", "remaining_blockers",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise GateC2Error("Gate C2 top-level schema mismatch")
    if value["schema_version"] != "phase9-gate-c2-runtime-exact-allowlist-v1.0":
        raise GateC2Error("Gate C2 schema version mismatch")
    if value["status"] != "GATE_C2_EXACT_RUNTIME_ALLOWLIST_FROZEN_ACQUISITION_BLOCKED":
        raise GateC2Error("Gate C2 status must remain acquisition-blocked")
    if value["source_evidence"] != EXPECTED_SOURCE:
        raise GateC2Error("Gate C2 source anchors mismatch")
    if value["observed_inert_network_syscall_signatures"] != EXPECTED_SIGNATURES:
        raise GateC2Error("Gate C2 inert network signature multiset mismatch")
    mappings = value["executable_file_mappings"]
    if not isinstance(mappings, list) or len(mappings) != 15:
        raise GateC2Error("Gate C2 must freeze exactly 15 executable mappings")
    identities: set[tuple[str, str]] = set()
    folded: set[tuple[str, str]] = set()
    gate_c_root = (
        f"/home/runner/work/_temp/phase9-gate-c1-{EXPECTED_SOURCE['run_id']}-"
        f"{EXPECTED_SOURCE['run_attempt']}/"
    )
    for row in mappings:
        if set(row) != {"path_scope", "path", "observed_path", "sha256", "bytes", "target_os", "target_arch"}:
            raise GateC2Error("Gate C2 mapping schema mismatch")
        if row["path_scope"] not in {"ABSOLUTE", "GATE_C_ROOT_RELATIVE"}:
            raise GateC2Error("Gate C2 mapping path scope mismatch")
        if row["path_scope"] == "ABSOLUTE":
            if not PurePosixPath(row["path"]).is_absolute():
                raise GateC2Error("Absolute mapping path required")
            if row["observed_path"] != row["path"]:
                raise GateC2Error("Absolute mapping observed path mismatch")
        else:
            safe_relative(row["path"])
            if row["observed_path"] != gate_c_root + row["path"]:
                raise GateC2Error("Gate C root-relative observed path mismatch")
        identity = (row["path_scope"], row["path"])
        folded_identity = (row["path_scope"], row["path"].casefold())
        if identity in identities or folded_identity in folded:
            raise GateC2Error("Duplicate or case-colliding runtime mapping")
        identities.add(identity)
        folded.add(folded_identity)
        if len(row["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in row["sha256"]):
            raise GateC2Error("Runtime mapping SHA-256 malformed")
        if not isinstance(row["bytes"], int) or row["bytes"] <= 0:
            raise GateC2Error("Runtime mapping size malformed")
        if row["target_os"] != "linux" or row["target_arch"] != "x86_64":
            raise GateC2Error("Runtime mapping target mismatch")
    state = value["authorization_state"]
    if not isinstance(state, dict) or any(state.get(field) is not False for field in FALSE_FIELDS):
        raise GateC2Error("Gate C2 authorization boundary changed")
    if state.get("phase9_price_files_acquired") != 0 or state.get("outcome_fields") != []:
        raise GateC2Error("Gate C2 price/outcome boundary changed")
    if not value["fail_closed_rules"].get("same_run_inventory_self_authorization_prohibited"):
        raise GateC2Error("Same-run self-authorization prohibition removed")
    if not value["remaining_blockers"]:
        raise GateC2Error("Gate C2 remaining blockers removed")
    if artifact_zip is not None:
        validate_artifact_zip(artifact_zip, value)
    return {
        "status": "GATE_C2_EXACT_MATCH_PASS_ACQUISITION_BLOCKED",
        "source_run_id": EXPECTED_SOURCE["run_id"],
        "executable_mapping_count": len(mappings),
        "artifact_zip_verified": artifact_zip is not None,
        "acquisition_authorized": False,
        "phase9_price_files_acquired": 0,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--artifact-zip", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate_allowlist(args.allowlist, args.artifact_zip), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
