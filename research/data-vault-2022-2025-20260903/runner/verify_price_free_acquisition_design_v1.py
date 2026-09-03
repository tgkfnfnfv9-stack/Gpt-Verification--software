#!/usr/bin/env python3
"""Offline verifier for the 2022–2025 price-free acquisition design."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "acquisition_design_v1.preaudit.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict[str, object]:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    assert spec["status"] == "PRICE_FREE_PREAUDIT_SUPERSEDED_BY_USER_APPROVED_SIMPLE_IMPLEMENTATION"
    assert spec["baseline_remote_main_sha"] == "b06c815547e8dbd354a54c554af4ab8b516da348"
    assert spec["interval"] == {
        "start_inclusive": "2022-01-01T00:00:00Z",
        "end_exclusive": "2026-01-01T00:00:00Z",
        "timezone": "UTC",
        "years": [2022, 2023, 2024, 2025],
    }

    fx = spec["fx_recovery"]
    assert len(fx["symbols"]) == len(set(fx["symbols"])) == 25
    assert fx["counts"]["new_archives"] == 4 * 25 * 2
    assert fx["counts"]["new_year_manifests"] == 4
    assert fx["counts"]["direct_side_series_years"] == 4 * 25 * 2 * 2
    assert fx["counts"]["derived_combined_side_series_years"] == 4 * 25 * 6
    assert sum(row["present"] for row in fx["year_counts"].values()) == 10084
    assert sum(row["known_missing"] for row in fx["year_counts"].values()) == 316
    assert fx["counts"]["base_weekly_source_identities"] == 10084 + 316

    commodity = spec["commodity"]
    assert len(commodity["mapping"]) == 4
    assert commodity["interval"]["years"] == list(range(2012, 2026))
    assert commodity["counts"]["new_archives_if_fully_available"] == 14 * 4 * 2
    assert commodity["counts"]["new_year_manifests_if_fully_available"] == 14
    assert commodity["counts"]["direct_side_series_years_if_fully_available"] == 14 * 4 * 2 * 2
    assert commodity["counts"]["derived_combined_side_series_years_if_fully_available"] == 14 * 4 * 6
    assert commodity["inventory_only_acquisition_authorized"] is False

    assert len(spec["approval_gates"]) == 5
    assert spec["approval_gates"][0]["state"] == "COMPLETED_WITH_BLOCKERS"
    assert spec["approval_gates"][1]["state"] == "AUTHORIZED_SIMPLE_FX_IMPLEMENTATION"
    assert all(gate["state"] == "NOT_AUTHORIZED" for gate in spec["approval_gates"][2:])
    assert all(spec["current_authorization"][name] is True for name in ("fx_implementation", "fx_commit", "fx_push"))
    assert all(spec["current_authorization"][name] is False for name in (
        "commodity_implementation", "commodity_commit", "commodity_push",
        "workflow_dispatch", "price_access", "oauth_token_exchange", "drive_access",
        "drive_write", "drive_content_download", "transaction_finalization", "cleanup", "research_use",
    ))
    assert spec["commodity_metadata_decision"] == "HOLD_UNTIL_AUTHORITATIVE_CALENDAR_AND_ROLL_DATA"
    assert "planned_gate2_files" not in spec
    anchor = ROOT.parent / "phase9-exploratory-fxcm-20260901" / "spec" / "fxcm_drive_vault_run1_recovery_v2_2.frozen.json"
    assert sha256(anchor) == spec["fx_recovery"]["anchors_sha256"]["recovery_v2_2_spec"]
    assert len(spec["blockers"]) >= 6
    assert len(spec["batch6_denylist"]) == 5

    required_hashes = {
        "source_payload_sha256",
        "canonical_csv_sha256",
        "timestamp_column_sha256",
        "missing_bucket_identities_sha256",
    }
    assert set(spec["qc"]["hashes_required"]) == required_hashes
    required_rejections = {
        "DUPLICATE_TIMESTAMP",
        "DUPLICATE_SHARD",
        "DUPLICATE_ARCHIVE_MEMBER",
        "UNKNOWN_ARCHIVE_MEMBER",
    }
    assert required_rejections.issubset(set(spec["qc"]["reject"]))

    return {
        "status": "PASS",
        "checks": 31,
        "spec_sha256": sha256(SPEC),
        "network_access": 0,
        "price_access": 0,
        "drive_access": 0,
        "drive_mutation": 0,
        "workflow_dispatch": 0,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
