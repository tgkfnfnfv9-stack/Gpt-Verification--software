#!/usr/bin/env python3
"""Shared fail-closed primitives for the exploratory FXCM Drive vault."""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


UTC = timezone.utc
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FXCM_SOURCE_PATH = re.compile(r"^/(m1|H1|D1)/([A-Z]{6})/(20[0-9]{2})/([1-9]|[1-4][0-9]|5[0-2])\.csv\.gz$")
ROOT_FOLDER_ID = "1cGQrkdpSNY9RcfpniVTYNb6zE0t9nTKu"
YEARS = tuple(range(2010, 2026))
SYMBOLS = (
    "AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CADCHF", "CADJPY", "CHFJPY",
    "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD", "GBPAUD",
    "GBPCAD", "GBPCHF", "GBPJPY", "GBPNZD", "GBPUSD", "NZDCAD", "NZDCHF", "NZDJPY",
    "NZDUSD", "USDCAD", "USDCHF", "USDJPY",
)
DIRECT_PERIODICITIES = ("m1", "H1", "D1")
WEEKS = tuple(range(1, 53))
DIRECT_HEADER = (
    "DateTime", "BidOpen", "BidHigh", "BidLow", "BidClose",
    "AskOpen", "AskHigh", "AskLow", "AskClose",
)
CANONICAL_HEADER = (
    "timestamp_utc", "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close", "volume_status", "volume",
)
SECRET_NAMES = (
    "PHASE9_GDRIVE_OAUTH_CLIENT_ID",
    "PHASE9_GDRIVE_OAUTH_CLIENT_SECRET",
    "PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN",
)
PROHIBITED_OUTCOME_KEYS = {
    "signal", "signals", "entry", "entries", "trade", "trades", "return", "returns",
    "edge", "mfe", "mae", "win", "wins", "loss", "losses", "win_rate", "profit_factor",
    "drawdown", "profit", "pnl", "expectancy", "p_value", "pvalue", "confidence_interval",
    "outcome", "outcomes", "equity_curve", "sharpe", "sortino",
}
PUBLIC_AUDIT_FILES = ("VAULT_RUN_PRICE_FREE_AUDIT.json", "artifact_manifest_sha256.txt")


