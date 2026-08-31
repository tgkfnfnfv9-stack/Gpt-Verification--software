#!/usr/bin/env python3
"""C1 inventory for the exact Phase 9 shaded runner; never authorizes acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath


EXPECTED_RUNNER_SHA256 = "545bb9601d547b0edd5476886474a9affb541df5dc1c3fe172cb544c7c1f8204"
EXPECTED_ALLOWLIST_SHA256 = "a0932eee2fe2c7019e838cce1557e78b19be42048af0474bbceb6b692b30602c"
EXPECTED_MANIFEST_FIELDS = {
    "Main-Class": "org.phase9.Phase9JForexAcquirer",
    "Premain-Class": "org.phase9.RuntimeClassOriginGuard",
    "Can-Redefine-Classes": "false",
    "Can-Retransform-Classes": "false",
}
PROHIBITED_MANIFEST_FIELDS = {"Class-Path", "Boot-Class-Path", "Multi-Release"}
NATIVE_SUFFIXES = (".so", ".dll", ".dylib", ".jnilib")
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
}
STATIC_TOKENS = {
    "process_builder": b"java/lang/ProcessBuilder",
    "runtime_exec": b"java/lang/Runtime",
    "system_load": b"java/lang/System",
    "socket": b"java/net/Socket",
    "server_socket": b"java/net/ServerSocket",
    "url_connection": b"java/net/URLConnection",
    "class_loader": b"java/lang/ClassLoader",
    "native_library": b"com/sun/jna/NativeLibrary",
}
HOST_NATIVE_PATHS = {
    "com/sun/jna/linux-amd64/libjnidispatch.so",
}
FALSE_FLAGS = {
    "credentials_referenced": False,
    "external_jnlp_request_attempted": False,
    "jforex_connect_invoked": False,
    "availability_request_attempted": False,
    "market_price_request_attempted": False,
    "forbidden_market_period_request_attempted": False,
    "research_outcomes_calculated": False,
    "runtime_code_closure_verified": False,
    "acquisition_authorized": False,
    "count_only_authorized": False,
    "outcomes_authorized": False,
}


class GateCError(ValueError):
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
        raise GateCError(f"{label} must be a single-link regular file")
    return path.resolve(strict=True)


def safe_zip_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value:
        raise GateCError(f"Unsafe ZIP path: {value!r}")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or "." in parsed.parts:
        raise GateCError(f"Unsafe ZIP path: {value!r}")
    return parsed


def native_magic(value: bytes, name: str) -> str | None:
    if value.startswith(b"\x7fELF"):
        return "ELF"
    if value.startswith(b"MZ"):
        return "PE"
    if value[:4] in MACHO_MAGICS and not name.lower().endswith(".class"):
        return "MACHO"
    return None


def parse_manifest(raw: bytes) -> dict[str, str]:
    text = raw.decode("utf-8").replace("\r\n", "\n")
    unfolded = text.replace("\n ", "")
    output: dict[str, str] = {}
    for line in unfolded.splitlines():
        if not line:
            continue
        if ": " not in line:
            raise GateCError("Malformed runner manifest")
        key, value = line.split(": ", 1)
        if key in output:
            raise GateCError(f"Duplicate manifest field: {key}")
        output[key] = value
    for key, expected in EXPECTED_MANIFEST_FIELDS.items():
        if output.get(key) != expected:
            raise GateCError(f"Manifest field mismatch: {key}")
    if PROHIBITED_MANIFEST_FIELDS.intersection(output):
        raise GateCError("Runner manifest contains an external or multi-release class path")
    return output


def expected_native_entries(allowlist_path: Path) -> dict[str, dict]:
    require_regular(allowlist_path, "Gate B allowlist")
    if sha256_file(allowlist_path) != EXPECTED_ALLOWLIST_SHA256:
        raise GateCError("Gate B allowlist SHA-256 mismatch")
    value = json.loads(allowlist_path.read_text(encoding="utf-8"))
    output: dict[str, dict] = {}
    for archive in value["archives"]:
        for entry in archive["entries"]:
            name = entry["entry"]
            safe_zip_path(name)
            if name in output or name.casefold() in {key.casefold() for key in output}:
                raise GateCError(f"Gate B native path collision: {name}")
            output[name] = entry
    if len(output) != 28:
        raise GateCError("Gate B must contain exactly 28 native entries")
    if not HOST_NATIVE_PATHS.issubset(output):
        raise GateCError("Gate B lacks an exact Linux X64 host native")
    return output


def scan_runner(runner_path: Path, allowlist_path: Path, extract_dir: Path) -> dict:
    runner = require_regular(runner_path, "Shaded runner")
    before = sha256_file(runner)
    if before != EXPECTED_RUNNER_SHA256:
        raise GateCError("Shaded runner SHA-256 mismatch")
    expected = expected_native_entries(allowlist_path)
    if extract_dir.exists() or extract_dir.is_symlink():
        raise GateCError("Native extraction directory must be new")
    extract_dir.mkdir(mode=0o700, parents=False)
    names: set[str] = set()
    folded: set[str] = set()
    classes: list[dict] = []
    natives: dict[str, dict] = {}
    services: list[dict] = []
    with zipfile.ZipFile(runner) as archive:
        infos = archive.infolist()
        for info in infos:
            path = safe_zip_path(info.filename)
            if info.flag_bits & 0x1:
                raise GateCError(f"Encrypted ZIP entry prohibited: {info.filename}")
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise GateCError(f"Non-regular ZIP entry prohibited: {info.filename}")
            if info.filename in names or info.filename.casefold() in folded:
                raise GateCError(f"Duplicate or case-colliding ZIP entry: {info.filename}")
            names.add(info.filename)
            folded.add(info.filename.casefold())
            if info.is_dir():
                continue
            data = archive.read(info)
            if path.name.lower().endswith(".class"):
                tokens = sorted(label for label, token in STATIC_TOKENS.items() if token in data)
                classes.append({"path": info.filename, "bytes": len(data), "sha256": sha256_bytes(data), "tokens": tokens})
            if info.filename.startswith("META-INF/services/"):
                services.append({"path": info.filename, "bytes": len(data), "sha256": sha256_bytes(data)})
            magic = native_magic(data[:4], info.filename)
            suffix = path.name.lower().endswith(NATIVE_SUFFIXES)
            if suffix or magic is not None:
                natives[info.filename] = {
                    "entry": info.filename,
                    "entry_size": len(data),
                    "entry_sha256": sha256_bytes(data),
                    "magic": magic,
                    "suffix_match": suffix,
                }
            if info.filename in HOST_NATIVE_PATHS:
                target = extract_dir / path.name
                if target.exists():
                    raise GateCError("Host-native basename collision")
                target.write_bytes(data)
                os.chmod(target, 0o500)
        manifest = parse_manifest(archive.read("META-INF/MANIFEST.MF"))
    additional = sorted(set(natives) - set(expected))
    missing = sorted(set(expected) - set(natives))
    if additional:
        raise GateCError(f"Shaded runner contains native entries outside Gate B: {additional}")
    if not HOST_NATIVE_PATHS.issubset(natives):
        raise GateCError("Shaded runner lacks its exact Linux X64 host native")
    for name, actual in natives.items():
        frozen = expected[name]
        for field in ("entry_size", "entry_sha256", "magic", "suffix_match"):
            if actual[field] != frozen[field]:
                raise GateCError(f"Shaded native field mismatch: {name} {field}")
    extracted = []
    for name in sorted(HOST_NATIVE_PATHS):
        target = extract_dir / PurePosixPath(name).name
        frozen = expected[name]
        if sha256_file(target) != frozen["entry_sha256"] or target.stat().st_size != frozen["entry_size"]:
            raise GateCError(f"Extracted host native mismatch: {name}")
        extracted.append({"entry": name, "path": str(target), "sha256": frozen["entry_sha256"], "bytes": frozen["entry_size"]})
    if sha256_file(runner) != before:
        raise GateCError("Shaded runner changed during scan")
    return {
        "schema_version": "phase9-gate-c1-shaded-inventory-v1.0",
        "status": "GATE_C1_INVENTORY_RECORDED_ACQUISITION_BLOCKED",
        "runner_sha256": before,
        "zip_entry_count": len(names),
        "class_count": len(classes),
        "classes": classes,
        "service_entries": sorted(services, key=lambda row: row["path"]),
        "manifest": manifest,
        "native_entry_count": len(natives),
        "native_entries": [natives[name] for name in sorted(natives)],
        "gate_b_source_native_entry_count": len(expected),
        "gate_b_source_native_entries_not_shaded": missing,
        "host_native_extractions": extracted,
        "static_inventory_is_not_runtime_authorization": True,
        "same_run_inventory_may_authorize": False,
        **FALSE_FLAGS,
        "phase9_price_files_acquired": 0,
        "outcome_fields": [],
        "remaining_blockers": [
            "GATE_C2_EXACT_RUNTIME_ALLOWLIST_NOT_FROZEN",
            "CHILD_PROCESS_SECCOMP_NOT_ENFORCED",
            "ACQUISITION_EGRESS_ALLOWLIST_NOT_ENFORCED",
            "JRE_AND_SYSTEM_DSO_ALLOWLIST_NOT_FROZEN",
            "ACQUIRER_OUTPUT_CACHE_REALPATH_GUARD_NOT_FIXED",
            "REMOTE_JNLP_NOT_OBSERVED_OR_LOCKED",
            "ACTUAL_48_SERIES_FULL_QC_NOT_EXECUTED",
            "RAW_CUSTODY_NOT_APPROVED",
        ],
    }


def parse_supervisor_identity(path: Path) -> dict[str, str]:
    values = {}
    for line in require_regular(path, "Supervisor identity").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            raise GateCError("Malformed supervisor identity row")
        key, value = line.split("=", 1)
        if key in values or not key or not value:
            raise GateCError("Duplicate or empty supervisor identity field")
        values[key] = value
    expected_keys = {
        "trace_supervisor_uid", "tracee_uids_observed", "tracee_gids_observed", "tracee_pid",
        "no_new_privs_observed",
        "supplementary_groups_observed",
        "setpriv_path", "env_path", "java_path",
    }
    if set(values) != expected_keys:
        raise GateCError("Supervisor identity schema mismatch")
    observed_uids = values["tracee_uids_observed"].split(",")
    observed_gids = values["tracee_gids_observed"].split(",")
    if (
        values["trace_supervisor_uid"] != "0"
        or len(observed_uids) != 4
        or len(observed_gids) != 4
        or any(value == "0" or value != observed_uids[0] for value in observed_uids)
        or any(value == "0" or value != observed_gids[0] for value in observed_gids)
        or values["no_new_privs_observed"] != "1"
        or values["supplementary_groups_observed"] != "NONE"
    ):
        raise GateCError("Supervisor/tracee privilege boundary mismatch")
    for key in ("setpriv_path", "env_path", "java_path"):
        require_regular(Path(values[key]), key)
    return values


def classify_exec_argv_shape(line: str) -> str:
    prefixes = (
        r'\bexecve\("[^"]+",\s*',
        r'\bexecveat\([^,]+,\s*"[^"]+",\s*',
    )
    remainder = None
    for prefix in prefixes:
        match = re.search(prefix, line)
        if match is not None:
            remainder = line[match.end():]
            break
    if remainder is None:
        return "UNKNOWN"
    if re.match(r'\[\.\.\.\]\s*,', remainder):
        return "BRACKET_ELLIPSIS"
    if re.match(r'\[(?:"(?:[^"\\]|\\.)*"\s*,\s*)+\.\.\.\]\s*,', remainder):
        return "ARRAY_TRAILING_ELLIPSIS"
    if re.match(r'0x[0-9a-fA-F]+\s*/\*\s*\d+\s+vars\s*\*/\s*,', remainder):
        return "POINTER_COUNT"
    if remainder.startswith("["):
        return "ARRAY"
    return "UNKNOWN"


def validate_runtime(
    inventory_path: Path,
    maps_path: Path,
    trace_dir: Path,
    supervisor_identity_path: Path,
    output: Path,
) -> dict:
    inventory = json.loads(require_regular(inventory_path, "C1 inventory").read_text(encoding="utf-8"))
    supervisor = parse_supervisor_identity(supervisor_identity_path)
    maps = require_regular(maps_path, "Probe maps").read_text(encoding="utf-8")
    mapped = []
    for item in inventory["host_native_extractions"]:
        native = require_regular(Path(item["path"]), "Extracted host native")
        if sha256_file(native) != item["sha256"]:
            raise GateCError("Host native changed before runtime validation")
        if not any(line.rstrip().endswith(str(native)) for line in maps.splitlines()):
            raise GateCError(f"Host native was not mapped: {native.name}")
        mapped.append({"path": str(native), "sha256": item["sha256"], "mapped": True})
    executable_dso_inventory = []
    seen_dso_paths = set()
    for line in maps.splitlines():
        match = re.match(r"^[0-9a-f]+-[0-9a-f]+\s+([rwxps-]{4})\s+\S+\s+\S+\s+\S+\s+(/.*)$", line)
        if match is None or "x" not in match.group(1):
            continue
        raw_path = match.group(2)
        if raw_path.endswith(" (deleted)"):
            raise GateCError(f"Deleted executable mapping cannot be anchored: {raw_path}")
        path = Path(raw_path)
        if raw_path in seen_dso_paths:
            continue
        seen_dso_paths.add(raw_path)
        exact = require_regular(path, "Executable mapped file")
        executable_dso_inventory.append({
            "path": str(exact),
            "sha256": sha256_file(exact),
            "bytes": exact.stat().st_size,
        })
    executable_dso_inventory.sort(key=lambda row: row["path"])
    if not executable_dso_inventory:
        raise GateCError("No executable file-backed mappings were inventoried")
    traces = sorted(path for path in trace_dir.iterdir() if path.is_file() and path.name.startswith("trace"))
    if not traces:
        raise GateCError("No syscall trace files")
    trace_records = [
        {"name": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for path in traces
    ]
    trace_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in traces)
    exec_records = []
    for line in trace_text.splitlines():
        match = re.search(r'\bexecve\("([^"]+)",', line)
        if match is None:
            match = re.search(r'\bexecveat\([^,]+, "([^"]+)",', line)
        if match is None:
            continue
        exec_records.append({"path": match.group(1), "line": line})
    expected_exec_paths = [supervisor["setpriv_path"], supervisor["env_path"], supervisor["java_path"]]
    if [record["path"] for record in exec_records] != expected_exec_paths:
        raise GateCError("Launcher/Java executable chain mismatch")
    if any(" = 0" not in record["line"] or "unfinished" in record["line"] for record in exec_records):
        raise GateCError("Launcher/Java exec did not complete successfully")
    required_setpriv_arguments = ("--reuid=", "--regid=", "--clear-groups", "--no-new-privs")
    missing_setpriv_arguments = [
        token for token in required_setpriv_arguments if token not in exec_records[0]["line"]
    ]
    setpriv_argv_shape = classify_exec_argv_shape(exec_records[0]["line"])
    setpriv_argv_abbreviated = setpriv_argv_shape in {
        "BRACKET_ELLIPSIS",
        "ARRAY_TRAILING_ELLIPSIS",
    }
    if missing_setpriv_arguments and not (
        missing_setpriv_arguments == list(required_setpriv_arguments) and setpriv_argv_abbreviated
    ):
        raise GateCError(
            "setpriv launcher arguments are incomplete: "
            + ",".join(missing_setpriv_arguments)
            + "; argv_shape="
            + setpriv_argv_shape
        )
    if '"-i"' not in exec_records[1]["line"]:
        raise GateCError("env launcher did not clear the environment")
    if not all(token in exec_records[2]["line"] for token in ("-XX:-UsePerfData", "org.phase9.gatec.GateCNativeMapProbe")):
        raise GateCError("Java probe arguments are incomplete")
    process_creations = []
    thread_clones = []
    for line in trace_text.splitlines():
        if re.search(r"\b(?:fork|vfork)\(", line):
            process_creations.append(line)
        elif re.search(r"\bclone3?\(", line):
            if "CLONE_THREAD" in line:
                thread_clones.append(line)
            else:
                process_creations.append(line)
    if process_creations:
        raise GateCError("Probe attempted a non-thread process creation syscall")
    prohibited_network = re.findall(
        r"\b(?:accept|accept4|bind|connect|getpeername|getsockname|getsockopt|listen|recv|recvfrom|recvmmsg|recvmsg|send|sendmmsg|sendmsg|sendto|setsockopt|shutdown|socket|socketcall|socketpair)\(",
        trace_text,
    )
    if prohibited_network:
        raise GateCError("Probe attempted a network syscall")
    result = {
        "schema_version": "phase9-gate-c1-runtime-observation-v1.0",
        "status": "GATE_C1_RUNTIME_OBSERVED_ACQUISITION_BLOCKED",
        "mapped_host_natives": mapped,
        "executable_file_mapping_count": len(executable_dso_inventory),
        "executable_file_mappings": executable_dso_inventory,
        "launcher_and_java_exec_count": len(exec_records),
        "launcher_and_java_exec_paths": expected_exec_paths,
        "setpriv_argv_observation": (
            "STRACE_ABBREVIATED_KERNEL_POSTCONDITIONS_VERIFIED"
            if setpriv_argv_abbreviated
            else "FULL_REQUIRED_ARGUMENTS_VERIFIED"
        ),
        "thread_clone_count": len(thread_clones),
        "child_process_spawned": False,
        "network_syscall_attempted": False,
        "os_network_namespace_required": True,
        "trace_file_count": len(traces),
        "trace_files": trace_records,
        **FALSE_FLAGS,
        "phase9_price_files_acquired": 0,
        "outcome_fields": [],
        "same_run_runtime_inventory_may_authorize": False,
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--runner", type=Path, required=True)
    scan.add_argument("--allowlist", type=Path, required=True)
    scan.add_argument("--extract-dir", type=Path, required=True)
    scan.add_argument("--output", type=Path, required=True)
    runtime = sub.add_parser("runtime")
    runtime.add_argument("--inventory", type=Path, required=True)
    runtime.add_argument("--maps", type=Path, required=True)
    runtime.add_argument("--trace-dir", type=Path, required=True)
    runtime.add_argument("--supervisor-identity", type=Path, required=True)
    runtime.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "scan":
        result = scan_runner(args.runner, args.allowlist, args.extract_dir)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        result = validate_runtime(
            args.inventory, args.maps, args.trace_dir, args.supervisor_identity, args.output
        )
    print(json.dumps({"status": result["status"], "acquisition_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
