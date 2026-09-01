#!/usr/bin/env python3
"""Verify the preregistered, fail-closed metadata-only JForex amendment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "spec/metadata_only_jforex_schedule_gate.frozen.json"
CONFIRMATION = "RUN_PHASE9_METADATA_ONLY_JFOREX_GATE_NO_SECRET_NO_CONNECTION"
STATUS = "FROZEN_AMENDMENT_EXECUTION_BLOCKED"


class GateError(ValueError):
    pass


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GateError(f"Expected JSON object: {path}")
    return value


def verify_gate(root: Path = ROOT) -> dict:
    contract = load_object(root / CONTRACT.relative_to(ROOT))
    state = load_object(root / "SESSION_STATE.json")
    calendar = load_object(root / "data_manifest/trading_calendar.json")
    provider_contract = load_object(root / "spec/provider_schedule_contract.frozen.json")

    if contract.get("schema_version") != "phase9-metadata-only-jforex-schedule-gate-v1.0":
        raise GateError("Unexpected metadata-only gate schema")
    if contract.get("status") != STATUS:
        raise GateError("Metadata-only gate must remain execution-blocked")
    if contract.get("purpose") != (
        "PREREGISTER_A_FUTURE_METADATA_ONLY_JFOREX_CONNECTION_WITHOUT_PRICE_AVAILABILITY_ORDER_OR_OUTCOME_ACCESS"
    ):
        raise GateError("Metadata-only purpose changed")
    if contract.get("current_preflight_scope") != (
        "NO_SECRET_NO_JNLP_NO_JFOREX_NO_NETWORK_STATIC_CONTRACT_VERIFICATION_ONLY"
    ):
        raise GateError("Current preflight scope changed")
    if contract.get("authorization") != {
        "user_approved_amendment": True,
        "amendment_authorized": True,
        "connection_dispatch_authorized": False,
        "external_jnlp_observation_authorized": False,
        "demo_credentials_may_be_configured": False,
        "provider_schedule_inventory_acquired": False,
        "provider_schedule_allowlist_frozen": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "outcome_access_authorized": False,
    }:
        raise GateError("Metadata-only authorization boundary changed")

    expected_provider = {
        "name": "Dukascopy Bank SA",
        "client": "DDS2-jClient-JForex",
        "client_version": "3.6.51",
        "api": "JForex-API",
        "api_version": "2.13.99",
        "demo_jnlp": "https://platform.dukascopy.com:443/demo_3/jforex_3.jnlp",
    }
    if contract.get("provider") != expected_provider:
        raise GateError("Provider or runtime identity changed")

    observation = contract.get("future_observation_scope", {})
    expected_instruments = [
        "AUDJPY", "AUDUSD", "EURGBP", "EURJPY", "EURUSD", "GBPJPY",
        "GBPUSD", "USDJPY", "XAUUSD", "XAGUSD", "BRENTCMDUSD", "LIGHTCMDUSD",
    ]
    if set(observation) != {
        "timezone",
        "bar_timestamp",
        "start_inclusive",
        "end_exclusive_by_timeframe",
        "instruments",
        "only_permitted_provider_data_call",
        "query_end_argument_rule",
        "observation_is_evidence_only",
        "observation_may_not_claim_complete_interval_inventory",
        "observation_may_not_self_authorize_or_freeze_allowlist",
        "jforex_internal_market_bytes_received",
    }:
        raise GateError("Future observation scope contains unknown or missing fields")
    if observation.get("timezone") != "UTC" or observation.get("bar_timestamp") != "BAR_OPEN":
        raise GateError("Schedule timestamp convention changed")
    if observation.get("start_inclusive") != "2013-01-01T00:00:00Z":
        raise GateError("Schedule start changed")
    if observation.get("end_exclusive_by_timeframe") != {
        "M15": "2019-08-28T00:00:00Z",
        "H1": "2019-08-01T00:00:00Z",
    }:
        raise GateError("Schedule end boundary changed")
    if observation.get("instruments") != expected_instruments or len(set(expected_instruments)) != 12:
        raise GateError("Exact 12-instrument order changed")
    if observation.get("only_permitted_provider_data_call") != (
        "IContext.getDataService().getOfflineTimeDomains(long,long,Instrument)"
    ):
        raise GateError("Exactly one schedule-metadata provider call must be permitted")
    if observation.get("query_end_argument_rule") != "END_EXCLUSIVE_MINUS_ONE_MILLISECOND":
        raise GateError("Historical query boundary is not fail-closed")
    for required_false_claim in (
        "observation_is_evidence_only",
        "observation_may_not_claim_complete_interval_inventory",
        "observation_may_not_self_authorize_or_freeze_allowlist",
    ):
        if observation.get(required_false_claim) is not True:
            raise GateError(f"Missing evidence-only rule: {required_false_claim}")
    if observation.get("jforex_internal_market_bytes_received") != "UNPROVEN":
        raise GateError("Unproven SDK-internal market byte state was overstated")

    prohibitions = contract.get("mechanical_prohibitions", {})
    expected_prohibitions = {
        "available_instrument_or_data_availability_queries",
        "instrument_subscription",
        "tester_data_interval_or_download",
        "history_or_feed_access",
        "tick_or_bar_value_access",
        "order_or_engine_access",
        "account_value_access",
        "return_or_outcome_access",
        "price_or_cache_artifact_upload",
        "raw_price_derived_schedule",
        "development_oos_final_holdout_access",
    }
    if set(prohibitions) != expected_prohibitions or not all(prohibitions.values()):
        raise GateError("Mechanical prohibition set changed")

    expected_before = [
        "SEPARATE_REMOTE_JNLP_OBSERVATION_AMENDMENT_AND_USER_APPROVAL",
        "REMOTE_JNLP_BYTES_AND_RUNTIME_CLOSURE_OBSERVED_WITHOUT_CREDENTIALS_OR_JFOREX_CONNECT",
        "REMOTE_JNLP_AND_RUNTIME_CLOSURE_EXACT_ALLOWLIST_FROZEN_IN_A_STRICTLY_LATER_COMMIT",
        "METADATA_PROBE_SOURCE_AND_REPRODUCIBLE_RUNNER_HASH_FROZEN",
        "DEDICATED_PLUGIN_MODULE_EXCLUDES_THE_EXISTING_ACQUIRER_AND_ALL_PRICE_CALLBACK_SURFACES",
        "OWNED_BYTECODE_METHOD_REFERENCES_MATCH_AN_EXACT_ALLOWLIST",
        "NETWORK_DESTINATION_AND_CHILD_PROCESS_ENVELOPE_FROZEN_FOR_METADATA_MODE",
        "UNSUBSCRIBED_CONNECTION_PROVEN_NOT_TO_PERSIST_OR_EXPOSE_PRICE_VALUES",
        "PRIVATE_EPHEMERAL_CACHE_CUSTODY_AND_CLEANUP_PROVEN",
        "ACCOUNT_TERMS_CONFIRMATION_RECORDED",
        "SEPARATE_EXACT_MANUAL_DISPATCH_CONFIRMATION",
    ]
    expected_after = [
        "AUDIT_RUN_ID_HEAD_SHA_ARTIFACT_ID_AND_ARTIFACT_ZIP_SHA256",
        "PROVE_WHETHER_OFFLINE_DOMAINS_INCLUDE_HOLIDAYS_MAINTENANCE_AND_ENERGY_DAILY_SESSIONS",
        "DO_NOT_CREATE_24_CANONICAL_SCHEDULE_FILES_UNLESS_COMPLETE_HISTORICAL_SEMANTICS_ARE_PROVEN",
        "FREEZE_ANY_CANONICAL_EXACT_MATCH_ALLOWLIST_ONLY_IN_A_STRICTLY_LATER_COMMIT",
    ]
    if contract.get("required_before_connection_dispatch") != expected_before:
        raise GateError("Pre-dispatch blocker set changed")
    if contract.get("required_after_observation") != expected_after:
        raise GateError("Post-observation proof set changed")
    if contract.get("current_commit_artifact_allowlist") != [
        "METADATA_ONLY_JFOREX_GATE_AUDIT.json", "artifact_manifest_sha256.txt"
    ]:
        raise GateError("Artifact allowlist changed")
    if contract.get("scientific_state") != {
        "phase9_price_files": 0,
        "actual_market_data_full_quality_gate_passed": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }:
        raise GateError("Scientific state changed")

    if calendar.get("quality_inventory", {}).get("provider_schedule_version") != "NO_VERSION_AVAILABLE_YET":
        raise GateError("Provider schedule version changed before an audited observation")
    if provider_contract.get("status") != "FROZEN_CONTRACT_NO_PROVIDER_INVENTORY_ACQUIRED":
        raise GateError("Provider schedule contract unexpectedly changed")
    for relative in (
        "data_manifest/provider_schedule_source.frozen.json",
        "data_manifest/provider_schedule_inventory.json",
        "spec/provider_schedule_exact_allowlist.frozen.json",
    ):
        if (root / relative).exists():
            raise GateError(f"Unreviewed schedule authority exists: {relative}")

    provider = state.get("provider_acquisition", {})
    phase9 = state.get("phase9", {})
    readiness = provider.get("provider_schedule_source_readiness", {})
    metadata_gate = provider.get("metadata_only_jforex_schedule_gate", {})
    if readiness.get("metadata_only_connection_amendment_authorized") is not True:
        raise GateError("Session state does not record the approved amendment")
    if metadata_gate != {
        "status": "AMENDMENT_FROZEN_EXECUTION_BLOCKED_PENDING_REMOTE_JNLP_RUNTIME_AND_PRICE_ISOLATION_PROOF",
        "contract": "spec/metadata_only_jforex_schedule_gate.frozen.json",
        "workflow": ".github/workflows/phase9-metadata-only-jforex-gate-preflight.yml",
        "verifier": "runner/verify_phase9_metadata_only_jforex_gate.py",
        "user_approved_amendment": True,
        "connection_dispatch_authorized": False,
        "external_jnlp_observation_authorized": False,
        "demo_credentials_may_be_configured": False,
        "provider_schedule_inventory_acquired": False,
        "provider_schedule_allowlist_frozen": False,
        "credentials_referenced": False,
        "external_jnlp_request_attempted": False,
        "jforex_connect_invoked": False,
        "market_price_request_attempted": False,
        "availability_request_attempted": False,
        "schedule_metadata_request_attempted": False,
        "forbidden_market_period_request_attempted": False,
        "phase9_price_files_acquired": 0,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "acquisition_authorized": False,
        "count_only_authorized": False,
    }:
        raise GateError("Session metadata-only gate state changed")
    if (
        phase9.get("status_for_all_active_questions") != "UNTESTED_PREREGISTERED"
        or phase9.get("data_download_started") is not False
        or phase9.get("authorized_data_download_started") is not False
        or phase9.get("outcome_accessed") is not False
        or provider.get("phase9_price_files_acquired") != 0
        or provider.get("phase9_outcomes_accessed") is not False
        or provider.get("provider_schedule_inventory_acquired") is not False
        or provider.get("provider_schedule_allowlist_frozen") is not False
    ):
        raise GateError("Phase 9 state advanced beyond the approved amendment")

    return {
        "schema_version": "phase9-metadata-only-jforex-gate-audit-v1.0",
        "status": STATUS,
        "run_id": int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,
        "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]) if os.environ.get("GITHUB_RUN_ATTEMPT") else None,
        "head_sha": os.environ.get("GITHUB_SHA"),
        "contract_sha256": hashlib.sha256((root / CONTRACT.relative_to(ROOT)).read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "amendment_authorized": True,
        "connection_dispatch_authorized": False,
        "credentials_referenced": False,
        "external_jnlp_request_attempted": False,
        "jforex_connect_invoked": False,
        "availability_request_attempted": False,
        "schedule_metadata_request_attempted": False,
        "market_price_request_attempted": False,
        "forbidden_market_period_request_attempted": False,
        "provider_schedule_inventory_acquired": False,
        "provider_schedule_allowlist_frozen": False,
        "same_run_self_authorization_used": False,
        "phase9_price_files_acquired": 0,
        "actual_market_data_full_quality_gate_passed": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
        "remaining_blockers": list(contract["required_before_connection_dispatch"])
        + list(contract["required_after_observation"]),
    }


def write_new_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.confirmation != CONFIRMATION:
        raise GateError("Exact no-secret/no-connection confirmation required")
    audit = verify_gate()
    write_new_json(args.report, audit)
    print(json.dumps({"status": audit["status"], "connection_dispatch_authorized": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
