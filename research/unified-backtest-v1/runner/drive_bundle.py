#!/usr/bin/env python3
"""Download one owner-only Google Drive dataset bundle and extract it safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import ssl
import tarfile
import urllib.error
import urllib.parse
import urllib.request


DRIVE_HOST = "www.googleapis.com"
TOKEN_HOST = "oauth2.googleapis.com"
FILE_ID = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_BUNDLE_BYTES = 20_000_000_000
MAX_EXTRACTED_BYTES = 100_000_000_000
MAX_MEMBERS = 400


class DriveBundleError(RuntimeError):
    pass


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        raise DriveBundleError(f"Google API redirect prohibited: {code}")


def opener():
    return urllib.request.build_opener(RejectRedirects())


def access_token(client) -> str:
    values = {}
    for name in (
        "PHASE9_GDRIVE_OAUTH_CLIENT_ID",
        "PHASE9_GDRIVE_OAUTH_CLIENT_SECRET",
        "PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN",
    ):
        value = os.environ.get(name)
        if not value or any(character in value for character in "\r\n\x00"):
            raise DriveBundleError(f"missing/invalid OAuth environment: {name}")
        values[name] = value
    payload = urllib.parse.urlencode({
        "client_id": values["PHASE9_GDRIVE_OAUTH_CLIENT_ID"],
        "client_secret": values["PHASE9_GDRIVE_OAUTH_CLIENT_SECRET"],
        "refresh_token": values["PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode("ascii")
    request = urllib.request.Request(
        f"https://{TOKEN_HOST}/token", data=payload, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "unified-backtest-v1/1.0"},
    )
    try:
        with client.open(request, timeout=45) as response:
            body = response.read(128 * 1024)
            if response.status != 200:
                raise DriveBundleError("OAuth token exchange failed")
    except (urllib.error.URLError, ssl.SSLError, TimeoutError) as exc:
        raise DriveBundleError("OAuth token exchange failed") from exc
    try:
        token = json.loads(body)["access_token"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise DriveBundleError("invalid OAuth token response") from exc
    if not isinstance(token, str) or not token:
        raise DriveBundleError("invalid OAuth access token")
    return token


def drive_request(file_id: str, token: str, *, media: bool = False):
    if not FILE_ID.fullmatch(file_id):
        raise DriveBundleError("invalid Drive file id")
    suffix = "?alt=media" if media else (
        "?fields=id,name,mimeType,size,ownedByMe,trashed,driveId,shortcutDetails,"
        "permissionIds,permissions(id,type,role,allowFileDiscovery,deleted,pendingOwner)"
        "&supportsAllDrives=false"
    )
    return urllib.request.Request(
        f"https://{DRIVE_HOST}/drive/v3/files/{file_id}{suffix}", method="GET",
        headers={"Authorization": f"Bearer {token}", "User-Agent": "unified-backtest-v1/1.0"},
    )


def download(file_id: str, expected_bytes: int, expected_sha256: str, destination: Path) -> dict:
    if type(expected_bytes) is not int or not 0 < expected_bytes <= MAX_BUNDLE_BYTES or not HEX64.fullmatch(expected_sha256):
        raise DriveBundleError("invalid expected bundle identity")
    if destination.exists() or destination.is_symlink():
        raise DriveBundleError("bundle destination must be new")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < expected_bytes + 2_000_000_000:
        raise DriveBundleError("insufficient disk space for bundle plus safety margin")
    client = opener()
    token = access_token(client)
    try:
        with client.open(drive_request(file_id, token), timeout=90) as response:
            metadata = json.loads(response.read(1024 * 1024))
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DriveBundleError("Drive metadata read failed") from exc
    permissions = metadata.get("permissions")
    if (
        metadata.get("id") != file_id
        or metadata.get("ownedByMe") is not True
        or metadata.get("trashed") is not False
        or metadata.get("driveId") is not None
        or metadata.get("shortcutDetails") is not None
        or metadata.get("mimeType") not in ("application/gzip", "application/x-gzip", "application/octet-stream")
        or metadata.get("size") != str(expected_bytes)
        or not isinstance(permissions, list)
        or len(permissions) != 1
        or permissions[0].get("type") != "user"
        or permissions[0].get("role") != "owner"
        or metadata.get("permissionIds") != [permissions[0].get("id")]
    ):
        raise DriveBundleError("Drive bundle custody/identity mismatch")
    digest = hashlib.sha256()
    written = 0
    try:
        with client.open(drive_request(file_id, token, media=True), timeout=600) as response, destination.open("xb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > expected_bytes:
                    raise DriveBundleError("Drive bundle exceeded expected size")
                digest.update(chunk)
                output.write(chunk)
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as exc:
        raise DriveBundleError("Drive bundle download failed") from exc
    if written != expected_bytes or digest.hexdigest() != expected_sha256:
        raise DriveBundleError("Drive bundle byte/hash mismatch")
    return {"file_id": file_id, "bytes": written, "sha256": digest.hexdigest()}


def materialize(bundle: Path, destination: Path) -> None:
    if bundle.is_symlink() or not bundle.is_file() or bundle.stat().st_nlink != 1:
        raise DriveBundleError("unsafe bundle file")
    if destination.exists() or destination.is_symlink():
        raise DriveBundleError("dataset destination must be new")
    with tarfile.open(bundle, mode="r:gz") as archive:
        members = archive.getmembers()
        if not members or len(members) > MAX_MEMBERS:
            raise DriveBundleError("bundle member count mismatch")
        total = 0
        names = set()
        for member in members:
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
                raise DriveBundleError("unsafe bundle member path")
            if member.name in names:
                raise DriveBundleError("duplicate bundle member")
            names.add(member.name)
            if not (member.isdir() or member.isreg()) or member.issym() or member.islnk():
                raise DriveBundleError("bundle links/special members rejected")
            if member.isreg():
                total += member.size
                if member.size < 0 or member.size > MAX_BUNDLE_BYTES or total > MAX_EXTRACTED_BYTES:
                    raise DriveBundleError("bundle extraction resource limit exceeded")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(destination.parent).free < total + 2_000_000_000:
            raise DriveBundleError("insufficient disk space for extraction plus safety margin")
        destination.mkdir(parents=True)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise DriveBundleError("bundle member body missing")
            remaining = member.size
            with target.open("xb") as output:
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise DriveBundleError("truncated bundle member")
                    output.write(chunk)
                    remaining -= len(chunk)
                if source.read(1):
                    raise DriveBundleError("oversized bundle member")
    if not (destination / "DATASET_MANIFEST.json").is_file():
        raise DriveBundleError("DATASET_MANIFEST.json missing from bundle root")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    download_parser = subparsers.add_parser("download")
    download_parser.add_argument("--file-id", required=True)
    download_parser.add_argument("--expected-bytes", required=True, type=int)
    download_parser.add_argument("--expected-sha256", required=True)
    download_parser.add_argument("--output", required=True)
    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("--bundle", required=True)
    materialize_parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    try:
        if args.command == "download":
            download(args.file_id, args.expected_bytes, args.expected_sha256, Path(args.output))
        else:
            materialize(Path(args.bundle), Path(args.output_root))
    except DriveBundleError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"Drive bundle {args.command} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
