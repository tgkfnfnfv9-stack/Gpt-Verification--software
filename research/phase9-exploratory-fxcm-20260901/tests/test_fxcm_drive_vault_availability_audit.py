import json
import unittest
from pathlib import Path


TRACK = Path(__file__).resolve().parents[1]
AUDIT = TRACK / "results/run-33627420903/FXCM_DRIVE_VAULT_AVAILABILITY_INDEPENDENT_AUDIT.json"


class VaultAvailabilityAuditTests(unittest.TestCase):
    def setUp(self):
        self.audit = json.loads(AUDIT.read_text())

    def test_exact_target_and_observed_totals(self):
        target = self.audit["target"]
        result = self.audit["result"]
        self.assertEqual(target["required_source_object_count"], 16 * 28 * 3 * 52)
        self.assertEqual(result["present_source_object_count"], 36000)
        self.assertEqual(result["missing_or_unavailable_source_object_count"], 33888)
        self.assertEqual(
            result["present_source_object_count"] + result["missing_or_unavailable_source_object_count"],
            target["required_source_object_count"],
        )
        self.assertEqual(sum(row["present"] for row in result["periodicity"].values()), 36000)
        self.assertEqual(sum(row["missing"] for row in result["periodicity"].values()), 33888)

    def test_blocking_absences_are_explicit(self):
        result = self.audit["result"]
        self.assertEqual(result["periodicity"]["D1"]["present"], 0)
        self.assertEqual(result["years_fully_unavailable"], [2010, 2011])
        self.assertEqual(result["symbols_fully_unavailable"], ["CHFJPY", "EURCAD", "GBPAUD"])
        self.assertFalse(result["all_target_objects_present"])

    def test_price_and_outcome_boundaries_remain_closed(self):
        validation = self.audit["independent_validation"]
        decision = self.audit["decision"]
        self.assertEqual(validation["total_response_body_bytes_read"], 0)
        self.assertFalse(validation["price_acquisition_executed"])
        self.assertFalse(validation["research_outcomes_calculated"])
        self.assertFalse(decision["v1_acquisition_workflow_authorized"])
        self.assertFalse(decision["silent_scope_reduction_allowed"])
        self.assertFalse(decision["root_seal_allowed"])
        self.assertFalse(decision["batch6_allowed"])

    def test_exact_year_and_artifact_sets(self):
        years = self.audit["year_summary"]
        artifacts = self.audit["source_artifacts"]
        self.assertEqual([row["year"] for row in years], list(range(2010, 2026)))
        self.assertEqual([row["year"] for row in artifacts], list(range(2010, 2026)))
        self.assertEqual(len({row["artifact_id"] for row in artifacts}), 16)
        self.assertTrue(all(len(row["zip_sha256"]) == 64 for row in artifacts))
        self.assertTrue(all(len(row["report_sha256"]) == 64 for row in artifacts))


if __name__ == "__main__":
    unittest.main()
