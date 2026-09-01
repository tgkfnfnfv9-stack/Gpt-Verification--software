#!/usr/bin/env python3
"""Verify the local/synthetic metadata-only M1 gate without provider access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "spec/metadata_only_local_m1_gate.frozen.json"
METHOD_ALLOWLIST = ROOT / "spec/metadata_owned_method_allowlist.frozen.json"
REMOTE_PROPOSAL = ROOT / "spec/remote_jnlp_observation_amendment.frozen.json"
REMOTE_PROPOSAL_MARKDOWN = ROOT / "JFOREX_REMOTE_JNLP_OBSERVATION_AMENDMENT.md"
MODULE = ROOT / "runner/jforex-metadata"
SYNTHETIC_API = ROOT / "tests/fixtures/metadata-jforex-api"
EXPECTED_PROVIDER_METHODS = [
    "com/dukascopy/api/IDataService.getOfflineTimeDomains:(JJLcom/dukascopy/api/Instrument;)Ljava/util/Set;",
    "com/dukascopy/api/ITimeDomain.getEnd:()J",
    "com/dukascopy/api/ITimeDomain.getStart:()J",
    "com/dukascopy/api/Instrument.fromString:(Ljava/lang/String;)Lcom/dukascopy/api/Instrument;",
    "com/dukascopy/api/JFException.<init>:(Ljava/lang/String;Ljava/lang/Throwable;)V",
    "com/dukascopy/api/IContext.getDataService:()Lcom/dukascopy/api/IDataService;",
    "com/dukascopy/api/plugins/IPluginContext.stop:()V",
    "com/dukascopy/api/plugins/Plugin.<init>:()V",
    "com/dukascopy/api/system/IClient.connect:(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V",
    "com/dukascopy/api/system/IClient.isConnected:()Z",
    "com/dukascopy/api/system/IClient.runPlugin:(Lcom/dukascopy/api/plugins/Plugin;Lcom/dukascopy/api/IStrategyExceptionHandler;)Ljava/util/UUID;",
    "com/dukascopy/api/system/IClient.setCacheDirectory:(Ljava/io/File;)V",
]


class GateError(RuntimeError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise GateError(f"Expected object: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_sources() -> list[Path]:
    source_root = MODULE / "src/main/java"
    return sorted(path for path in source_root.rglob("*.java") if path.is_file())


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def validate_static_contract() -> dict[str, Any]:
    contract = load_object(CONTRACT)
    allowlist = load_object(METHOD_ALLOWLIST)
    if contract.get("schema_version") != "phase9-metadata-local-m1-gate-v1.0":
        raise GateError("Unexpected local M1 contract schema")
    if contract.get("status") != "LOCAL_SYNTHETIC_CONTROLS_FROZEN_REMOTE_EXECUTION_BLOCKED":
        raise GateError("Unexpected local M1 status")
    expected_authorization = {
        "local_synthetic_preflight_authorized": True,
        "external_jnlp_observation_authorized": False,
        "connection_dispatch_authorized": False,
        "demo_credentials_may_be_configured": False,
        "provider_schedule_inventory_acquired": False,
        "provider_schedule_allowlist_frozen": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "outcome_access_authorized": False,
    }
    if contract.get("authorization") != expected_authorization:
        raise GateError("Local M1 authorization changed")
    if allowlist.get("schema_version") != "phase9-metadata-owned-method-allowlist-v1.0":
        raise GateError("Unexpected method allowlist schema")
    if allowlist.get("status") != (
        "EXACT_SYNTHETIC_ABI_OWNED_BYTECODE_PROVIDER_METHOD_ALLOWLIST_FROZEN_"
        "REAL_JFOREX_UNVERIFIED"
    ):
        raise GateError("Unexpected method allowlist status")
    if set(contract) != {
        "schema_version", "status", "recorded_at_utc", "authorization", "module",
        "owned_source_prohibitions", "synthetic_network_envelope",
        "private_writable_path_custody", "remote_jnlp_observation_amendment",
        "scientific_state",
    }:
        raise GateError("Local M1 contract fields changed")
    if contract.get("module") != {
        "path": "runner/jforex-metadata",
        "artifact_id": "phase9-jforex-metadata-probe",
        "physically_excludes": "runner/jforex/src/main/java/org/phase9/Phase9JForexAcquirer.java",
        "owned_class_exact_set": [
            "org/phase9/metadata/Phase9MetadataClient.class",
            "org/phase9/metadata/Phase9OfflineDomainPlugin.class",
        ],
        "authorized_executable_dispatch_present": False,
        "only_future_provider_data_method": "IContext.getDataService().getOfflineTimeDomains(long,long,Instrument)",
        "compiled_against_frozen_synthetic_api_fixture": True,
        "real_jforex_api_2_13_99_compatibility_verified": False,
        "real_jforex_runtime_methodrefs_verified": False,
        "java_path_toctou_resistant_connection_custody_verified": False,
        "raw_observation_output": "OFFLINE_DOMAINS_RAW.tsv",
        "canonical_timestamp_files_created": False,
    }:
        raise GateError("Dedicated module contract changed")
    if contract.get("synthetic_network_envelope") != {
        "network_namespace": "SEPARATE_CLIENT_AND_SERVER_NAMESPACES_EXACT_VETH_HOST_ROUTE_NO_DEFAULT_ROUTE",
        "allowed_destination_ipv4": "198.18.0.1",
        "allowed_destination_tcp_port": 38443,
        "dns_permitted": False,
        "udp_permitted": False,
        "nonthread_child_process_permitted": False,
        "default_deny_other_destinations": True,
        "real_provider_destination_allowlist": [],
        "real_provider_egress_authorized": False,
    }:
        raise GateError("Synthetic network contract changed")
    if contract.get("scientific_state") != {
        "phase9_price_files": 0,
        "provider_schedule_files": 0,
        "actual_market_data_full_quality_gate_passed": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }:
        raise GateError("Scientific state changed")
    if allowlist.get("dukascopy_method_references") != EXPECTED_PROVIDER_METHODS:
        raise GateError("Provider method allowlist changed")
    if allowlist.get("scope") != (
        "SYNTHETIC_FIXTURE_COMPILED_DUKASCOPY_METHODREF_AND_INTERFACEMETHODREF_"
        "CONSTANT_POOL_ENTRIES_IN_EXACT_OWNED_CLASS_SET"
    ):
        raise GateError("Method allowlist scope changed")
    for field in (
        "compiled_against_real_jforex_api_2_13_99_jar",
        "real_jforex_api_2_13_99_compatibility_verified",
        "real_runtime_methodrefs_verified",
    ):
        if allowlist.get(field) is not False:
            raise GateError(f"Unverified real JForex claim changed: {field}")
    if allowlist.get("exact_match_required") is not True or allowlist.get("authorization_effect") != "NONE":
        raise GateError("Method allowlist authorization changed")

    sources = module_sources()
    observed_sources = [relative(path) for path in sources]
    if observed_sources != allowlist.get("owned_source_paths"):
        raise GateError("Owned metadata source set changed")
    observed_hashes = {relative(path): sha256(path) for path in sources}
    if observed_hashes != allowlist.get("owned_source_sha256"):
        raise GateError("Owned metadata source bytes changed")
    pom = MODULE / "pom.xml"
    if (
        allowlist.get("module_pom_path") != relative(pom)
        or allowlist.get("module_pom_sha256") != sha256(pom)
    ):
        raise GateError("Metadata module POM changed")
    fixture_files = sorted(path for path in SYNTHETIC_API.rglob("*.java") if path.is_file())
    fixture_hashes = {relative(path): sha256(path) for path in fixture_files}
    if fixture_hashes != allowlist.get("synthetic_api_fixture_sha256"):
        raise GateError("Synthetic JForex API fixture set or bytes changed")
    remote_contract = contract.get("remote_jnlp_observation_amendment")
    if remote_contract != {
        "path": "JFOREX_REMOTE_JNLP_OBSERVATION_AMENDMENT.md",
        "markdown_sha256": sha256(REMOTE_PROPOSAL_MARKDOWN),
        "frozen_json_path": "spec/remote_jnlp_observation_amendment.frozen.json",
        "frozen_json_sha256": sha256(REMOTE_PROPOSAL),
        "status": "FROZEN_PROPOSAL_USER_APPROVAL_REQUIRED",
        "authorization_effect": "NONE",
    }:
        raise GateError("Remote JNLP proposal identity changed")
    remote = load_object(REMOTE_PROPOSAL)
    if remote.get("authorization") != {
        "user_approved_remote_jnlp_observation": False,
        "external_jnlp_observation_authorized": False,
        "credentials_may_be_referenced": False,
        "jforex_connect_authorized": False,
        "provider_schedule_query_authorized": False,
        "price_or_availability_access_authorized": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "outcome_access_authorized": False,
    } or remote.get("workflow") != {
        "implemented": False,
        "dispatchable_before_separate_user_approval": False,
        "exact_manual_confirmation": "OBSERVE_PHASE9_REMOTE_JNLP_IDENTITY_ONLY_NO_CONNECT_NO_SECRETS",
    }:
        raise GateError("Remote JNLP proposal authorization changed")
    forbidden_fragments = tuple(contract["owned_source_prohibitions"])
    for path in sources:
        value = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in value:
                raise GateError(f"Forbidden source surface {fragment!r}: {relative(path)}")

    old_acquirer = ROOT / "runner/jforex/src/main/java/org/phase9/Phase9JForexAcquirer.java"
    if old_acquirer.resolve().is_relative_to(MODULE.resolve()):
        raise GateError("Existing price acquirer entered metadata module")
    if any(path.name == old_acquirer.name for path in sources):
        raise GateError("Existing price acquirer copied into metadata module")
    return {
        "owned_source_paths": observed_sources,
        "owned_source_sha256": observed_hashes,
        "module_pom_sha256": sha256(pom),
        "synthetic_api_fixture_sha256": fixture_hashes,
        "old_price_acquirer_physically_excluded": True,
    }


METHOD_REF = re.compile(
    r"^\s*#\d+\s+=\s+(?:InterfaceMethodref|Methodref)\s+.+//\s+"
    r"(?P<owner>com/dukascopy/[^.]+)\.\"?(?P<name>[^\":]+)\"?:(?P<descriptor>\S+)\s*$"
)


def bytecode_provider_method_references(classes_dir: Path) -> list[str]:
    class_files = sorted((classes_dir / "org/phase9/metadata").glob("*.class"))
    names = [path.relative_to(classes_dir).as_posix() for path in class_files]
    expected = [
        "org/phase9/metadata/Phase9MetadataClient.class",
        "org/phase9/metadata/Phase9OfflineDomainPlugin.class",
    ]
    if names != expected:
        raise GateError(f"Owned class set changed: {names}")
    references: set[str] = set()
    for class_file in class_files:
        result = subprocess.run(
            ["javap", "-p", "-v", str(class_file)],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            match = METHOD_REF.match(line)
            if match:
                references.add(
                    f"{match.group('owner')}.{match.group('name')}:{match.group('descriptor')}"
                )
        for forbidden in (
            "com/dukascopy/api/system/ITesterClient",
            "com/dukascopy/api/IStrategy",
            "com/dukascopy/api/IHistory",
            "com/dukascopy/api/IBar",
            "com/dukascopy/api/ITick",
            "com/dukascopy/api/IEngine",
            "com/dukascopy/api/IAccount",
        ):
            if forbidden in result.stdout:
                raise GateError(f"Forbidden provider class reference: {forbidden}")
    return sorted(references)


def verify(classes_dir: Path | None = None) -> dict[str, Any]:
    static = validate_static_contract()
    allowlist = load_object(METHOD_ALLOWLIST)
    observed_methods: list[str] | None = None
    if classes_dir is not None:
        observed_methods = bytecode_provider_method_references(classes_dir)
        if observed_methods != allowlist.get("dukascopy_method_references"):
            raise GateError(
                "Owned bytecode method references changed:\n"
                + json.dumps(observed_methods, indent=2)
            )
    audit = {
        "schema_version": "phase9-metadata-local-m1-audit-v1.0",
        "status": "LOCAL_SYNTHETIC_PRECONDITIONS_PASS_REMOTE_EXECUTION_BLOCKED",
        "contract_sha256": sha256(CONTRACT),
        "method_allowlist_sha256": sha256(METHOD_ALLOWLIST),
        "remote_jnlp_proposal_sha256": sha256(REMOTE_PROPOSAL),
        "remote_jnlp_proposal_markdown_sha256": sha256(REMOTE_PROPOSAL_MARKDOWN),
        **static,
        "bytecode_provider_method_references": observed_methods,
        "bytecode_exact_match_checked": classes_dir is not None,
        "compiled_against_real_jforex_api_2_13_99_jar": False,
        "real_jforex_api_2_13_99_compatibility_verified": False,
        "real_jforex_runtime_methodrefs_verified": False,
        "java_path_toctou_resistant_connection_custody_verified": False,
        "synthetic_only": True,
        "credentials_referenced": False,
        "external_jnlp_request_attempted": False,
        "jforex_connect_invoked": False,
        "availability_request_attempted": False,
        "provider_schedule_request_attempted": False,
        "market_price_request_attempted": False,
        "forbidden_market_period_request_attempted": False,
        "phase9_price_files_acquired": 0,
        "provider_schedule_inventory_acquired": False,
        "provider_schedule_allowlist_frozen": False,
        "acquisition_authorized": False,
        "count_only_authorized": False,
        "research_outcomes_calculated": False,
        "outcome_fields": [],
    }
    return audit


def write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
        raise GateError("Audit file custody failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classes-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    write_new(arguments.output, verify(arguments.classes_dir))


if __name__ == "__main__":
    main()
