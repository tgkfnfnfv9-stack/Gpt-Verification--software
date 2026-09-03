#!/usr/bin/env python3
"""Offline verifier for the Batch 6 Fast Track design-only contract.

The module intentionally exposes no network, OAuth, Drive, FXCM, workflow
dispatch, market-data parsing, signal-count, or return-calculation surface.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA = "phase9-exploratory-fxcm-blind-mtf-batch6-fast-track-design-v1.0.0"
EXPECTED_STATUS = "FROZEN_DESIGN_AND_PRICE_FREE_PREAUDIT_BLOCKED_P0_NO_IMPLEMENTATION_NO_EXECUTION"
EXPECTED_HEAD = "1c013f04a6217ff2db900519bd7963e5d745cc25"
EXPECTED_CANDIDATES = [f"EXP-P9-MTF-{number}" for number in range(321, 325)]
EXPECTED_SYMBOLS = [
    "AUDJPY",
    "AUDUSD",
    "EURGBP",
    "EURJPY",
    "EURUSD",
    "GBPJPY",
    "GBPUSD",
    "USDJPY",
]
EXPECTED_YEARS = [2017, 2018]
EXPECTED_PERIODICITIES = ["m1", "H1"]
EXPECTED_FINAL_TIMEFRAMES = ["M15", "H1", "H4", "D1"]
EXPECTED_AUTHORIZATION_KEYS = {
    "implementation",
    "workflow_creation",
    "workflow_dispatch",
    "oauth_token_exchange",
    "drive_metadata_get",
    "drive_manifest_content_read",
    "drive_archive_content_read",
    "drive_mutation",
    "drive_cleanup",
    "fxcm_price_acquisition",
    "count_execution",
    "return_oos_execution",
    "commit",
    "push",
}
EXPECTED_PERFORMED_KEYS = {
    "network_price_request",
    "oauth_token_exchange",
    "drive_metadata_get",
    "drive_file_content_get",
    "drive_mutation",
    "workflow_dispatch",
    "count_only_analysis",
    "return_or_outcome_analysis",
    "commit",
    "push",
}
SCIENTIFIC_SPECIFICATION_CLOSURE_STAGE = "SCIENTIFIC_SPECIFICATION_BEFORE_IMPLEMENTATION"
CONTROL_IMPLEMENTATION_CLOSURE_STAGE = "CONTROL_IMPLEMENTATION_AND_STATIC_AUDIT_AFTER_SEPARATE_APPROVAL"
EXPECTED_SCIENTIFIC_SPECIFICATION_P0 = [
    "P0-CANDIDATE-323-FUTURE-AVAILABILITY",
    "P0-EPISODE-SEMANTICS",
    "P0-CANDIDATE-323-FREQUENCY-FEASIBILITY",
    "P0-MECHANISM-INDEPENDENCE",
    "P0-LEGACY-MTF-QC",
    "P0-CANDIDATE-324-COVERAGE-SEMANTICS",
]
EXPECTED_CONTROL_IMPLEMENTATION_P0 = [
    "P0-COUNT-RUNTIME-ISOLATION",
    "P0-CLEANUP-AND-ATTESTATION",
    "P0-INCOMPLETE-TRANSACTION-INPUT",
    "P0-VAULT-V2-DERIVED-COMPLETENESS",
]


class VerificationError(ValueError):
    """Raised when the frozen design boundary is violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "contract must be a JSON object")
    return value


def expected_archive_names(scope: dict[str, Any]) -> list[str]:
    template = scope["archive_name_template"]
    return [
        template.format(symbol=symbol, year=year, periodicity=periodicity)
        for year in EXPECTED_YEARS
        for symbol in EXPECTED_SYMBOLS
        for periodicity in EXPECTED_PERIODICITIES
    ]


