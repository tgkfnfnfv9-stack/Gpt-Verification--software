from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = load_module(
    "verify_phase9_remote_libs_jnlp_independent_audit_tests",
    ROOT / "runner/verify_phase9_remote_libs_jnlp_independent_audit.py",
)


def load_inputs():
    audit = json.loads(VERIFY.AUDIT_PATH.read_text(encoding="utf-8"))
    allowlist = json.loads(VERIFY.ALLOWLIST_PATH.read_text(encoding="utf-8"))
    independent = json.loads(VERIFY.INDEPENDENT_PATH.read_text(encoding="utf-8"))
    return audit, allowlist, independent


class IndependentAuditTests(unittest.TestCase):
    def test_frozen_independent_audit_passes(self):
        value = VERIFY.verify()
        self.assertEqual(value["http_request_count"], 1)
        self.assertEqual(value["reference_count"], 36)
        self.assertEqual(value["phase9_price_files"], 0)
        self.assertFalse(value["research_outcomes_calculated"])

    def test_requested_reference_is_rejected(self):
        audit, allowlist, independent = load_inputs()
        audit["jnlp_identity"]["references"][0]["fetched"] = True
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify_dicts(audit, allowlist, independent)

    def test_allowlist_drift_is_rejected(self):
        audit, allowlist, independent = load_inputs()
        drifted = copy.deepcopy(allowlist)
        drifted["entries"][0]["resolved_url"] += "?changed=1"
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify_dicts(audit, drifted, independent)

    def test_price_or_outcome_access_is_rejected(self):
        audit, allowlist, independent = load_inputs()
        price = copy.deepcopy(independent)
        price["prohibited_activity"]["phase9_price_files_acquired"] = 1
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify_dicts(audit, allowlist, price)
        outcome = copy.deepcopy(independent)
        outcome["prohibited_activity"]["research_outcomes_calculated"] = True
        with self.assertRaises(VERIFY.VerificationError):
            VERIFY.verify_dicts(audit, allowlist, outcome)


if __name__ == "__main__":
    unittest.main()
