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
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = load_module(
    "verify_phase9_remote_jnlp_independent_audit",
    ROOT / "runner/verify_phase9_remote_jnlp_independent_audit.py",
)
AUDIT = json.loads(VERIFY.AUDIT.read_text(encoding="utf-8"))
ALLOWLIST = json.loads(VERIFY.ALLOWLIST.read_text(encoding="utf-8"))


class RemoteJnlpIndependentAuditTests(unittest.TestCase):
    def test_committed_independent_audit_and_exact_url_set_pass(self):
        value = VERIFY.verify_values(copy.deepcopy(AUDIT), copy.deepcopy(ALLOWLIST))
        self.assertEqual(value["status"], "PASS_EXACT_URLS_FROZEN_FOLLOWUP_BLOCKED")
        self.assertEqual(value["canonical_exact_url_count"], 5)
        self.assertFalse(value["followup_request_authorized"])
        self.assertFalse(value["acquisition_authorized"])
        self.assertFalse(value["research_outcomes_calculated"])

    def test_source_run_job_artifact_head_and_zip_are_immutable(self):
        fields = [
            ("run_id", 1), ("job_id", 1), ("artifact_id", 1),
            ("run_number", True),
            ("head_sha", "0" * 40),
            ("independently_downloaded_zip_sha256", "0" * 64),
        ]
        for key, changed in fields:
            audit = copy.deepcopy(AUDIT)
            audit["github_actions"][key] = changed
            with self.subTest(key=key), self.assertRaises(VERIFY.AuditError):
                VERIFY.verify_values(audit, copy.deepcopy(ALLOWLIST))

    def test_url_sha_addition_removal_and_authorization_flip_fail(self):
        mutations = []
        missing = copy.deepcopy(ALLOWLIST)
        missing["canonical_exact_string_set"].pop()
        mutations.append(missing)
        added = copy.deepcopy(ALLOWLIST)
        added["canonical_exact_string_set"].append("https://example.invalid/x")
        mutations.append(added)
        changed = copy.deepcopy(ALLOWLIST)
        changed["entries"][2]["url_sha256"] = "0" * 64
        mutations.append(changed)
        authorized = copy.deepcopy(ALLOWLIST)
        authorized["authorization"]["extension_jnlp_request_authorized"] = True
        mutations.append(authorized)
        requested = copy.deepcopy(ALLOWLIST)
        requested["entries"][4]["request_authorized_after_source_run"] = True
        mutations.append(requested)
        wrong_parent = copy.deepcopy(ALLOWLIST)
        wrong_parent["freeze_separation"]["required_freeze_parent_sha"] = "0" * 40
        mutations.append(wrong_parent)
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(VERIFY.AuditError):
                VERIFY.verify_values(copy.deepcopy(AUDIT), value)

    def test_raw_body_credential_price_and_outcome_mutations_fail(self):
        audit_raw = copy.deepcopy(AUDIT)
        audit_raw["observation"]["raw_jnlp_bytes"] = "forbidden"
        allow_secret = copy.deepcopy(ALLOWLIST)
        allow_secret["authorization"]["secret"] = "forbidden"
        allow_price = copy.deepcopy(ALLOWLIST)
        allow_price["authorization"]["price_access_authorized"] = True
        audit_outcome = copy.deepcopy(AUDIT)
        audit_outcome["scientific_state"]["research_outcomes_calculated"] = True
        for audit, allowlist in (
            (audit_raw, copy.deepcopy(ALLOWLIST)),
            (copy.deepcopy(AUDIT), allow_secret),
            (copy.deepcopy(AUDIT), allow_price),
            (audit_outcome, copy.deepcopy(ALLOWLIST)),
        ):
            with self.assertRaises(VERIFY.AuditError):
                VERIFY.verify_values(audit, allowlist)

    def test_unknown_root_nested_and_entry_fields_fail_closed(self):
        mutations = []
        audit_root = copy.deepcopy(AUDIT)
        audit_root["unknown"] = False
        mutations.append((audit_root, copy.deepcopy(ALLOWLIST)))
        audit_nested = copy.deepcopy(AUDIT)
        audit_nested["observation"]["unknown"] = False
        mutations.append((audit_nested, copy.deepcopy(ALLOWLIST)))
        allow_root = copy.deepcopy(ALLOWLIST)
        allow_root["unknown"] = False
        mutations.append((copy.deepcopy(AUDIT), allow_root))
        allow_entry = copy.deepcopy(ALLOWLIST)
        allow_entry["entries"][0]["unknown"] = False
        mutations.append((copy.deepcopy(AUDIT), allow_entry))
        for index, (audit, allowlist) in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(VERIFY.AuditError):
                VERIFY.verify_values(audit, allowlist)


if __name__ == "__main__":
    unittest.main()
