from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = ROOT / "data_manifest/native_entry_allowlist.run33376110507.json"
DEFAULT_EVIDENCE = ROOT / "results/s1b-run-33376110507"

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "status",
    "frozen_at",
    "source_evidence",
    "scope",
    "fail_closed_rules",
    "archives",
    "authorization_state",
    "remaining_blockers",
}
EXPECTED_ENTRY_KEYS = {
    "archive",
    "archive_sha256",
    "entry",
    "entry_sha256",
    "entry_size",
    "magic",
    "suffix_match",
    "target_os",
    "target_arches",
    "reviewed_binary_format",
}
EXPECTED_SOURCE_ANCHORS = {
    "run_id": 33376110507,
    "run_number": 2,
    "run_attempt": 1,
    "job_id": 99437846539,
    "head_sha": "951c38aaa875180fa7dbbe498866a4e3ece50e9c",
    "artifact_id": 9751919672,
    "artifact_zip_sha256": "ad72a646f91ec4e15fb7df564bbc7fd0fb4133c3c8999f8bf8a0468e4af0094a",
    "locked_jar_count": 116,
    "locked_jar_manifest_sha256": "8a6fca0cf65d80fc7ca0459ff56cf35ec6f92fe89b8f516de7bc8905ab941aeb",
    "native_entry_count": 28,
    "native_archive_count": 2,
}
EXPECTED_ALLOWLIST_SHA256 = "a0932eee2fe2c7019e838cce1557e78b19be42048af0474bbceb6b692b30602c"
EXPECTED_ARTIFACT_MANIFEST_SHA256 = "6ee13c8fedad21d1d818036e1f07bf0ac5b0b395441ef7c043d75ab15798049e"
EXPECTED_ARTIFACT_PAYLOAD_SHA256 = {
    "local_jnlp_synthetic_audit.json": "08ebf22317810005fe4185191762fca65a008c8ca09ba0ec12320a65d1b8ace1",
    "locked_jar_downloads.json": "fc9de4701faa7401bea0cafe278fb20d730a4eaa4f3ffdba873bced928f70e15",
    "locked_jar_sha256.txt": "8a6fca0cf65d80fc7ca0459ff56cf35ec6f92fe89b8f516de7bc8905ab941aeb",
    "native_library_inventory.json": "37e947016c764708c1258dcce5e205f8fd4c0bd9a2fec6a9a2b7a3d750d6f929",
    "runtime_identity.txt": "7c56db741ce18a115eaae8cd9453cd730906e302c718ee8706e85324aaf563ba",
    "s1b_authorization_state.json": "948425f3cffff988b95efb3a4e200178653300ecc8097e8b3051f33a91fbf0b7",
    "synthetic_qc_report.json": "81ed8fd03b6b581ae24f3ffbc92a55e3194e12069ccd88d030bb3055d4731c37",
    "workflow_policy_audit.json": "648bb003d8beb2643325266974516a3c1af083c51cdb54dbe9a5901d1301ee66",
}
EXPECTED_SCOPE = {
    "purpose": "Separate-commit exact-match Gate B for the Run 33376110507 locked-JAR native inventory.",
    "review_basis": "Artifact ZIP hash and all nine payload hashes reverified; the two SHA-locked archives were independently fetched and all 28 entry hashes, sizes, binary formats, operating systems, and architectures were reviewed.",
    "observed_runner_os": "linux",
    "observed_runner_arch": "x86_64",
    "native_execution_allowed": False,
    "market_or_jnlp_access_allowed": False,
}
EXPECTED_REMAINING_BLOCKERS = [
    "SHADED_RUNNER_NOT_SCANNED",
    "NATIVE_LOAD_AND_MAPPED_DSO_NOT_TESTED",
    "CHILD_PROCESS_AND_OS_EGRESS_NOT_ENFORCED",
    "REMOTE_JNLP_NOT_OBSERVED_OR_LOCKED",
    "STREAMING_48_SERIES_FULL_QC_NOT_FROZEN",
    "ACTUAL_MARKET_DATA_FULL_QC_NOT_EXECUTED",
    "RAW_CUSTODY_PATH_NOT_APPROVED",
]
FALSE_AUTHORIZATION_FIELDS = {
    "acquisition_authorized",
    "count_only_authorized",
    "outcomes_authorized",
    "runtime_code_closure_verified",
    "shaded_runner_scanned",
    "native_load_and_mapped_dso_verified",
    "child_process_and_os_egress_enforced",
    "remote_jnlp_locked",
    "streaming_48_series_full_qc_ready",
    "actual_market_data_full_quality_gate_passed",
}
ARTIFACT_FILENAMES = {
    "artifact_manifest_sha256.txt",
    "local_jnlp_synthetic_audit.json",
    "locked_jar_downloads.json",
    "locked_jar_sha256.txt",
    "native_library_inventory.json",
    "runtime_identity.txt",
    "s1b_authorization_state.json",
    "synthetic_qc_report.json",
    "workflow_policy_audit.json",
}


