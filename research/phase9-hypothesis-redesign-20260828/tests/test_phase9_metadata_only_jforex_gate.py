from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = load_module(
    "verify_phase9_metadata_only_jforex_gate",
    ROOT / "runner/verify_phase9_metadata_only_jforex_gate.py",
)


class MetadataOnlyJForexGateTests(unittest.TestCase):
    def copy_inputs(self, target_root: Path) -> None:
        for relative in (
            "spec/metadata_only_jforex_schedule_gate.frozen.json",
            "spec/provider_schedule_contract.frozen.json",
            "data_manifest/trading_calendar.json",
            "SESSION_STATE.json",
        ):
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())

    def test_current_amendment_is_frozen_but_connection_dispatch_is_blocked(self):
        audit = gate.verify_gate()
        self.assertEqual(audit["status"], gate.STATUS)
        self.assertTrue(audit["amendment_authorized"])
        self.assertFalse(audit["connection_dispatch_authorized"])
        self.assertGreaterEqual(len(audit["remaining_blockers"]), 12)

    def test_every_access_and_research_effect_remains_false(self):
        audit = gate.verify_gate()
        for key in (
            "connection_dispatch_authorized",
            "credentials_referenced",
            "external_jnlp_request_attempted",
            "jforex_connect_invoked",
            "availability_request_attempted",
            "schedule_metadata_request_attempted",
            "market_price_request_attempted",
            "forbidden_market_period_request_attempted",
            "provider_schedule_inventory_acquired",
            "provider_schedule_allowlist_frozen",
            "same_run_self_authorization_used",
            "actual_market_data_full_quality_gate_passed",
            "acquisition_authorized",
            "count_only_authorized",
            "research_outcomes_calculated",
        ):
            self.assertIs(audit[key], False, key)
        self.assertEqual(audit["phase9_price_files_acquired"], 0)
        self.assertEqual(audit["outcome_fields"], [])

    def test_any_dispatch_or_research_authorization_mutation_is_rejected(self):
        mutations = (
            ("connection_dispatch_authorized", True),
            ("demo_credentials_may_be_configured", True),
            ("provider_schedule_inventory_acquired", True),
            ("acquisition_authorized", True),
            ("count_only_authorized", True),
        )
        for field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_inputs(root)
                path = root / "spec/metadata_only_jforex_schedule_gate.frozen.json"
                contract = json.loads(path.read_text(encoding="utf-8"))
                contract["authorization"][field] = value
                path.write_text(json.dumps(contract), encoding="utf-8")
                with self.assertRaises(gate.GateError):
                    gate.verify_gate(root)

    def test_forbidden_provider_source_inventory_or_allowlist_is_rejected(self):
        for relative in (
            "data_manifest/provider_schedule_source.frozen.json",
            "data_manifest/provider_schedule_inventory.json",
            "spec/provider_schedule_exact_allowlist.frozen.json",
        ):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_inputs(root)
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("{}\n", encoding="utf-8")
                with self.assertRaises(gate.GateError):
                    gate.verify_gate(root)

    def test_cli_requires_exact_confirmation_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "audit.json"
            with mock.patch.object(sys, "argv", ["runner", "--confirmation", "wrong", "--report", str(report)]):
                with self.assertRaises(gate.GateError):
                    gate.main()
            with mock.patch.dict(os.environ, {
                "GITHUB_RUN_ID": "456",
                "GITHUB_RUN_ATTEMPT": "3",
                "GITHUB_SHA": "b" * 40,
            }):
                with mock.patch.object(sys, "argv", [
                    "runner", "--confirmation", gate.CONFIRMATION, "--report", str(report)
                ]):
                    self.assertEqual(gate.main(), 0)
            value = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(value["run_id"], 456)
            self.assertEqual(value["head_sha"], "b" * 40)
            with self.assertRaises(FileExistsError):
                gate.write_new_json(report, value)

    def test_workflow_has_no_connection_or_secret_capability(self):
        workflow = (REPOSITORY_ROOT / ".github/workflows/phase9-metadata-only-jforex-gate-preflight.yml").read_text(
            encoding="utf-8"
        )
        prohibited = (
            "secrets.",
            "Phase9JForexAcquirer",
            "ClientFactory",
            "TesterFactory",
            "getAvailableInstruments",
            "getOfflineTimeDomains",
            "downloadData",
            "setDataInterval",
            "mvn ",
            "java ",
            "curl ",
            "wget ",
        )
        for token in prohibited:
            self.assertNotIn(token, workflow)
        self.assertIn(gate.CONFIRMATION, workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("github.event_name == 'push'", workflow)

    def test_contract_permits_only_offline_domain_schedule_metadata(self):
        contract = json.loads((ROOT / "spec/metadata_only_jforex_schedule_gate.frozen.json").read_text())
        scope = contract["future_observation_scope"]
        self.assertEqual(
            scope["only_permitted_provider_data_call"],
            "IContext.getDataService().getOfflineTimeDomains(long,long,Instrument)",
        )
        self.assertTrue(all(contract["mechanical_prohibitions"].values()))
        self.assertTrue(scope["observation_may_not_claim_complete_interval_inventory"])

    def test_unknown_scope_key_period_change_or_removed_blocker_is_rejected(self):
        mutations = (
            lambda value: value["future_observation_scope"].__setitem__("second_permitted_call", "getBars"),
            lambda value: value["future_observation_scope"]["end_exclusive_by_timeframe"].__setitem__(
                "H1", "2026-08-28T00:00:00Z"
            ),
            lambda value: value["required_before_connection_dispatch"].pop(),
        )
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_inputs(root)
                path = root / "spec/metadata_only_jforex_schedule_gate.frozen.json"
                contract = json.loads(path.read_text(encoding="utf-8"))
                mutate(contract)
                path.write_text(json.dumps(contract), encoding="utf-8")
                with self.assertRaises(gate.GateError):
                    gate.verify_gate(root)

    def test_frozen_scientific_anchors_are_unchanged(self):
        expected = {
            "spec/candidate_registry.frozen.json": "8740f58efe48c40ba0664606194b18b40cf14c27",
            "spec/data_requirements.frozen.json": "7e6a476366140e07edac4e4316f8c08a6ab4ae92",
            "policy/preregistered_research_policy.json": "8483418a6a75f5a6ea7d6b54ca54beb68896855f",
        }
        for relative, blob in expected.items():
            actual = subprocess.check_output(["git", "hash-object", ROOT / relative], text=True).strip()
            self.assertEqual(actual, blob, relative)


if __name__ == "__main__":
    unittest.main()
