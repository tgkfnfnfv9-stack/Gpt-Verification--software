#!/usr/bin/env python3
"""Fetch the frozen Run 5 Maven JAR/POM closure as opaque verified bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit


EXPECTED_LOCK_SHA256 = "94838ee9280ba2f02adb456129c01bb32bd7e17d4909ac3e43a1556f74c8964c"
EXPECTED_COUNT = 341
MAXIMUM_BYTES = 268435456
LOCK_ROW = re.compile(r"^([0-9a-f]{64})  \./([^\r\n]+\.(?:jar|pom))$")
REPOSITORY_BASES = (
    "https://repo.maven.apache.org/maven2/",
    "https://www.dukascopy.com/client/jforexlib/publicrepo/",
)


class PrefetchError(ValueError):
    pass


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise urllib.error.HTTPError(request.full_url, code, "Redirect prohibited", headers, file_pointer)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_regular(path: Path, label: str) -> Path:
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise PrefetchError(f"{label} must be a single-link regular file")
    return path.resolve(strict=True)


def safe_path(value: str) -> PurePosixPath:
    if "\\" in value or "\x00" in value:
        raise PrefetchError(f"Unsafe Maven path: {value!r}")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or not parsed.parts or "." in parsed.parts or ".." in parsed.parts:
        raise PrefetchError(f"Unsafe Maven path: {value!r}")
    if not value.endswith((".jar", ".pom")):
        raise PrefetchError(f"Unexpected Maven artifact type: {value!r}")
    return parsed


def parse_lock(path: Path) -> list[tuple[str, str]]:
    exact = require_regular(path, "Maven build lock")
    if sha256_file(exact) != EXPECTED_LOCK_SHA256:
        raise PrefetchError("Maven build lock SHA-256 mismatch")
    text = exact.read_text(encoding="ascii")
    if not text.endswith("\n") or "\r" in text:
        raise PrefetchError("Maven build lock must use final-LF Unix lines")
    output = []
    folded = set()
    for line in text.splitlines():
        match = LOCK_ROW.fullmatch(line)
        if match is None:
            raise PrefetchError(f"Malformed Maven build lock row: {line!r}")
        digest, relative = match.groups()
        safe_path(relative)
        if relative.casefold() in folded:
            raise PrefetchError(f"Duplicate or case-colliding Maven path: {relative}")
        folded.add(relative.casefold())
        output.append((relative, digest))
    if len(output) != EXPECTED_COUNT:
        raise PrefetchError("Maven build lock count mismatch")
    return output


def urls(relative: str) -> list[str]:
    parsed = safe_path(relative)
    encoded = "/".join(quote(part, safe="-._~") for part in parsed.parts)
    bases = list(REPOSITORY_BASES)
    if relative.startswith("com/dukascopy/"):
        bases.reverse()
    output = []
    for base in bases:
        split = urlsplit(base)
        if split.scheme != "https" or split.query or split.fragment or split.username or split.password or not base.endswith("/"):
            raise PrefetchError("Unsafe frozen Maven repository base")
        output.append(base + encoded)
    return output


def download(relative: str, expected: str, root: Path, opener) -> dict:
    parsed = safe_path(relative)
    target = root.joinpath(*parsed.parts)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise PrefetchError(f"Maven target must be new: {relative}")
    temporary = target.with_suffix(target.suffix + ".part")
    last_404 = None
    mismatched_sources = []
    for url in urls(relative):
        request = urllib.request.Request(url, headers={"User-Agent": "phase9-gate-c1-opaque-prefetch/1.0"}, method="GET")
        digest = hashlib.sha256()
        observed = 0
        try:
            with opener.open(request, timeout=60) as response:
                if response.geturl() != url:
                    raise PrefetchError("Maven response URL changed")
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > MAXIMUM_BYTES:
                    raise PrefetchError(f"Maven artifact exceeds size cap: {relative}")
                with temporary.open("xb") as handle:
                    os.chmod(temporary, 0o600)
                    for block in iter(lambda: response.read(1024 * 1024), b""):
                        observed += len(block)
                        if observed > MAXIMUM_BYTES:
                            raise PrefetchError(f"Maven artifact exceeds size cap: {relative}")
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
        if actual != expected:
            temporary.unlink()
            mismatched_sources.append(url)
            continue
        os.replace(temporary, target)
        require_regular(target, "Downloaded Maven artifact")
        return {"path": relative, "sha256": actual, "bytes": observed, "source_url": url}
    if mismatched_sources:
        raise PrefetchError(
            f"Maven artifact SHA-256 mismatch at every available repository: {relative}"
        )
    raise PrefetchError(f"Frozen Maven artifact not found: {relative}") from last_404


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    rows = parse_lock(args.lock)
    if args.output_root.exists() or args.output_root.is_symlink():
        raise PrefetchError("Maven output root must be new")
    args.output_root.mkdir(mode=0o700, parents=False)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
    records = [download(relative, digest, args.output_root, opener) for relative, digest in rows]
    for relative, digest in rows:
        if sha256_file(args.output_root.joinpath(*PurePosixPath(relative).parts)) != digest:
            raise PrefetchError(f"Maven artifact changed before seal: {relative}")
    audit = {
        "schema_version": "phase9-gate-c1-maven-opaque-prefetch-v1.0",
        "status": "FROZEN_MAVEN_BYTES_VERIFIED_BEFORE_EXECUTION",
        "lock_sha256": EXPECTED_LOCK_SHA256,
        "artifact_count": len(records),
        "redirects_allowed": False,
        "environment_proxy_used": False,
        "maven_executed_before_verification": False,
        "credentials_referenced": False,
        "external_jnlp_request_attempted": False,
        "market_price_request_attempted": False,
        "phase9_price_files_acquired": 0,
        "research_outcomes_calculated": False,
        "acquisition_authorized": False,
        "records": records,
    }
    args.audit.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "artifact_count": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