class GateBError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GateBError(f"Expected a JSON object: {path}")
    return value


def validate_relative_path(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or "\\" in value:
        raise GateBError(f"Invalid {label}: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise GateBError(f"Unsafe {label}: {value!r}")
    if str(path) != value:
        raise GateBError(f"Non-canonical {label}: {value!r}")


def parse_sha_manifest(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    folded: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise GateBError(f"Malformed SHA manifest line {line_number}")
        digest, name = parts
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise GateBError(f"Invalid SHA-256 on line {line_number}")
        if name.startswith("./"):
            name = name[2:]
        validate_relative_path(name, "manifest path")
        folded_name = name.casefold()
        if name in rows or folded_name in folded:
            raise GateBError(f"Duplicate or case-colliding manifest path: {name}")
        rows[name] = digest
        folded.add(folded_name)
    return rows


def validate_artifact_manifest(evidence_dir: Path) -> None:
    manifest_path = evidence_dir / "artifact_manifest_sha256.txt"
    if sha256_file(manifest_path) != EXPECTED_ARTIFACT_MANIFEST_SHA256:
        raise GateBError("Artifact manifest SHA-256 differs from the Run 2 anchor")
    manifest = parse_sha_manifest(manifest_path)
    expected_payloads = ARTIFACT_FILENAMES - {"artifact_manifest_sha256.txt"}
    if set(manifest) != expected_payloads or manifest != EXPECTED_ARTIFACT_PAYLOAD_SHA256:
        raise GateBError("Artifact manifest payload hashes differ from the Run 2 anchors")
    for name, expected in manifest.items():
        path = evidence_dir / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
            raise GateBError(f"Unsafe preserved artifact file: {name}")
        if sha256_file(path) != expected:
            raise GateBError(f"Preserved artifact hash mismatch: {name}")


def validate_artifact_zip(path: Path, expected_sha256: str) -> None:
    if sha256_file(path) != expected_sha256:
        raise GateBError("Artifact ZIP SHA-256 mismatch")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if set(names) != ARTIFACT_FILENAMES or len(names) != len(ARTIFACT_FILENAMES):
            raise GateBError("Artifact ZIP exact filename allowlist mismatch")
        if len({name.casefold() for name in names}) != len(names):
            raise GateBError("Artifact ZIP contains a case collision")
        for info in infos:
            validate_relative_path(info.filename, "ZIP entry")
            if info.is_dir() or info.flag_bits & 0x1:
                raise GateBError(f"Unsafe ZIP entry: {info.filename}")
            unix_mode = info.external_attr >> 16
            if unix_mode and not stat.S_ISREG(unix_mode):
                raise GateBError(f"Non-regular ZIP entry: {info.filename}")
        manifest = archive.read("artifact_manifest_sha256.txt").decode("utf-8")
        expected_rows: dict[str, str] = {}
        for line in manifest.splitlines():
            digest, name = line.split("  ", 1)
            if name in expected_rows or name.casefold() in {item.casefold() for item in expected_rows}:
                raise GateBError(f"Duplicate ZIP manifest path: {name}")
            expected_rows[name] = digest
        if set(expected_rows) != ARTIFACT_FILENAMES - {"artifact_manifest_sha256.txt"}:
            raise GateBError("ZIP manifest payload filename mismatch")
        for name, expected in expected_rows.items():
            if sha256_bytes(archive.read(name)) != expected:
                raise GateBError(f"ZIP payload hash mismatch: {name}")


def validate_authorization_state(allowlist: dict[str, Any], inventory: dict[str, Any]) -> None:
    state = allowlist.get("authorization_state")
    if not isinstance(state, dict) or set(state) != FALSE_AUTHORIZATION_FIELDS | {
        "phase9_price_files_acquired",
        "market_price_request_attempted",
        "forbidden_market_period_request_attempted",
        "research_outcomes_calculated",
        "outcome_fields",
    }:
        raise GateBError("Authorization state schema mismatch")
    for field in FALSE_AUTHORIZATION_FIELDS:
        if state[field] is not False:
            raise GateBError(f"Gate B must not authorize {field}")
    if state["phase9_price_files_acquired"] != 0:
        raise GateBError("Gate B evidence must contain zero Phase 9 price files")
    for field in (
        "market_price_request_attempted",
        "forbidden_market_period_request_attempted",
        "research_outcomes_calculated",
    ):
        if state[field] is not False:
            raise GateBError(f"Gate B evidence must keep {field}=false")
    if state["outcome_fields"] != []:
        raise GateBError("Gate B must have no outcome fields")
    for field, expected in (
        ("acquisition_authorized", False),
        ("market_price_request_attempted", False),
        ("phase9_price_files_acquired", 0),
        ("research_outcomes_calculated", False),
        ("outcome_fields", []),
    ):
        if inventory.get(field) != expected:
            raise GateBError(f"Inventory safety field mismatch: {field}")


def validate_allowlist(
    allowlist_path: Path = DEFAULT_ALLOWLIST,
    evidence_dir: Path = DEFAULT_EVIDENCE,
    artifact_zip: Path | None = None,
) -> dict[str, Any]:
    if sha256_file(allowlist_path) != EXPECTED_ALLOWLIST_SHA256:
        raise GateBError("Gate B allowlist SHA-256 differs from the reviewed frozen bytes")
    allowlist = load_json(allowlist_path)
    if set(allowlist) != EXPECTED_TOP_LEVEL_KEYS:
        raise GateBError("Gate B top-level schema mismatch")
    if allowlist["schema_version"] != "phase9-gate-b-native-exact-allowlist-v1.0":
        raise GateBError("Unexpected Gate B schema version")
    if allowlist["status"] != "GATE_B_EXACT_ALLOWLIST_FROZEN_ACQUISITION_BLOCKED":
        raise GateBError("Gate B status must remain acquisition-blocked")
    if allowlist["frozen_at"] != "2026-08-31":
        raise GateBError("Gate B freeze date mismatch")
    if allowlist["scope"] != EXPECTED_SCOPE:
        raise GateBError("Gate B scope differs from the reviewed no-execution/no-market scope")
    if allowlist["remaining_blockers"] != EXPECTED_REMAINING_BLOCKERS:
        raise GateBError("Gate B remaining blockers differ from the reviewed frozen list")

    anchors = allowlist.get("source_evidence")
    if not isinstance(anchors, dict) or anchors != EXPECTED_SOURCE_ANCHORS:
        raise GateBError("Gate B source anchors differ from Run 33376110507")

    audit = load_json(evidence_dir / "S1B_AUDIT.json")
    workflow = audit["workflow"]
    artifact = audit["artifact"]
    native_audit = audit["native_inventory"]
    observed_anchors = {
        "run_id": workflow["run_id"],
        "run_number": workflow["run_number"],
        "run_attempt": workflow["run_attempt"],
        "job_id": workflow["job_id"],
        "head_sha": workflow["head_sha"],
        "artifact_id": artifact["artifact_id"],
        "artifact_zip_sha256": artifact["artifact_zip_sha256"],
        "locked_jar_count": audit["dependency_bytes"]["locked_jar_count"],
        "locked_jar_manifest_sha256": audit["dependency_bytes"]["locked_jar_manifest_sha256"],
        "native_entry_count": native_audit["native_entry_count"],
        "native_archive_count": native_audit["archive_count"],
    }
    if observed_anchors != anchors:
        raise GateBError("S1B audit anchors differ from the frozen Gate B source")

    locked_manifest = evidence_dir / "locked_jar_sha256.txt"
    if sha256_file(locked_manifest) != anchors["locked_jar_manifest_sha256"]:
        raise GateBError("Locked-JAR manifest SHA-256 mismatch")
    locked_rows = parse_sha_manifest(locked_manifest)
    if len(locked_rows) != anchors["locked_jar_count"]:
        raise GateBError("Locked-JAR count mismatch")

    archives = allowlist.get("archives")
    if not isinstance(archives, list) or len(archives) != anchors["native_archive_count"]:
        raise GateBError("Gate B native archive count mismatch")
    expected_entries: dict[tuple[str, str], dict[str, Any]] = {}
    archive_paths: set[str] = set()
    archive_folded: set[str] = set()
    for archive in archives:
        if set(archive) != {"path", "sha256", "entry_count", "entries"}:
            raise GateBError("Native archive schema mismatch")
        archive_path = archive["path"]
        validate_relative_path(archive_path, "native archive path")
        if archive_path in archive_paths or archive_path.casefold() in archive_folded:
            raise GateBError(f"Duplicate or case-colliding archive: {archive_path}")
        archive_paths.add(archive_path)
        archive_folded.add(archive_path.casefold())
        manifest_path = archive_path.removeprefix("locked-jar/")
        if not archive_path.startswith("locked-jar/") or locked_rows.get(manifest_path) != archive["sha256"]:
            raise GateBError(f"Native archive is not exact in the locked manifest: {archive_path}")
        entries = archive["entries"]
        if not isinstance(entries, list) or len(entries) != archive["entry_count"]:
            raise GateBError(f"Native entry count mismatch for {archive_path}")
        folded_entries: set[str] = set()
        for entry in entries:
            if set(entry) != EXPECTED_ENTRY_KEYS:
                raise GateBError("Gate B native entry schema mismatch")
            if entry["archive"] != archive_path or entry["archive_sha256"] != archive["sha256"]:
                raise GateBError("Native entry archive identity mismatch")
            validate_relative_path(entry["entry"], "native entry path")
            if entry["entry"].casefold() in folded_entries:
                raise GateBError(f"Duplicate or case-colliding native entry: {entry['entry']}")
            folded_entries.add(entry["entry"].casefold())
            if not isinstance(entry["entry_size"], int) or entry["entry_size"] <= 0:
                raise GateBError("Native entry size must be a positive integer")
            if not isinstance(entry["suffix_match"], bool) or entry["suffix_match"] is not True:
                raise GateBError("Every frozen native entry must retain its suffix match")
            if entry["magic"] not in {"ELF", "PE", "MACHO", None}:
                raise GateBError("Unknown Gate A magic classification")
            if not isinstance(entry["target_os"], str) or entry["target_os"] in {"", "unknown"}:
                raise GateBError("Target OS must be explicit")
            arches = entry["target_arches"]
            if (
                not isinstance(arches, list)
                or not arches
                or len(set(arches)) != len(arches)
                or any(not isinstance(value, str) or value in {"", "unknown"} for value in arches)
            ):
                raise GateBError("Target architectures must be explicit and unique")
            if not isinstance(entry["reviewed_binary_format"], str) or not entry["reviewed_binary_format"]:
                raise GateBError("Reviewed binary format must be explicit")
            if entry["magic"] is None and not (
                entry["target_os"] == "aix" and entry["reviewed_binary_format"] == "XCOFF64"
            ):
                raise GateBError("Suffix-only native entry lacks an exact reviewed format")
            key = (archive_path, entry["entry"])
            if key in expected_entries:
                raise GateBError(f"Duplicate native key: {key}")
            expected_entries[key] = entry

    if len(expected_entries) != anchors["native_entry_count"]:
        raise GateBError("Total Gate B native entry count mismatch")
    if len({(archive.casefold(), entry.casefold()) for archive, entry in expected_entries}) != len(expected_entries):
        raise GateBError("Cross-archive native entry case collision")

    inventory = load_json(evidence_dir / "native_library_inventory.json")
    observed_list = inventory.get("native_entries")
    if not isinstance(observed_list, list) or len(observed_list) != anchors["native_entry_count"]:
        raise GateBError("Observed native entry count mismatch")
    observed_entries: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in observed_list:
        expected_observed_keys = {
            "archive",
            "archive_sha256",
            "entry",
            "entry_sha256",
            "entry_size",
            "magic",
            "suffix_match",
        }
        if set(entry) != expected_observed_keys:
            raise GateBError("Observed native inventory schema mismatch")
        validate_relative_path(entry["archive"], "observed archive path")
        validate_relative_path(entry["entry"], "observed native entry path")
        key = (entry["archive"], entry["entry"])
        if key in observed_entries:
            raise GateBError(f"Duplicate observed native entry: {key}")
        observed_entries[key] = entry
    if len({(archive.casefold(), entry.casefold()) for archive, entry in observed_entries}) != len(observed_entries):
        raise GateBError("Observed native inventory contains a case collision")
    if set(observed_entries) != set(expected_entries):
        missing = sorted(set(expected_entries) - set(observed_entries))
        additional = sorted(set(observed_entries) - set(expected_entries))
        raise GateBError(f"Native exact-match failure; missing={missing}, additional={additional}")
    for key, observed in observed_entries.items():
        expected = expected_entries[key]
        for field in (
            "archive",
            "archive_sha256",
            "entry",
            "entry_sha256",
            "entry_size",
            "magic",
            "suffix_match",
        ):
            if observed[field] != expected[field]:
                raise GateBError(f"Native exact-match field mismatch: {key} {field}")

    validate_authorization_state(allowlist, inventory)
    validate_artifact_manifest(evidence_dir)
    if artifact_zip is not None:
        validate_artifact_zip(artifact_zip, anchors["artifact_zip_sha256"])

    rules = allowlist.get("fail_closed_rules")
    required_true_rules = {
        "exact_archive_set_required",
        "exact_entry_set_required",
        "reject_unknown_archive",
        "reject_additional_entry",
        "reject_missing_entry",
        "reject_duplicate_entry",
        "reject_case_collision",
        "reject_unknown_magic_or_target",
        "same_run_inventory_self_authorization_prohibited",
        "gate_b_does_not_authorize_acquisition",
    }
    if not isinstance(rules, dict) or set(rules) != required_true_rules or any(value is not True for value in rules.values()):
        raise GateBError("Gate B fail-closed rules are incomplete")

    return {
        "status": "GATE_B_EXACT_MATCH_PASS_ACQUISITION_BLOCKED",
        "source_run_id": anchors["run_id"],
        "source_head_sha": anchors["head_sha"],
        "locked_jar_count": anchors["locked_jar_count"],
        "native_archive_count": len(archives),
        "native_entry_count": len(expected_entries),
        "artifact_zip_verified": artifact_zip is not None,
        "acquisition_authorized": False,
        "phase9_price_files_acquired": 0,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the frozen Phase 9 Gate B native allowlist.")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--artifact-zip", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_allowlist(args.allowlist, args.evidence_dir, args.artifact_zip)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
