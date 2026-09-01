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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


readiness = load_module(
    "verify_phase9_provider_schedule_readiness",
    ROOT / "runner/verify_phase9_provider_schedule_readiness.py",
)


class ProviderScheduleReadinessTests(unittest.TestCase):
    def copy_blocked_inputs(self, root: Path) -> None:
        for relative in (
            "data_manifest/trading_calendar.json",
            "spec/provider_schedule_contract.frozen.json",
            "SESSION_STATE.json",
        ):
            source = ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

    def test_current_repository_is_fail_closed_on_missing_authoritative_source(self):
        audit = readiness.blocked_audit()
        self.assertEqual(audit["status"], readiness.BLOCKED_STATUS)
        self.assertFalse(audit["canonical_source_present"])
        self.assertEqual(audit["provider_schedule_version"], "NO_VERSION_AVAILABLE_YET")
        self.assertEqual(len(audit["blockers"]), 3)

    def test_blocked_audit_keeps_every_authorization_false_and_prices_zero(self):
        audit = readiness.blocked_audit()
        for key in (
            "provider_schedule_inventory_acquired",
            "provider_schedule_allowlist_frozen",
            "same_run_self_authorization_used",
            "credentials_referenced",
            "external_jnlp_request_attempted",
            "jforex_connect_invoked",
            "availability_request_attempted",
            "market_price_request_attempted",
            "forbidden_market_period_request_attempted",
            "actual_market_data_full_quality_gate_passed",
            "acquisition_authorized",
            "count_only_authorized",
            "research_outcomes_calculated",
        ):
            self.assertIs(audit[key], False, key)
        self.assertEqual(audit["phase9_price_files_acquired"], 0)
        self.assertEqual(audit["outcome_fields"], [])

    def test_source_inventory_or_allowlist_presence_stops_blocked_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_blocked_inputs(root)
            for relative in (
                "data_manifest/provider_schedule_source.frozen.json",
                "data_manifest/provider_schedule_inventory.json",
                "spec/provider_schedule_exact_allowlist.frozen.json",
            ):
                with self.subTest(relative=relative):
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("{}\n", encoding="utf-8")
                    with self.assertRaises(readiness.ReadinessError):
                        readiness.blocked_audit(root)
                    target.unlink()

    def test_state_authorization_or_readiness_mutation_is_rejected(self):
        mutations = (
            ("provider_schedule_inventory_acquired", True),
            ("provider_schedule_allowlist_frozen", True),
        )
        for field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.copy_blocked_inputs(root)
                path = root / "SESSION_STATE.json"
                state = json.loads(path.read_text(encoding="utf-8"))
                state["provider_acquisition"][field] = value
                path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(readiness.ReadinessError):
                    readiness.blocked_audit(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_blocked_inputs(root)
            path = root / "SESSION_STATE.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            state["provider_acquisition"]["provider_schedule_source_readiness"][
                "metadata_only_connection_amendment_authorized"
            ] = True
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(readiness.ReadinessError):
                readiness.blocked_audit(root)

    def test_cli_requires_exact_confirmation_and_creates_new_report_only(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "audit.json"
            with mock.patch.object(sys, "argv", ["runner", "--confirmation", "wrong", "--report", str(report)]):
                with self.assertRaises(readiness.ReadinessError):
                    readiness.main()
            with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "a" * 40}):
                with mock.patch.object(sys, "argv", [
                    "runner", "--confirmation", readiness.CONFIRMATION, "--report", str(report)
                ]):
                    self.assertEqual(readiness.main(), 0)
            value = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(value["run_id"], 123)
            self.assertEqual(value["head_sha"], "a" * 40)
            with self.assertRaises(FileExistsError):
                readiness.write_new_json(report, value)

    def test_workflow_is_metadata_only_and_does_not_invoke_market_runners(self):
        workflow = (ROOT.parents[1] / ".github/workflows/phase9-provider-schedule-readiness-preflight.yml").read_text(
            encoding="utf-8"
        )
        for prohibited in (
            "acquire_phase9_data.py",
            "validate_phase9_acquisition.py",
            "phase9_actual_full_qc.py",
            "phase9_full_qc.py",
            "Phase9JForexAcquirer",
            "mvn ",
            "java ",
            "curl ",
            "wget ",
            "secrets.",
        ):
            self.assertNotIn(prohibited, workflow)
        self.assertIn(readiness.CONFIRMATION, workflow)
        self.assertIn("permissions:\n  contents: read", workflow)

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
