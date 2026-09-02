from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


OBSERVER = load_module(
    "phase9_remote_libs_jnlp_observer_v2_tests",
    ROOT / "runner/phase9_remote_libs_jnlp_observer.py",
)
VERIFIER = load_module(
    "verify_phase9_remote_libs_jnlp_observation_v2_tests",
    ROOT / "runner/verify_phase9_remote_libs_jnlp_observation_v2.py",
)
GATE_V1 = ROOT / "spec/remote_libs_jnlp_observation_gate.frozen.json"
GATE_V2 = ROOT / "spec/remote_libs_jnlp_observation_gate_v2.frozen.json"


def args(**overrides):
    values = {
        "confirmation": VERIFIER.EXACT_CONFIRMATION,
        "github_event_name": "workflow_dispatch",
        "github_ref": "refs/heads/main",
        "github_sha": "b" * 40,
        "github_run_id": "456",
        "github_run_number": "1",
        "github_run_attempt": "1",
        "github_job": "observe",
        "timeout_seconds": 5.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class V2GateTests(unittest.TestCase):
    def test_v2_gate_and_source_evidence_validate(self):
        gate, digest = OBSERVER.validate_gate(GATE_V2)
        self.assertEqual(digest, VERIFIER.EXPECTED_GATE_SHA256)
        self.assertFalse(gate["single_use_authorization"]["repository_preapproval"])
        self.assertTrue(
            gate["single_use_authorization"]["exact_manual_dispatch_is_approval"]
        )
        self.assertEqual(gate["v1_incident"]["http_request_count"], 0)

    def test_v1_gate_remains_verifiable_and_consumed(self):
        gate, _digest = OBSERVER.validate_gate(GATE_V1)
        self.assertEqual(
            gate["single_use_authorization"]["authorization_consumed_on"],
            "FIRST_WORKFLOW_DISPATCH_REGARDLESS_OF_RESULT",
        )
        self.assertFalse(gate["single_use_authorization"]["retry_authorized"])

    def test_corrected_static_workflow_verification_passes(self):
        value = VERIFIER.verify_static()
        self.assertEqual(value["v1_http_request_count"], 0)
        self.assertFalse(value["acquisition_authorized"])
        self.assertFalse(value["count_only_authorized"])
        self.assertFalse(value["research_outcomes_calculated"])

    def test_invalid_v2_run_identity_never_uses_network(self):
        gate, digest = OBSERVER.validate_gate(GATE_V2)
        confirmation = gate["approval_context"]["exact_confirmation"]
        utility = OBSERVER.utility
        with mock.patch.object(
            utility.socket, "getaddrinfo", side_effect=AssertionError("network used")
        ) as resolver:
            audit = OBSERVER.observe(
                args(github_run_number="2"), digest, confirmation
            )
        resolver.assert_not_called()
        self.assertEqual(audit["transport"]["http_request_count"], 0)
        self.assertEqual(audit["status"], "ATTEMPTED_TERMINAL_NEW_APPROVAL_REQUIRED")

    def test_wrong_confirmation_never_uses_network(self):
        gate, digest = OBSERVER.validate_gate(GATE_V2)
        confirmation = gate["approval_context"]["exact_confirmation"]
        utility = OBSERVER.utility
        with mock.patch.object(
            utility.socket, "getaddrinfo", side_effect=AssertionError("network used")
        ) as resolver:
            audit = OBSERVER.observe(args(confirmation="WRONG"), digest, confirmation)
        resolver.assert_not_called()
        self.assertEqual(audit["transport"]["http_request_count"], 0)


if __name__ == "__main__":
    unittest.main()
