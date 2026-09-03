import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AVAILABILITY = ROOT / ".github/workflows/phase9-exploratory-fxcm-drive-vault-availability-v1.yml"
ACQUISITION = ROOT / ".github/workflows/phase9-exploratory-fxcm-drive-vault-acquisition-v1.yml"


class VaultWorkflowTests(unittest.TestCase):
    def test_both_workflows_are_manual_only_and_single_use(self):
        for path in (AVAILABILITY, ACQUISITION):
            text = path.read_text()
            self.assertIn("workflow_dispatch:", text)
            self.assertNotRegex(text, r"(?m)^\s*(push|schedule|workflow_run|repository_dispatch):")
            self.assertIn("github.run_number == 1", text)
            self.assertIn("github.run_attempt == 1", text)
            self.assertIn("inputs.expected_head_sha == github.sha", text)
            self.assertIn("contents: read", text)
            self.assertNotIn("id-token: write", text)

    def test_acquisition_has_exact_year_matrix_and_always_cleanup(self):
        text = ACQUISITION.read_text()
        years = re.search(r"year: \[([^]]+)\]", text).group(1)
        self.assertEqual([int(value.strip()) for value in years.split(",")], list(range(2010, 2026)))
        self.assertGreaterEqual(text.count("if: ${{ always() }}"), 2)
        self.assertIn("environment: phase9-fxcm-vault-acquisition", text)
        self.assertIn("Finalize exact 1344-shard vault and write seal last", text)
        self.assertNotIn("phase9-exploratory-fxcm-blind-mtf-batch6-count-only", text)

    def test_oauth_secrets_are_environment_only_and_artifact_is_price_free(self):
        text = ACQUISITION.read_text()
        for name in (
            "PHASE9_GDRIVE_OAUTH_CLIENT_ID",
            "PHASE9_GDRIVE_OAUTH_CLIENT_SECRET",
            "PHASE9_GDRIVE_OAUTH_REFRESH_TOKEN",
        ):
            self.assertIn(f"{name}: ${{{{ secrets.{name} }}}}", text)
        self.assertIn("Upload exact price-free vault audit only", text)
        self.assertNotRegex(text, r"(?m)^\s*path:\s+.*(?:csv|gz|tar|zst)")

    def test_existing_batch6_workflow_is_fail_closed_and_not_called(self):
        batch6 = ROOT / ".github/workflows/phase9-exploratory-fxcm-blind-mtf-batch6-count-only.yml"
        self.assertTrue(batch6.exists())
        self.assertIn("${{ false &&", batch6.read_text())
        availability_text = AVAILABILITY.read_text()
        acquisition_text = ACQUISITION.read_text()
        self.assertNotIn(batch6.name, availability_text)
        self.assertNotIn(batch6.name, acquisition_text)


if __name__ == "__main__":
    unittest.main()
