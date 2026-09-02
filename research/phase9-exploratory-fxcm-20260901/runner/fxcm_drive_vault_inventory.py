#!/usr/bin/env python3
"""HEAD-only FXCM vault availability inventory; never reads response bodies."""

from __future__ import annotations

import argparse
import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

from fxcm_drive_vault_common import (
    DIRECT_PERIODICITIES,
    SYMBOLS,
    WEEKS,
    YEARS,
    VaultError,
    canonical_sha256,
    contract_sha_bundle,
    load_frozen_contracts,
    require_exact_confirmations,
    sha256_file,
    source_url,
    write_canonical_json,
)


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise VaultError(f"redirect prohibited during availability inventory: {code}")


def head_status(opener, url: str, attempts: int = 3) -> tuple[int, int | None, str | None]:
    """Return status/content-length/error class without reading a response byte."""
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "phase9-fxcm-drive-vault-inventory/1.0"})
        try:
            with opener.open(request, timeout=45) as response:
                status = int(response.status)
                length_text = response.headers.get("Content-Length")
                length = int(length_text) if length_text and length_text.isdigit() else None
                return status, length, None
        except urllib.error.HTTPError as error:
            if error.code in (404, 410):
                return error.code, None, "MISSING"
            if error.code in (429, 500, 502, 503, 504) and attempt < attempts:
                time.sleep(2 ** (attempt - 1))
                continue
            return error.code, None, "HTTP_ERROR"
        except (urllib.error.URLError, ConnectionError, TimeoutError, ssl.SSLError) as error:
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
                continue
            return 0, None, type(error).__name__
    raise AssertionError("unreachable")


def inventory_year(contract: dict, year: int, opener=None, pause_seconds: float = 0.02) -> dict:
    if year not in YEARS:
        raise VaultError("year outside frozen inventory scope")
    opener = opener or urllib.request.build_opener(RejectRedirects())
    objects = []
    for symbol in SYMBOLS:
        for periodicity in DIRECT_PERIODICITIES:
            for week in WEEKS:
                url = source_url(contract, year, symbol, periodicity, week)
                status, content_length, error_class = head_status(opener, url)
                objects.append({
                    "year": year,
                    "symbol": symbol,
                    "periodicity": periodicity,
                    "week_index": week,
                    "url": url,
                    "http_status": status,
                    "content_length": content_length,
                    "availability": "PRESENT" if status == 200 else "MISSING_OR_UNAVAILABLE",
                    "error_class": error_class,
                })
                if pause_seconds:
                    time.sleep(pause_seconds)
    if len(objects) != 28 * 3 * 52 or len({row["url"] for row in objects}) != len(objects):
        raise VaultError("availability object inventory mismatch")
    present = sum(row["http_status"] == 200 for row in objects)
    return {
        "schema_version": "phase9-exploratory-fxcm-drive-vault-availability-year-v1.0.0",
        "status": "COMPLETE_HEAD_ONLY_NO_RESPONSE_BODY",
        "year": year,
        "source_object_count": len(objects),
        "present_count": present,
        "missing_or_unavailable_count": len(objects) - present,
        "all_target_objects_present": present == len(objects),
        "scope_shrunk": False,
        "price_response_body_bytes_read": 0,
        "price_acquisition_authorized": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "objects_sha256": canonical_sha256(objects),
        "objects": objects,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-contract", type=Path, required=True)
    parser.add_argument("--partitions-contract", type=Path, required=True)
    parser.add_argument("--manifest-schema", type=Path, required=True)
    parser.add_argument("--formal-boundary", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--usage-confirmation", required=True)
    parser.add_argument("--formal-acknowledgement", required=True)
    args = parser.parse_args()
    contract, _, _, _ = load_frozen_contracts(
        args.acquisition_contract, args.partitions_contract, args.manifest_schema, args.formal_boundary
    )
    require_exact_confirmations(
        contract, args.confirmation, args.usage_confirmation, args.formal_acknowledgement, "availability"
    )
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise VaultError("output directory must not exist")
    args.output_dir.mkdir(parents=True)
    result = inventory_year(contract, args.year)
    result["contract_sha256"] = contract_sha_bundle((
        args.acquisition_contract, args.partitions_contract, args.manifest_schema, args.formal_boundary
    ))
    report = args.output_dir / "FXCM_VAULT_AVAILABILITY_YEAR.json"
    write_canonical_json(report, result)
    (args.output_dir / "artifact_manifest_sha256.txt").write_text(
        f"{sha256_file(report)}  {report.name}\n", encoding="ascii"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