def verify(contract_path: Path, repository_root: Path) -> dict[str, Any]:
    contract = load_json(contract_path)
    require(contract.get("schema_version") == EXPECTED_SCHEMA, "unexpected schema")
    require(contract.get("status") == EXPECTED_STATUS, "design is not frozen and execution-disabled")

    repository = contract["repository_anchor"]
    require(repository["repository"] == "tgkfnfnfv9-stack/Gpt-Verification--software", "repository changed")
    require(repository["branch"] == "main", "branch changed")
    require(repository["reviewed_head_sha"] == EXPECTED_HEAD, "reviewed main SHA changed")
    require(repository["existing_uncommitted_recovery_work_must_remain_untouched"] is True, "dirty worktree protection missing")

    scope = contract["immutable_batch6_scope"]
    require(scope["candidate_ids"] == EXPECTED_CANDIDATES, "candidate set or order changed")
    require(scope["symbols"] == EXPECTED_SYMBOLS, "FX8 scope changed")
    require(scope["years"] == EXPECTED_YEARS, "year scope changed")
    require(scope["direct_periodicities"] == EXPECTED_PERIODICITIES, "direct periodicities changed")
    require(scope["available_sides"] == ["BID", "ASK"], "BID/ASK scope changed")
    require(scope["final_timeframes"] == EXPECTED_FINAL_TIMEFRAMES, "final timeframe set changed")
    require(scope["start_inclusive"] == "2017-01-01T00:00:00Z", "start boundary changed")
    require(scope["end_exclusive"] == "2018-12-31T00:00:00Z", "end boundary changed")
    archives = expected_archive_names(scope)
    require(len(archives) == len(set(archives)) == 32, "Route A archive set is not exact and unique")
    require(scope["expected_archive_count_route_a"] == 32, "Route A archive count changed")
    require(scope["expected_source_object_count_route_b"] == 8 * 2 * 2 * 52, "Route B request count changed")
    require(scope["expected_final_side_series_count"] == 8 * 2 * 4, "final series count changed")
    for field in (
        "candidate_rule_change_allowed",
        "threshold_change_allowed",
        "direction_flip_allowed",
        "symbol_or_timeframe_selection_allowed",
        "prior_candidate_rescue_allowed",
    ):
        require(scope[field] is False, f"research rescue enabled: {field}")
    require(scope["candidate_rule_change_in_this_version"] is False, "candidate rule changed in design-only version")
    require(
        scope["future_candidate_rule_change_requires_prospective_amended_preregistration"] is True,
        "future candidate-rule changes may bypass prospective amendment",
    )

    anchors = contract["frozen_research_anchors"]
    require(anchors["candidate_contract"]["git_blob_sha"] == "2b0070ec70a91e2b2480658bc315e725e5f7b4cc", "candidate blob changed")
    require(anchors["candidate_contract"]["sha256"] == "da49f0f061a5ed6edc90effa232114742900ef316b19a953fd74143113566460", "candidate SHA changed")
    require(anchors["legacy_count_runner_reference"]["git_blob_sha"] == "90e76fc115351424fc390295f2bab8d21c2fc0ed", "count runner blob changed")
    require(anchors["legacy_count_runner_reference"]["sha256"] == "082071317dd9a6d555beda75a44abfcdeaea2c73b0f202fa8ad7b7d20de39685", "count runner SHA changed")
    require(anchors["legacy_count_runner_reference"]["required_state"] == "REFERENCE_ONLY_UNSAFE_FOR_FAST_TRACK_EXECUTION", "legacy runner may execute")
    require(anchors["legacy_batch6_workflow"]["required_state"] == "PERMANENTLY_FAIL_CLOSED_FALSE_AND_LEAVE_UNCHANGED", "legacy workflow may run")

    preaudit = contract["price_free_preaudit_decision"]
    require(preaudit["verdict"] == "BLOCK_FAST_TRACK_EXECUTION_PENDING_P0_RESOLUTION", "preaudit is not fail-closed")
    require(preaudit["old_workflow_or_runner_reuse_allowed"] is False, "legacy execution allowed")
    expected_p0 = set(EXPECTED_SCIENTIFIC_SPECIFICATION_P0 + EXPECTED_CONTROL_IMPLEMENTATION_P0)
    findings_by_id = {row["id"]: row for row in preaudit["p0_findings"]}
    require(set(findings_by_id) == expected_p0, "P0 finding set changed")
    require(len(findings_by_id) == len(preaudit["p0_findings"]), "duplicate P0 finding id")
    for finding_id in EXPECTED_SCIENTIFIC_SPECIFICATION_P0:
        require(
            findings_by_id[finding_id].get("closure_stage") == SCIENTIFIC_SPECIFICATION_CLOSURE_STAGE,
            f"scientific-specification P0 closure stage changed: {finding_id}",
        )
    for finding_id in EXPECTED_CONTROL_IMPLEMENTATION_P0:
        require(
            findings_by_id[finding_id].get("closure_stage") == CONTROL_IMPLEMENTATION_CLOSURE_STAGE,
            f"control-implementation P0 closure stage changed: {finding_id}",
        )
    frequency_finding = findings_by_id["P0-CANDIDATE-323-FREQUENCY-FEASIBILITY"]
    require("coarse opportunity upper bound" in frequency_finding["finding"], "candidate 323 coarse opportunity bound missing")
    require("not a realizable Count bound" in frequency_finding["finding"], "candidate 323 feasibility overstated")

    closure = preaudit["p0_closure_model"]
    require(
        closure["scientific_specification_p0_ids"] == EXPECTED_SCIENTIFIC_SPECIFICATION_P0,
        "scientific-specification P0 order or set changed",
    )
    require(
        closure["control_implementation_p0_ids"] == EXPECTED_CONTROL_IMPLEMENTATION_P0,
        "control-implementation P0 order or set changed",
    )
    require(
        closure["scientific_specification_closure_requirement"]
        == "CLOSE_BY_PROSPECTIVE_PRICE_FREE_SPECIFICATION_AND_REAUDIT_BEFORE_ANY_IMPLEMENTATION",
        "scientific-specification P0 may remain open at implementation",
    )
    require(
        closure["control_implementation_closure_requirement"]
        == "CLOSE_DURING_SEPARATELY_APPROVED_IMPLEMENTATION_AND_PRICE_FREE_STATIC_AUDIT_BEFORE_EXTERNAL_ACCESS_OR_COUNT",
        "control-implementation P0 closure boundary changed",
    )
    require(closure["implementation_authorized_by_this_design_version"] is False, "design version authorized implementation")
    require(closure["runtime_data_identity_and_qc_gates_remain_required_after_control_closure"] is True, "runtime input gates removed")
    p1_constraints = set(preaudit["p1_constraints"])
    require(
        "Define whether observation-consecutive H1 bars may cross real-time gaps for candidates 321 and 322."
        in p1_constraints,
        "candidate 321/322 real-time gap semantics missing",
    )
    require(
        "Keep all results exploratory because repeated 2017-2018 hypothesis generation is not program-level untouched OOS."
        in p1_constraints,
        "repeated 2017-2018 exploratory classification missing",
    )

    route = contract["source_route_decision"]
    require(route["preferred_route"] == "ROUTE_A_EXISTING_DRIVE_2017_2018_CONDITIONAL", "unexpected preferred route")
    require(route["automatic_fallback_from_a_to_b"] is False, "automatic provider fallback enabled")
    require(route["automatic_route_selection_at_runtime"] is False, "runtime route selection enabled")
    require(route["incomplete_transaction_may_be_called_canonical_or_committed"] is False, "incomplete transaction relabeled")
    require(route["may_proceed_before_all_p0_findings_are_resolved"] is False, "P0 bypass enabled")

    route_a = contract["route_a_existing_drive_design"]
    source = route_a["source_acquisition_run"]
    require(source["run_id"] == 33705800232 and source["run_attempt"] == 1, "source acquisition identity changed")
    require(source["transaction_state"] == "ACQUIRING", "transaction state is not incomplete")
    require(source["canonical_v2_folder_count"] == 0, "canonical v2 unexpectedly claimed")
    a1 = route_a["gate_a1_manifest_selection"]
    require(a1["current_state"] == "DESIGN_ONLY_NOT_IMPLEMENTED_NOT_AUTHORIZED", "A1 implementation or authorization leaked")
    require(a1["future_separate_user_approval_required"] is True, "A1 approval boundary missing")
    require(a1["year_manifest_content_get_max"] == 2, "A1 manifest scope expanded")
    require(a1["archive_content_get"] == 0 and a1["price_bytes_allowed"] is False, "A1 may read prices")
    require(a1["drive_mutation_allowed"] is False and a1["cleanup_allowed"] is False, "A1 may mutate Drive")
    a2 = route_a["gate_a2_archive_qc_and_count"]
    require(a2["current_state"] == "DESIGN_ONLY_NOT_IMPLEMENTED_NOT_AUTHORIZED", "A2 implementation or authorization leaked")
    require(a2["future_separate_user_approval_required"] is True, "A2 approval boundary missing")
    require(a2["archive_content_get_exact"] == 32, "A2 archive scope changed")
    require(a2["regular_members_per_archive_exact"] == 54, "archive member count changed")
    require(
        a2["member_layout_per_archive"] == {"payload_manifest": 1, "canonical_csv": 1, "source_gzip": 52},
        "archive member layout changed",
    )
    require(a2["source_member_identity_count_exact"] == 1664, "source member identity scope changed")
    extraction = a2["archive_extraction_policy"]
    for rejected in ("ABSOLUTE", "PARENT_TRAVERSAL", "SYMLINK", "HARDLINK", "DUPLICATE", "UNKNOWN"):
        require(rejected in extraction, f"safe extraction rule missing: {rejected}")
    require(a2["drive_mutation_allowed"] is False and a2["cleanup_of_remote_transaction_allowed"] is False, "A2 may mutate Drive")
    require(a2["automatic_return_oos_continuation_allowed"] is False, "A2 may continue to outcomes")
    require(a2["workflow_dispatch_authorized_at_preaudit_time"] is False, "A2 dispatch was authorized at preaudit time")
    require(a2["count_execution_authorized_at_preaudit_time"] is False, "A2 Count was authorized at preaudit time")

    route_b = contract["route_b_fxcm_reacquisition_design_boundary"]
    require(route_b["current_state"] == "NOT_SELECTED_NOT_IMPLEMENTED_NOT_AUTHORIZED", "Route B activated")
    require(route_b["future_new_versioned_design_required"] is True, "Route B can bypass design")
    require(route_b["exact_source_request_count"] == 1664, "Route B request scope changed")
    require(route_b["runtime_fallback_from_route_a_allowed"] is False, "Route B automatic fallback enabled")
    require(route_b["reuse_of_route_a_approval_allowed"] is False, "approval inheritance enabled")

    qc = contract["mtf_reconstruction_and_qc"]
    require(qc["H1"] == "USE_DIRECT_H1_ONLY_M1_DERIVED_H1_IS_QC_REFERENCE_ONLY", "H1 source substituted")
    require(qc["H4"].startswith("DERIVE_FROM_DIRECT_H1"), "H4 source changed")
    require(qc["D1"].startswith("DERIVE_FROM_DIRECT_H1"), "D1 source changed")
    require(qc["bid_and_ask_aggregated_separately"] is True, "BID/ASK aggregation merged")
    require(qc["forward_fill_allowed"] is False and qc["interpolation_allowed"] is False, "fill or interpolation enabled")
    require(qc["structural_qc_failure_action"] == "STOP_BEFORE_COUNT", "QC failure may reach Count")
    require(qc["direct_h1_canonical_for_count"] is True, "direct H1 is not canonical")
    require(qc["m1_derived_h1_vs_direct_h1_exact_comparison_required"] is True, "H1 exact comparison disabled")
    require(qc["m1_derived_h1_vs_direct_h1_exact_equality_required_for_count"] is False, "diagnostic equality became a Count gate")
    require(qc["m1_derived_h1_vs_direct_h1_role"].startswith("DIAGNOSTIC_ONLY_AFTER_A_PROSPECTIVE_PRE_COUNT_AMENDMENT"), "H1 reconciliation silently relaxed")
    require(qc["legacy_structural_qc_pass_may_be_claimed"] is False, "legacy QC failure relabeled")
    require(qc["final_64_series_identity_must_match_legacy_canonical_projection"] is True, "legacy identity gate removed")
    require(qc["count_price_basis_numeric_semantics"].startswith("LEGACY_IEEE754_BINARY64"), "numeric semantics changed")
    require(qc["decimal_scope"] == "SOURCE_PARSE_SOURCE_HASH_STRUCTURAL_QC_AND_TIMEFRAME_AGGREGATION_ONLY", "Decimal scope changed")
    require(qc["count_midpoint_scope"].startswith("LEGACY_IEEE754_BINARY64"), "Count midpoint scope changed")
    require(qc["h4_d1_completeness_rule"].startswith("INDEPENDENTLY_GENERATE_EXPECTED_H1_TIMESTAMP_SET"), "derived completeness remains unsafe")

    count = contract["count_only_boundary"]
    require(count["count_first"] is True, "Count-first disabled")
    forbidden = set(count["forbidden_calculations"])
    required_forbidden = {
        "FORWARD_RETURN",
        "MFE",
        "MAE",
        "WIN_LOSS",
        "PROFIT_FACTOR",
        "EDGE",
        "P_VALUE",
        "CONFIDENCE_INTERVAL",
        "OUTCOME_CHART",
    }
    require(required_forbidden <= forbidden, "outcome denylist incomplete")
    require(count["prior_outcome_tested_candidate_count"] == 7, "prior multiplicity count changed")
    require(count["return_gate_only_for_frequency_passers"] is True, "failed candidates may reach Return")
    require(count["return_oos_requires_new_preregistration_and_separate_approval"] is True, "Return approval boundary missing")

    artifact = contract["future_artifact_policy"]
    require(len(artifact["gate_a1_exact_files"]) == 2, "A1 artifact allowlist changed")
    require(len(artifact["gate_a2_exact_files"]) == 2, "A2 artifact allowlist changed")
    for field in (
        "raw_or_derived_price_allowed",
        "event_timestamp_allowed",
        "full_timestamp_sequence_allowed",
        "drive_file_or_folder_id_allowed",
        "secret_or_oauth_value_allowed",
        "return_or_outcome_field_allowed",
        "unbounded_remote_name_allowed",
    ):
        require(artifact[field] is False, f"artifact leak enabled: {field}")

    authorization = contract["authorization_at_preaudit_time"]
    require(set(authorization) == EXPECTED_AUTHORIZATION_KEYS, "preaudit authorization key set changed")
    require(all(value is False for value in authorization.values()), "an operation was authorized at preaudit time")
    performed = contract["operations_performed_by_this_design_preaudit"]
    require(set(performed) == EXPECTED_PERFORMED_KEYS, "preaudit performed-operation key set changed")
    require(all(value == 0 for value in performed.values()), "preaudit performed an external or research operation")

    implementation = contract["implementation_boundary"]
    require(implementation["all_three_must_be_absent_at_this_design_gate"] is True, "design gate permits implementation")
    require(implementation["legacy_batch6_workflow_may_be_modified_or_reenabled"] is False, "legacy workflow modification allowed")
    require(implementation["shared_recovery_runner_may_be_modified"] is False, "shared recovery runner modification allowed")
    for field in ("new_standalone_count_runner_path", "new_workflow_path", "new_execution_contract_path"):
        require(not (repository_root / implementation[field]).exists(), f"forbidden implementation path exists: {implementation[field]}")

    stop_condition = contract["stop_condition"]
    require("DO_NOT_IMPLEMENT_UNTIL_ALL_SCIENTIFIC_SPECIFICATION_P0_ARE_CLOSED" in stop_condition, "scientific P0 implementation stop missing")
    require("CONTROL_IMPLEMENTATION_IS_SEPARATELY_APPROVED" in stop_condition, "separate implementation approval missing")
    require("DO_NOT_USE_EXTERNAL_DATA_OR_RUN_COUNT_UNTIL_CONTROL_IMPLEMENTATION_P0_PASS_PRICE_FREE_STATIC_AUDIT" in stop_condition, "control P0 execution stop missing")

    return {
        "schema_version": "phase9-exploratory-fxcm-blind-mtf-batch6-fast-track-design-verification-v1.0.0",
        "status": "PASS_DESIGN_AND_PRICE_FREE_PREAUDIT_ONLY",
        "candidate_count": 4,
        "route_a_archive_count": 32,
        "route_b_source_request_count": 1664,
        "final_side_series_count": 64,
        "implementation_paths_present": 0,
        "network_price_requests_performed": 0,
        "drive_file_content_gets_performed": 0,
        "drive_mutations_performed": 0,
        "workflow_dispatches_performed": 0,
        "count_analyses_performed": 0,
        "return_or_outcome_analyses_performed": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.contract.resolve(), args.repository_root.resolve())
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
