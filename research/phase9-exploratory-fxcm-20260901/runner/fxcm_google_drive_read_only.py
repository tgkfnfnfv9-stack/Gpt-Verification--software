#!/usr/bin/env python3
"""Minimal Google Drive metadata client with no Drive mutation or media path."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fxcm_drive_vault_common import VaultError, require_oauth_environment


DRIVE_API_HOST = "www.googleapis.com"
TOKEN_HOST = "oauth2.googleapis.com"
FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT_FOLDER_ID = "1lZ0CkTn3tBxStf5H3V7W38ZcOsZ5Rw_v"
IDENTITY_FIELDS = (
    "id,name,mimeType,size,parents,appProperties,ownedByMe,trashed,driveId,shortcutDetails,"
    "permissionIds,permissions(id,type,role,allowFileDiscovery,deleted,pendingOwner)"
)


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise VaultError(f"Google API redirect prohibited: {code}")


class GoogleDriveReadOnly:
    """Expose only identity GET and child-list GET operations."""

    def __init__(self) -> None:
        secrets = require_oauth_environment()
        self._client_id = secrets["PHASE9_GDRIVE_OAUTH_CLIENT_ID"]
        self._client_secret = secrets["PHASE9_GDRIVE_OAUTH_CLIENT_SECRET"]
        self._refresh_token = secrets["PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN"]
        self._opener = urllib.request.build_opener(RejectRedirects())
        self._access_token: str | None = None
        self._owner_permission_id: str | None = None

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
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "phase9-fxcm-vault-read-only-inventory/1.0",
            },
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

    def _drive_json_get(self, url: str) -> dict[str, Any]:
        parsed = urllib.parse.urlsplit(url)
        try:
            port = parsed.port
        except ValueError:
            raise VaultError("Drive API port mismatch") from None
        if (
            parsed.scheme != "https"
            or parsed.hostname != DRIVE_API_HOST
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise VaultError("Drive API host mismatch")
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if parsed.path == f"/drive/v3/files/{ROOT_FOLDER_ID}":
            if set(query) != {"fields", "supportsAllDrives"} or query["supportsAllDrives"] != ["false"]:
                raise VaultError("Drive root metadata GET query mismatch")
        elif parsed.path == "/drive/v3/files":
            required = {"q", "spaces", "pageSize", "fields"}
            if (
                not required.issubset(query)
                or not set(query).issubset(required | {"pageToken"})
                or query["spaces"] != ["drive"]
                or query["pageSize"] != ["1000"]
            ):
                raise VaultError("Drive child metadata GET query mismatch")
        else:
            raise VaultError("Drive metadata GET path mismatch")
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self._token()}",
                "User-Agent": "phase9-fxcm-vault-read-only-inventory/1.0",
            },
        )
        try:
            with self._opener.open(request, timeout=90) as response:
                if response.status != 200:
                    raise VaultError("Drive metadata GET failed")
                body = response.read(4 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            raise VaultError(f"Drive metadata GET HTTP failure: {exc.code}") from None
        except (urllib.error.URLError, ssl.SSLError, TimeoutError) as exc:
            raise VaultError("Drive metadata GET failed") from exc
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            raise VaultError("Drive metadata GET returned invalid JSON") from None
        if not isinstance(value, dict):
            raise VaultError("Drive metadata JSON root is not an object")
        return value

    @staticmethod
    def _verify_owned(value: dict[str, Any], expected_parent: str | None = None) -> None:
        if (
            value.get("ownedByMe") is not True
            or value.get("trashed") is not False
            or value.get("driveId") is not None
            or value.get("shortcutDetails") is not None
            or (expected_parent is not None and value.get("parents") != [expected_parent])
        ):
            raise VaultError("Drive metadata custody mismatch")

    def _verify_private(self, value: dict[str, Any]) -> None:
        self._verify_owned(value)
        if self._owner_permission_id is None:
            return
        permissions = value.get("permissions")
        if (
            value.get("permissionIds") != [self._owner_permission_id]
            or not isinstance(permissions, list)
            or len(permissions) != 1
            or not isinstance(permissions[0], dict)
            or permissions[0].get("id") != self._owner_permission_id
            or permissions[0].get("type") != "user"
            or permissions[0].get("role") != "owner"
            or permissions[0].get("deleted") not in (None, False)
            or permissions[0].get("pendingOwner") not in (None, False)
            or permissions[0].get("allowFileDiscovery") not in (None, False)
        ):
            raise VaultError("Drive object sharing metadata is not owner-only")

    def verify_private_root(self, root_folder_id: str, expected_name: str) -> dict[str, Any]:
        if root_folder_id != ROOT_FOLDER_ID:
            raise VaultError("Drive root ID mismatch")
        fields = urllib.parse.quote(IDENTITY_FIELDS, safe="(),")
        value = self._drive_json_get(
            f"https://{DRIVE_API_HOST}/drive/v3/files/{root_folder_id}?fields={fields}&supportsAllDrives=false"
        )
        self._verify_owned(value)
        permissions = value.get("permissions")
        permission_ids = value.get("permissionIds")
        if (
            value.get("id") != root_folder_id
            or value.get("name") != expected_name
            or value.get("mimeType") != FOLDER_MIME
            or not isinstance(permissions, list)
            or len(permissions) != 1
            or not isinstance(permissions[0], dict)
            or permissions[0].get("type") != "user"
            or permissions[0].get("role") != "owner"
            or permissions[0].get("deleted") not in (None, False)
            or permissions[0].get("pendingOwner") not in (None, False)
            or permissions[0].get("allowFileDiscovery") not in (None, False)
            or not isinstance(permissions[0].get("id"), str)
            or permission_ids != [permissions[0]["id"]]
        ):
            raise VaultError("Drive root is not the exact owner-only root")
        self._owner_permission_id = permissions[0]["id"]
        return value

    def list_children(self, parent_id: str) -> list[dict[str, Any]]:
        query = urllib.parse.quote(f"'{parent_id}' in parents and trashed = false", safe="")
        fields = urllib.parse.quote(f"nextPageToken,files({IDENTITY_FIELDS})", safe="(),")
        rows: list[dict[str, Any]] = []
        page_token = ""
        while True:
            suffix = f"&pageToken={urllib.parse.quote(page_token)}" if page_token else ""
            value = self._drive_json_get(
                f"https://{DRIVE_API_HOST}/drive/v3/files?q={query}&spaces=drive&pageSize=1000&fields={fields}{suffix}"
            )
            files = value.get("files")
            if not isinstance(files, list):
                raise VaultError("Drive child metadata listing malformed")
            rows.extend(files)
            page_token = value.get("nextPageToken", "")
            if not page_token:
                break
            if not isinstance(page_token, str):
                raise VaultError("Drive page token malformed")
        ids = [row.get("id") for row in rows]
        if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
            raise VaultError("Drive child metadata contains invalid duplicate IDs")
        for row in rows:
            self._verify_owned(row, parent_id)
            self._verify_private(row)
        return rows