class VaultError(RuntimeError):
    """A fail-closed vault contract or custody violation."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def write_canonical_json(path: Path, value: Any) -> None:
    if path.exists() or path.is_symlink():
        raise VaultError(f"refusing to replace existing file: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def parse_utc(text: str) -> datetime:
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise VaultError("invalid canonical UTC timestamp") from None
    return parsed


def iso_utc(value: datetime) -> str:
    if value.tzinfo != UTC:
        value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_source_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    match = FXCM_SOURCE_PATH.fullmatch(parsed.path)
    try:
        port = parsed.port
    except ValueError:
        raise VaultError("FXCM source URL has an invalid port") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "candledata.fxcorporate.com"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or match is None
        or match.group(2) not in SYMBOLS
        or int(match.group(3)) not in YEARS
    ):
        raise VaultError("FXCM source URL is outside the exact pinned endpoint")
    return value


def source_url(contract: dict[str, Any], year: int, symbol: str, periodicity: str, week: int) -> str:
    value = contract["provider"]["base_url_template"].format(
        periodicity=periodicity, instrument=symbol, year=year, week=week
    )
    expected = f"https://candledata.fxcorporate.com/{periodicity}/{symbol}/{year}/{week}.csv.gz"
    if value != expected:
        raise VaultError("FXCM source URL template mismatch")
    return validate_source_url(value)


def iter_source_identities(contract: dict[str, Any]) -> Iterable[tuple[int, str, str, int, str]]:
    for year in YEARS:
        for symbol in SYMBOLS:
            for periodicity in DIRECT_PERIODICITIES:
                for week in WEEKS:
                    yield year, symbol, periodicity, week, source_url(contract, year, symbol, periodicity, week)


def expected_shard_keys() -> list[tuple[int, str, str]]:
    return [(year, symbol, periodicity) for year in YEARS for symbol in SYMBOLS for periodicity in DIRECT_PERIODICITIES]


def partition_for_year(partitions: dict[str, Any], year: int) -> dict[str, Any]:
    matches = [item for item in partitions["partitions"] if year in item["years"]]
    if len(matches) != 1:
        raise VaultError(f"year {year} does not map to exactly one partition")
    return matches[0]


def validate_safe_member(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or any(part in ("", ".") for part in path.parts):
        raise VaultError("unsafe archive member path")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VaultError(f"invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise VaultError(f"JSON root must be an object: {path.name}")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise VaultError(f"{label} key set mismatch")


def load_frozen_contracts(
    acquisition_path: Path, partitions_path: Path, manifest_schema_path: Path, formal_boundary_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    acquisition = load_json(acquisition_path)
    partitions = load_json(partitions_path)
    manifest = load_json(manifest_schema_path)
    formal = load_json(formal_boundary_path)
    checks = (
        (acquisition.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-acquisition-v1.0.0", "acquisition schema"),
        (acquisition.get("status") == "FROZEN_IMPLEMENTED_NOT_EXECUTED", "acquisition status"),
        (acquisition.get("vault_version") == "v1", "vault version"),
        (acquisition.get("track") == "EXPLORATORY_FXCM_DRIVE_VAULT_NOT_FORMAL_PHASE9", "track"),
        (acquisition.get("formal_phase9_authorization_effect") is False, "Formal authorization"),
        (acquisition.get("target", {}).get("years") == list(YEARS), "years"),
        (acquisition.get("target", {}).get("symbols") == list(SYMBOLS), "symbols"),
        (acquisition.get("target", {}).get("direct_periodicities") == list(DIRECT_PERIODICITIES), "direct periodicities"),
        (acquisition.get("target", {}).get("expected_shard_count") == 1344, "shard count"),
        (acquisition.get("target", {}).get("expected_source_object_count") == 69888, "source count"),
        (acquisition.get("provider", {}).get("endpoint_week_index_first") == 1, "week first"),
        (acquisition.get("provider", {}).get("endpoint_week_index_last") == 52, "week last"),
        (acquisition.get("direct_schema", {}).get("required_header") == list(DIRECT_HEADER), "direct header"),
        (acquisition.get("drive_custody", {}).get("root_folder_id") == ROOT_FOLDER_ID, "Drive root"),
        (acquisition.get("oauth", {}).get("secret_names") == list(SECRET_NAMES), "OAuth secrets"),
        (acquisition.get("oauth", {}).get("scope") == "https://www.googleapis.com/auth/drive.file", "OAuth scope"),
        (acquisition.get("research_boundaries", {}).get("price_acquisition_executed") is False, "price state"),
        (acquisition.get("research_boundaries", {}).get("count_only_authorized") is False, "Count authorization"),
        (acquisition.get("research_boundaries", {}).get("existing_batch6_workflow_may_run") is False, "Batch 6 block"),
        (partitions.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-partitions-v1.0.0", "partition schema"),
        (partitions.get("status") == "FROZEN_BEFORE_AVAILABILITY_OR_PRICE_ACCESS", "partition status"),
        (manifest.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-manifest-schema-v1.0.0", "manifest schema"),
        (manifest.get("year_manifest", {}).get("exact_shard_count") == 84, "year shard count"),
        (manifest.get("vault_manifest", {}).get("exact_shard_count") == 1344, "vault shard count"),
        (manifest.get("public_artifact", {}).get("exact_files") == list(PUBLIC_AUDIT_FILES), "public files"),
        (formal.get("schema_version") == "phase9-exploratory-fxcm-drive-vault-formal-boundary-v1.0.0", "formal boundary schema"),
        (formal.get("formal_phase9_authorization_effect") is False, "formal boundary authorization"),
        (formal.get("formal_split_effect_if_executed", {}).get("globally_unseen_formal_holdout_inside_vault") is False, "unseen claim"),
    )
    for passed, label in checks:
        if not passed:
            raise VaultError(f"frozen vault contract mismatch: {label}")
    if len(expected_shard_keys()) != 1344 or sum(1 for _ in iter_source_identities(acquisition)) != 69888:
        raise VaultError("derived contract inventory count mismatch")
    if len(set(expected_shard_keys())) != 1344:
        raise VaultError("duplicate expected shard")
    all_years: list[int] = []
    previous_end = partitions["outer_interval"]["start_inclusive"]
    for item in partitions["partitions"]:
        if item["start_inclusive"] != previous_end:
            raise VaultError("partition gap or overlap")
        previous_end = item["end_exclusive"]
        all_years.extend(item["years"])
    if previous_end != partitions["outer_interval"]["end_exclusive"] or all_years != list(YEARS):
        raise VaultError("partition coverage mismatch")
    if acquisition["canonical_and_reference_roles"]["canonical_strategy_source"] != "CLOSED_DIRECT_M1_ROWS_AFTER_QC":
        raise VaultError("M1 is not canonical")
    if acquisition["canonical_and_reference_roles"]["direct_H1"] != "QC_REFERENCE_ONLY_NEVER_FILL_OR_SUBSTITUTE":
        raise VaultError("direct H1 role mismatch")
    if acquisition["canonical_and_reference_roles"]["direct_D1"] != "QC_REFERENCE_ONLY_NEVER_FILL_OR_SUBSTITUTE":
        raise VaultError("direct D1 role mismatch")
    return acquisition, partitions, manifest, formal


def require_exact_confirmations(
    acquisition: dict[str, Any], confirmation: str, usage_confirmation: str, formal_acknowledgement: str, expected_mode: str
) -> None:
    workflow = acquisition["workflow"]
    expected = workflow["availability_confirmation"] if expected_mode == "availability" else workflow["acquisition_confirmation"]
    if confirmation != expected:
        raise VaultError("confirmation mismatch")
    if usage_confirmation != workflow["usage_confirmation"]:
        raise VaultError("usage confirmation mismatch")
    required = "I_ACCEPT_EXPLORATORY_VAULT_2019_PLUS_RETIRES_FORMAL_PHASE9_UNSEEN_CLAIMS"
    if formal_acknowledgement != required:
        raise VaultError("Formal boundary acknowledgement mismatch")


def require_oauth_environment() -> dict[str, str]:
    values = {name: os.environ.get(name, "") for name in SECRET_NAMES}
    if any(not value for value in values.values()):
        raise VaultError("required Google OAuth secret is missing")
    return values


def reject_prohibited_keys(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in PROHIBITED_OUTCOME_KEYS:
                raise VaultError(f"prohibited outcome field at {'/'.join(path + (str(key),))}")
            reject_prohibited_keys(child, path + (str(key),))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_prohibited_keys(child, path + (str(index),))


def validate_public_report_tree(report_dir: Path) -> dict[str, Any]:
    if report_dir.is_symlink() or not report_dir.is_dir():
        raise VaultError("public report directory is invalid")
    entries = sorted(report_dir.iterdir(), key=lambda item: item.name)
    if [item.name for item in entries] != list(PUBLIC_AUDIT_FILES):
        raise VaultError("public report file set mismatch")
    total = 0
    for item in entries:
        stat = item.lstat()
        if item.is_symlink() or not item.is_file() or stat.st_nlink != 1:
            raise VaultError("public report contains unsafe file")
        total += stat.st_size
    if total > 1024 * 1024:
        raise VaultError("public report exceeds byte limit")
    audit_path = report_dir / PUBLIC_AUDIT_FILES[0]
    audit = load_json(audit_path)
    reject_prohibited_keys(audit)
    serialized = canonical_json_bytes(audit).lower()
    forbidden_fragments = (b"timestamp_utc", b"drive_file_id", b"access_token", b"refresh_token", b"resumable", b"bid_open", b"ask_open")
    if any(fragment in serialized for fragment in forbidden_fragments):
        raise VaultError("public report contains private or price-bearing field")
    manifest_line = (report_dir / PUBLIC_AUDIT_FILES[1]).read_text(encoding="ascii")
    expected_line = f"{sha256_file(audit_path)}  {audit_path.name}\n"
    if manifest_line != expected_line:
        raise VaultError("public report manifest mismatch")
    return audit


def contract_sha_bundle(paths: Iterable[Path]) -> dict[str, str]:
    return {path.name: sha256_file(path) for path in paths}


def assert_hex64(value: object, label: str) -> None:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise VaultError(f"invalid SHA-256: {label}")
