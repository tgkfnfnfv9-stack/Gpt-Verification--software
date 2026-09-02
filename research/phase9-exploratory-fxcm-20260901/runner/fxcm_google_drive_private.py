#!/usr/bin/env python3
"""Minimal in-repo Google Drive client with secrets kept out of argv and files."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fxcm_drive_vault_common import ROOT_FOLDER_ID, VaultError, canonical_json_bytes, require_oauth_environment


DRIVE_API_HOST = "www.googleapis.com"
DRIVE_UPLOAD_HOSTS = {"www.googleapis.com", "content.googleapis.com"}
TOKEN_HOST = "oauth2.googleapis.com"
FOLDER_MIME = "application/vnd.google-apps.folder"


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise VaultError(f"Google API redirect prohibited: {code}")


class GoogleDrivePrivate:
    def __init__(self) -> None:
        secrets = require_oauth_environment()
        self._client_id = secrets["PHASE9_GDRIVE_OAUTH_CLIENT_ID"]
        self._client_secret = secrets["PHASE9_GDRIVE_OAUTH_CLIENT_SECRET"]
        self._refresh_token = secrets["PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN"]
        self._opener = urllib.request.build_opener(RejectRedirects())
        self._access_token: str | None = None

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        encoded = urllib.parse.urlencode({
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
        }).encode("ascii")
        request = urllib.request.Request(
            f"https://{TOKEN_HOST}/token",
            data=encoded,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "phase9-fxcm-vault/1.0"},
        )
        try:
            with self._opener.open(request, timeout=45) as response:
                if response.status != 200:
                    raise VaultError("OAuth token exchange failed")
                body = response.read(128 * 1024)
        except (urllib.error.URLError, ssl.SSLError, TimeoutError) as exc:
            raise VaultError("OAuth token exchange failed") from exc
        try:
            value = json.loads(body)
            token = value["access_token"]
            if not isinstance(token, str) or not token:
                raise KeyError
        except (json.JSONDecodeError, KeyError, TypeError):
            raise VaultError("OAuth token response invalid") from None
        self._access_token = token
        return token

    def _json_request(self, method: str, url: str, payload: dict | None = None) -> dict:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != DRIVE_API_HOST:
            raise VaultError("Drive API host mismatch")
        data = canonical_json_bytes(payload) if payload is not None else None
        headers = {"Authorization": f"Bearer {self._token()}", "User-Agent": "phase9-fxcm-vault/1.0"}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=UTF-8"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self._opener.open(request, timeout=90) as response:
                if response.status not in (200, 201):
                    raise VaultError("Drive API request failed")
                body = response.read(4 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            raise VaultError(f"Drive API HTTP failure: {exc.code}") from None
        except (urllib.error.URLError, ssl.SSLError, TimeoutError) as exc:
            raise VaultError("Drive API request failed") from exc
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            raise VaultError("Drive API returned invalid JSON") from None
        if not isinstance(value, dict):
            raise VaultError("Drive API JSON root is not an object")
        return value

    def verify_root(self, expected_name: str, root_folder_id: str = ROOT_FOLDER_ID) -> dict:
        fields = "id,name,mimeType,ownedByMe,trashed,driveId,shortcutDetails,parents"
        value = self._json_request("GET", f"https://{DRIVE_API_HOST}/drive/v3/files/{root_folder_id}?fields={fields}&supportsAllDrives=false")
        if value.get("id") != root_folder_id or value.get("name") != expected_name:
            raise VaultError("Drive root identity mismatch")
        if value.get("mimeType") != FOLDER_MIME or value.get("ownedByMe") is not True or value.get("trashed") is not False:
            raise VaultError("Drive root custody mismatch")
        if value.get("driveId") is not None or value.get("shortcutDetails") is not None:
            raise VaultError("shared-drive or shortcut root prohibited")
        return value

    def list_children(self, parent_id: str) -> list[dict]:
        query = urllib.parse.quote(f"'{parent_id}' in parents and trashed = false", safe="")
        fields = urllib.parse.quote("nextPageToken,files(id,name,mimeType,size,md5Checksum,parents,appProperties,trashed,shortcutDetails)", safe="(),")
        page_token = ""
        rows: list[dict] = []
        while True:
            suffix = f"&pageToken={urllib.parse.quote(page_token)}" if page_token else ""
            value = self._json_request(
                "GET", f"https://{DRIVE_API_HOST}/drive/v3/files?q={query}&spaces=drive&pageSize=1000&fields={fields}{suffix}"
            )
            files = value.get("files")
            if not isinstance(files, list):
                raise VaultError("Drive child listing malformed")
            rows.extend(files)
            page_token = value.get("nextPageToken", "")
            if not page_token:
                break
        ids = [row.get("id") for row in rows]
        if any(not isinstance(item, str) for item in ids) or len(ids) != len(set(ids)):
            raise VaultError("Drive listing contains invalid duplicate IDs")
        return rows

    def create_folder_new(self, parent_id: str, name: str, app_properties: dict[str, str]) -> dict:
        if "/" in name or name in ("", ".", ".."):
            raise VaultError("invalid Drive folder name")
        if any(row.get("name") == name for row in self.list_children(parent_id)):
            raise VaultError("Drive destination name already exists")
        payload = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id], "appProperties": app_properties}
        fields = "id,name,mimeType,parents,appProperties"
        value = self._json_request("POST", f"https://{DRIVE_API_HOST}/drive/v3/files?fields={fields}&supportsAllDrives=false", payload)
        if value.get("name") != name or value.get("mimeType") != FOLDER_MIME or value.get("parents") != [parent_id]:
            raise VaultError("created Drive folder identity mismatch")
        return value

    def _start_resumable(self, parent_id: str, name: str, size: int, mime_type: str, app_properties: dict[str, str]) -> str:
        query = "uploadType=resumable&fields=id,name,size,parents,appProperties"
        url = f"https://{DRIVE_API_HOST}/upload/drive/v3/files?{query}"
        parsed = urllib.parse.urlsplit(url)
        payload = canonical_json_bytes({"name": name, "parents": [parent_id], "appProperties": app_properties})
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": mime_type,
            "X-Upload-Content-Length": str(size),
            "User-Agent": "phase9-fxcm-vault/1.0",
        }
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=90)
        try:
            connection.request("POST", parsed.path + "?" + parsed.query, body=payload, headers=headers)
            response = connection.getresponse()
            response.read(128 * 1024)
            if response.status not in (200, 201):
                raise VaultError("Drive resumable initialization failed")
            location = response.getheader("Location")
        finally:
            connection.close()
        if not location:
            raise VaultError("Drive resumable URL missing")
        location_parts = urllib.parse.urlsplit(location)
        if location_parts.scheme != "https" or location_parts.hostname not in DRIVE_UPLOAD_HOSTS:
            raise VaultError("Drive resumable host mismatch")
        return location

    def upload_file_new(
        self, parent_id: str, path: Path, remote_name: str, mime_type: str, app_properties: dict[str, str]
    ) -> dict:
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise VaultError("unsafe local upload file")
        if any(row.get("name") == remote_name for row in self.list_children(parent_id)):
            raise VaultError("Drive upload destination already exists")
        size = path.stat().st_size
        location = self._start_resumable(parent_id, remote_name, size, mime_type, app_properties)
        parsed = urllib.parse.urlsplit(location)
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": mime_type,
            "Content-Length": str(size),
            "User-Agent": "phase9-fxcm-vault/1.0",
        }
        connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=600)
        try:
            connection.putrequest("PUT", parsed.path + ("?" + parsed.query if parsed.query else ""))
            for key, value in headers.items():
                connection.putheader(key, value)
            connection.endheaders()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    connection.send(block)
            response = connection.getresponse()
            body = response.read(1024 * 1024)
            if response.status not in (200, 201):
                raise VaultError("Drive resumable upload failed")
        finally:
            connection.close()
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            raise VaultError("Drive upload response invalid") from None
        if value.get("name") != remote_name or value.get("parents") != [parent_id] or int(value.get("size", -1)) != size:
            raise VaultError("Drive upload identity mismatch")
        return value

    def download_verify(self, file_id: str, destination: Path, expected_size: int, expected_sha256: str) -> None:
        if destination.exists() or destination.is_symlink():
            raise VaultError("Drive verification destination must be new")
        url = f"https://{DRIVE_API_HOST}/drive/v3/files/{file_id}?alt=media"
        request = urllib.request.Request(
            url, method="GET", headers={"Authorization": f"Bearer {self._token()}", "User-Agent": "phase9-fxcm-vault/1.0"}
        )
        digest = hashlib.sha256()
        total = 0
        try:
            with self._opener.open(request, timeout=600) as response, destination.open("xb") as handle:
                if response.status != 200:
                    raise VaultError("Drive verification download failed")
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    total += len(block)
                    if total > expected_size:
                        raise VaultError("Drive verification byte overflow")
                    digest.update(block)
                    handle.write(block)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        if total != expected_size or digest.hexdigest() != expected_sha256:
            destination.unlink(missing_ok=True)
            raise VaultError("Drive redownload SHA-256 mismatch")

    def move_file(
        self, file_id: str, old_parent_id: str, new_parent_id: str, app_properties: dict[str, str] | None = None
    ) -> dict:
        query = urllib.parse.urlencode({
            "addParents": new_parent_id,
            "removeParents": old_parent_id,
            "fields": "id,name,size,parents,appProperties",
            "supportsAllDrives": "false",
        })
        payload = {"appProperties": app_properties} if app_properties is not None else {}
        value = self._json_request("PATCH", f"https://{DRIVE_API_HOST}/drive/v3/files/{file_id}?{query}", payload)
        if value.get("parents") != [new_parent_id]:
            raise VaultError("Drive move parent mismatch")
        return value
