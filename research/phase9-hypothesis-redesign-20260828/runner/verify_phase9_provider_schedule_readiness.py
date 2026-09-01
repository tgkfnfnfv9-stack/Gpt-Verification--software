#!/usr/bin/env python3
"""Fail-closed readiness check for the independent Phase 9 schedule source."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION = "RUN_PHASE9_PROVIDER_SCHEDULE_READINESS_NO_SECRET_NO_PRICE"
CANONICAL_SOURCE = ROOT / "data_manifest/provider_schedule_source.frozen.json"
CANONICAL_INVENTORY = ROOT / "data_manifest/provider_schedule_inventory.json"
CANONICAL_ALLOWLIST = ROOT / "spec/provider_schedule_exact_allowlist.frozen.json"
BLOCKED_STATUS = "BLOCKED_AUTHORITATIVE_INDEPENDENT_PROVIDER_SCHEDULE_SOURCE_NOT_FROZEN"


class ReadinessError(ValueError):
    pass


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReadinessError(f"Expected JSON object: {path}")
    return value


def blocked_audit(root: Path = ROOT) -> dict:
    calendar = load_json(root / "data_manifest/trading_calendar.json")
    contract = load_json(root / "spec/provider_schedule_contract.frozen.json")
    metadata_gate = load_json(root / "spec/metadata_only_jforex_schedule_gate.frozen.json")
    state = load_json(root / "SESSION_STATE.json")
    source = root / CANONICAL_SOURCE.relative_to(ROOT)
    inventory = root / CANONICAL_INVENTORY.relative_to(ROOT)
    allowlist = root / CANONICAL_ALLOWLIST.relative_to(ROOT)

    if calendar.get("quality_inventory", {}).get("provider_schedule_version") != "NO_VERSION_AVAILABLE_YET":
        raise ReadinessError("Blocked-state preflight no longer matches the calendar source state")
    if contract.get("status") != "FROZEN_CONTRACT_NO_PROVIDER_INVENTORY_ACQUIRED":
        raise ReadinessError("Provider schedule contract status unexpectedly changed")
    if (
        metadata_gate.get("status") != "FROZEN_AMENDMENT_EXECUTION_BLOCKED"
        or metadata_gate.get("authorization", {}).get("amendment_authorized") is not True
        or metadata_gate.get("authorization", {}).get("connection_dispatch_authorized") is not False
    ):
        raise ReadinessError("Metadata-only amendment is not frozen and execution-blocked")
    authorization = contract.get("authorization_state", {})
    if authorization != {
        "provider_schedule_inventory_acquired": False,
        "actual_market_data_full_quality_gate_passed": False,
        "count_only_authorized": False,
        "outcome_access_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }:
        raise ReadinessError("Provider schedule contract authorization state changed")
    if source.exists() or inventory.exists() or allowlist.exists():
        raise ReadinessError("Blocked-state preflight cannot accept source, inventory, or allowlist bytes")

    phase9 = state.get("phase9", {})
    provider = state.get("provider_acquisition", {})
    readiness = provider.get("provider_schedule_source_readiness", {})
    if (
        phase9.get("status_for_all_active_questions") != "UNTESTED_PREREGISTERED"
        or provider.get("phase9_price_files_acquired") != 0
        or provider.get("phase9_outcomes_accessed") is not False
        or provider.get("provider_schedule_inventory_acquired") is not False
        or provider.get("provider_schedule_allowlist_frozen") is not False
    ):
        raise ReadinessError("Phase 9 research state changed before schedule readiness")
    if readiness != {
        "status": "P0_BLOCKED_AUTHORITATIVE_INDEPENDENT_SOURCE_NOT_FROZEN",
        "workflow": ".github/workflows/phase9-provider-schedule-readiness-preflight.yml",
        "runner": "runner/verify_phase9_provider_schedule_readiness.py",
        "authoritative_versioned_source_frozen": False,
        "generic_weekday_or_current_session_template_accepted": False,
        "official_historical_offline_domain_api_requires_jforex_context": True,
        "metadata_only_connection_amendment_authorized": True,
        "provider_schedule_inventory_acquired": False,
        "provider_schedule_allowlist_frozen": False,
        "phase9_price_files_acquired": 0,
        "forbidden_market_period_request_attempted": False,
        "research_outcomes_calculated": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
    }:
        raise ReadinessError("Provider schedule readiness state is not the exact blocked state")

    return {
        "schema_version": "phase9-provider-schedule-readiness-v1.0",
        "status": BLOCKED_STATUS,
        "run_id": int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,
        "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]) if os.environ.get("GITHUB_RUN_ATTEMPT") else None,
        "head_sha": os.environ.get("GITHUB_SHA"),
        "canonical_source_path": CANONICAL_SOURCE.relative_to(ROOT).as_posix(),
        "canonical_source_present": False,
        "provider_schedule_version": "NO_VERSION_AVAILABLE_YET",
        "metadata_only_connection_amendment_authorized": True,
        "metadata_only_connection_dispatch_authorized": False,
        "provider_schedule_inventory_acquired": False,
        "provider_schedule_allowlist_frozen": False,
        "same_run_self_authorization_used": False,
        "credentials_referenced": False,
        "external_jnlp_request_attempted": False,
        "jforex_connect_invoked": False,
        "availability_request_attempted": False,
        "market_price_request_attempted": False,
        "forbidden_market_period_request_attempted": False,
        "phase9_price_files_acquired": 0,
        "actual_market_data_full_quality_gate_passed": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "blockers": [
            "AUTHORITATIVE_VERSIONED_PROVIDER_SCHEDULE_SOURCE_ABSENT",
            "ONLY_DOCUMENTED_HISTORICAL_OFFLINE_DOMAIN_API_REQUIRES_PROHIBITED_JFOREX_CONTEXT",
            "ENERGY_HISTORICAL_SESSION_AND_HOLIDAY_COMPLETENESS_UNPROVEN",
            "METADATA_ONLY_CONNECTION_DISPATCH_BLOCKED_PENDING_REMOTE_RUNTIME_AND_PRICE_ISOLATION_PROOF",
        ],
    }


def write_new_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise ReadinessError("Exact no-secret/no-price readiness confirmation required")
    audit = blocked_audit()
    write_new_json(args.report, audit)
    print(json.dumps({"status": audit["status"], "acquisition_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
