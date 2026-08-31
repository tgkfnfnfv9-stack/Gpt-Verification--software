#!/usr/bin/env python3
"""Phase 9 S1B Gate A: verify locked JAR bytes, then inventory them without execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urljoin, urlsplit
from xml.etree import ElementTree


NATIVE_SUFFIXES = (".so", ".dll", ".dylib", ".jnilib")
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
}
CREDENTIAL_ENV_NAMES = ("DUKASCOPY_USERNAME", "DUKASCOPY_PASSWORD")
LOCK_ROW = re.compile(r"^([0-9a-f]{64})  \./([^\r\n]+\.jar)$")
DOWNLOAD_BLOCK_SIZE = 1024 * 1024


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(DOWNLOAD_BLOCK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"Audit target must not already exist: {path}")
    temporary = path.with_suffix(path.suffix + ".part")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"Temporary audit target already exists: {temporary}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def require_regular_file(path: Path, label: str) -> Path:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
        raise ValueError(f"{label} must be a regular, single-link, non-symlink file: {path}")
    return path.resolve(strict=True)


def safe_relative_jar(value: str) -> PurePosixPath:
    if "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe locked JAR path: {value!r}")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or not parsed.parts or ".." in parsed.parts or "." in parsed.parts:
        raise ValueError(f"Unsafe locked JAR path: {value!r}")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError(f"Unsafe locked JAR path: {value!r}")
    if not value.endswith(".jar"):
        raise ValueError(f"Locked dependency is not a JAR: {value!r}")
    return parsed


def parse_jar_lock(path: Path, policy: dict) -> list[tuple[str, str]]:
    exact = require_regular_file(path, "JAR lock")
    raw = exact.read_bytes()
    build_lock = policy["build_lock"]
    if sha256_bytes(raw) != build_lock["locked_jar_manifest_sha256"]:
        raise ValueError("Locked JAR manifest SHA-256 differs from the frozen policy.")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("Locked JAR manifest must be ASCII.") from error
    if not text.endswith("\n") or "\r" in text:
        raise ValueError("Locked JAR manifest must use final-LF Unix lines.")
    rows: list[tuple[str, str]] = []
    seen_paths: set[str] = set()
    for line in text.splitlines():
        match = LOCK_ROW.fullmatch(line)
        if match is None:
            raise ValueError(f"Invalid locked JAR row: {line!r}")
        digest, relative = match.groups()
        safe_relative_jar(relative)
        if relative in seen_paths:
            raise ValueError(f"Duplicate locked JAR path: {relative}")
        seen_paths.add(relative)
        rows.append((relative, digest))
    if len(rows) != build_lock["locked_jar_count"]:
        raise ValueError("Locked JAR count differs from the frozen policy.")
    return rows


def native_magic(value: bytes) -> str | None:
    if value.startswith(b"\x7fELF"):
        return "ELF"
    if value.startswith(b"MZ"):
        return "PE"
    if value[:4] in MACHO_MAGICS:
        return "MACHO"
    return None


def validate_archive_entry(name: str) -> PurePosixPath:
    if "\\" in name or "\x00" in name:
        raise ValueError(f"Unsafe archive entry name: {name!r}")
    parsed = PurePosixPath(name)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ValueError(f"Archive path traversal: {name!r}")
    return parsed


def scan_native_entries(archive: Path, archive_label: str, maximum_entry_bytes: int = 64 * 1024 * 1024) -> list[dict]:
    archive = require_regular_file(archive, "Verified JAR")
    output: list[dict] = []
    seen: set[str] = set()
    native_casefold: dict[str, str] = {}
    archive_sha = sha256_file(archive)
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            if info.is_dir():
                continue
            parsed = validate_archive_entry(info.filename)
            if info.filename in seen:
                raise ValueError(f"Duplicate archive entry in {archive_label}: {info.filename}")
            seen.add(info.filename)
            suffix_match = parsed.name.lower().endswith(NATIVE_SUFFIXES)
            with handle.open(info, "r") as entry:
                header = entry.read(4)
                magic = native_magic(header)
            # CAFEBABE is both the Java class-file magic and a Mach-O fat magic.
            # A .class entry inside a JAR is Java bytecode, not a native payload.
            if parsed.name.lower().endswith(".class") and header == b"\xca\xfe\xba\xbe":
                magic = None
            if not suffix_match and magic is None:
                continue
            if info.file_size > maximum_entry_bytes:
                raise ValueError(f"Native entry exceeds frozen size cap in {archive_label}: {info.filename}")
            folded = info.filename.casefold()
            previous = native_casefold.get(folded)
            if previous is not None and previous != info.filename:
                raise ValueError(f"Native case collision in {archive_label}: {previous}, {info.filename}")
            native_casefold[folded] = info.filename
            digest = hashlib.sha256()
            observed = 0
            with handle.open(info, "r") as entry:
                for block in iter(lambda: entry.read(DOWNLOAD_BLOCK_SIZE), b""):
                    observed += len(block)
                    if observed > maximum_entry_bytes:
                        raise ValueError(f"Native entry exceeds frozen size cap in {archive_label}: {info.filename}")
                    digest.update(block)
            output.append({
                "archive": archive_label, "archive_sha256": archive_sha,
                "entry": info.filename, "entry_size": observed,
                "entry_sha256": digest.hexdigest(), "magic": magic,
                "suffix_match": suffix_match,
            })
    return output


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise urllib.error.HTTPError(request.full_url, code, "Redirect prohibited", headers, file_pointer)


def repository_urls(relative: str, policy: dict) -> list[str]:
    safe_relative_jar(relative)
    bases = policy["locked_jar_download"]["allowed_repository_bases"]
    preferred = list(reversed(bases)) if relative.startswith("com/dukascopy/") else list(bases)
    encoded = "/".join(quote(part, safe="-._~") for part in PurePosixPath(relative).parts)
    urls: list[str] = []
    for base in preferred:
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)
            or not base.endswith("/")
        ):
            raise ValueError(f"Unsafe repository base URL in policy: {base}")
        urls.append(base + encoded)
    return urls


def download_locked_jar(relative: str, expected_sha256: str, root: Path, policy: dict, opener=None) -> dict:
    relative_path = safe_relative_jar(relative)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Download root must be a real directory.")
    target = root.joinpath(*relative_path.parts)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise ValueError(f"Locked JAR target must be new: {relative}")
    temporary = target.with_suffix(target.suffix + ".part")
    maximum = policy["locked_jar_download"]["maximum_jar_bytes"]
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
    last_404 = None
    for url in repository_urls(relative, policy):
        request = urllib.request.Request(url, headers={
            "Accept": "application/java-archive, application/octet-stream",
            "User-Agent": "phase9-s1b-locked-byte-audit/1.0",
        }, method="GET")
        digest = hashlib.sha256()
        observed = 0
        try:
            with opener.open(request, timeout=policy["locked_jar_download"]["timeout_seconds"]) as response:
                final_url = response.geturl()
                if final_url != url:
                    raise ValueError(f"Repository response URL changed without authorization: {url} -> {final_url}")
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > maximum:
                    raise ValueError(f"Locked JAR exceeds size cap: {relative}")
                with temporary.open("xb") as handle:
                    os.chmod(temporary, 0o600)
                    for block in iter(lambda: response.read(DOWNLOAD_BLOCK_SIZE), b""):
                        observed += len(block)
                        if observed > maximum:
                            raise ValueError(f"Locked JAR exceeds size cap: {relative}")
                        digest.update(block)
                        handle.write(block)
        except urllib.error.HTTPError as error:
            if temporary.exists():
                temporary.unlink()
            if error.code == 404:
                last_404 = error
                continue
            raise
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise
        actual = digest.hexdigest()
        if actual != expected_sha256:
            temporary.unlink()
            raise ValueError(f"Locked JAR SHA-256 mismatch: {relative}")
        os.replace(temporary, target)
        require_regular_file(target, "Downloaded locked JAR")
        return {
            "path": relative, "expected_sha256": expected_sha256,
            "actual_sha256": actual, "bytes": observed, "source_url": url,
            "verified_before_archive_parse": True,
        }
    raise ValueError(f"Locked JAR was not found on an allowed repository: {relative}") from last_404


def strict_https_url(value: str, allowed_host: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or parsed.hostname != allowed_host
        or parsed.username is not None or parsed.password is not None
        or parsed.query or parsed.fragment or parsed.port not in (None, 443)
    ):
        raise ValueError(f"JNLP URL violates the frozen static policy: {value}")
    if ".." in PurePosixPath(parsed.path).parts:
        raise ValueError(f"JNLP URL contains path traversal: {value}")
    return value


def inspect_local_jnlp(value: bytes, initial_url: str, policy: dict) -> dict:
    upper = value.upper()
    for prohibited in (b"<!DOCTYPE", b"<!ENTITY", b"XI:INCLUDE", b"XINCLUDE", b"W3.ORG/2001/XINCLUDE"):
        if prohibited in upper:
            raise ValueError("Local JNLP contains prohibited XML constructs.")
    allowed_initial = policy["jnlp_static_policy"]["allowed_initial_url"]
    if initial_url != allowed_initial:
        raise ValueError("Initial JNLP URL differs from the frozen static-policy value.")
    host = urlsplit(allowed_initial).hostname
    if host is None:
        raise ValueError("Frozen JNLP URL has no hostname.")
    strict_https_url(initial_url, host)
    try:
        root = ElementTree.fromstring(value)
    except ElementTree.ParseError as error:
        raise ValueError("Local JNLP is not well-formed XML.") from error
    if root.tag.split("}")[-1] != "jnlp":
        raise ValueError("Local descriptor root is not jnlp.")
    codebase = root.attrib.get("codebase", initial_url)
    strict_https_url(codebase, host)
    allowed_elements = set(policy["jnlp_static_policy"]["allowed_resource_elements"])
    resources: list[dict] = []
    for element in root.iter():
        local_name = element.tag.split("}")[-1]
        if local_name not in allowed_elements:
            continue
        href = element.attrib.get("href")
        if not href:
            raise ValueError(f"JNLP {local_name} element has no href.")
        if ".." in PurePosixPath(urlsplit(href).path).parts:
            raise ValueError(f"JNLP resource href contains path traversal: {href}")
        normalized = urljoin(codebase.rstrip("/") + "/", href)
        strict_https_url(normalized, host)
        resources.append({"kind": local_name, "url": normalized})
    if not resources:
        raise ValueError("Local JNLP has no auditable resources.")
    return {
        "schema_version": "phase9-local-jnlp-static-audit-v1.0",
        "status": "LOCAL_SYNTHETIC_DESCRIPTOR_PARSED_NO_NETWORK",
        "initial_url": initial_url, "raw_bytes": len(value), "raw_sha256": sha256_bytes(value),
        "resources": resources, "network_fetch_attempted": False,
        "jnlp_launch_invoked": False, "jforex_connect_invoked": False,
        "authorization_effect": "NONE",
    }


def run(args: argparse.Namespace) -> dict:
    for name in CREDENTIAL_ENV_NAMES:
        if os.environ.get(name):
            raise ValueError(f"Credential environment must be absent during Gate A: {name}")
    for source, label in ((args.policy, "Runtime policy"), (args.synthetic_jnlp, "Synthetic JNLP")):
        require_regular_file(source, label)
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    rows = parse_jar_lock(args.jar_lock, policy)
    if args.download_dir.exists() or args.download_dir.is_symlink():
        raise ValueError("Locked JAR download directory must not already exist.")
    args.download_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    downloads: list[dict] = []
    native_entries: list[dict] = []
    for relative, expected in rows:
        record = download_locked_jar(relative, expected, args.download_dir, policy)
        downloads.append(record)
        target = args.download_dir.joinpath(*PurePosixPath(relative).parts)
        if sha256_file(target) != expected:
            raise ValueError(f"Locked JAR changed before archive parsing: {relative}")
        native_entries.extend(scan_native_entries(target, f"locked-jar/{relative}"))
    native_entries.sort(key=lambda row: (row["archive"], row["entry"]))
    audit = {
        "schema_version": "phase9-runtime-envelope-gate-a-audit-v2.0",
        "status": "LOCKED_JAR_NATIVE_INVENTORY_RECORDED_AUTHORIZATION_BLOCKED",
        "locked_jar_count": len(rows),
        "locked_jar_manifest_sha256": sha256_file(args.jar_lock),
        "run5_maven_repository_inventory_line_count_recorded": policy["build_lock"]["maven_repository_inventory_line_count"],
        "run5_maven_repository_inventory_sha256_recorded": policy["build_lock"]["maven_repository_inventory_sha256"],
        "run5_runner_jar_sha256_recorded": policy["build_lock"]["runner_jar_sha256"],
        "native_entry_count": len(native_entries), "native_entries": native_entries,
        "java_class_cafebabe_collision_excluded": True,
        "maven_executed": False, "java_executed": False, "shaded_runner_scanned": False,
        "dukascopy_or_market_credentials_referenced": False,
        "external_jnlp_request_attempted": False, "jforex_connect_invoked": False,
        "market_price_request_attempted": False, "phase9_price_files_acquired": 0,
        "research_outcomes_calculated": False, "outcome_fields": [],
        "runtime_code_closure_verified": False, "acquisition_authorized": False,
        "blockers": [
            "NATIVE_ENTRY_ALLOWLIST_NOT_YET_COMMITTED", "SHADED_RUNNER_NOT_SCANNED_IN_GATE_A",
            "NATIVE_LOAD_AND_MAPPED_DSO_NOT_TESTED", "CHILD_PROCESS_AND_OS_EGRESS_NOT_ENFORCED",
            "REMOTE_JNLP_NOT_OBSERVED_OR_LOCKED", "ACTUAL_MARKET_DATA_FULL_QC_NOT_EXECUTED",
        ],
    }
    args.metadata_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    atomic_json(args.metadata_dir / "native_library_inventory.json", audit)
    atomic_json(args.metadata_dir / "locked_jar_downloads.json", {
        "schema_version": "phase9-locked-jar-download-audit-v1.0",
        "status": "ALL_LOCKED_JARS_SHA256_VERIFIED_BEFORE_PARSE",
        "redirects_allowed": False, "environment_proxy_used": False,
        "maven_executed": False, "java_executed": False, "records": downloads,
    })
    lock_copy = args.metadata_dir / "locked_jar_sha256.txt"
    lock_copy.write_bytes(args.jar_lock.read_bytes())
    os.chmod(lock_copy, 0o600)
    jnlp_audit = inspect_local_jnlp(
        args.synthetic_jnlp.read_bytes(), policy["jnlp_static_policy"]["allowed_initial_url"], policy
    )
    atomic_json(args.metadata_dir / "local_jnlp_synthetic_audit.json", jnlp_audit)
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jar-lock", type=Path, required=True)
    parser.add_argument("--download-dir", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--synthetic-jnlp", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({"status": result["status"], "native_entry_count": result["native_entry_count"]}, sort_keys=True))
