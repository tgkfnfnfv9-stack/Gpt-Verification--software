from __future__ import annotations

import csv
import gzip
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fxcm_qc", ROOT / "runner/fxcm_exploratory_qc.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def source(path: Path, rows: list[list[str]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(module.EXPECTED_HEADER)
        writer.writerows(rows)


class FxcmQCTests(unittest.TestCase):
    def test_frozen_contract(self):
        value = module.load_contract(ROOT / "spec/fxcm_exploratory_contract.frozen.json")
        self.assertEqual(len(value["symbols"]), 8)
        self.assertFalse(value["formal_authorization_effect"])
        self.assertEqual(value["provider"], module.EXPECTED_PROVIDER)
        self.assertEqual(value["usage_constraints"], module.EXPECTED_USAGE)

    def test_bid_ask_integrity_and_gap_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gz = root / "one.csv.gz"
            source(gz, [
                ["01/01/2017 00:00:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
                ["01/01/2017 02:00:00.000", "1.1", "1.3", "1", "1.2", "1.11", "1.31", "1.01", "1.21"],
            ])
            prices = root / "prices"; prices.mkdir()
            observed = root / "observed"; observed.mkdir()
            item = module.process_symbol("EURUSD", [gz], prices, observed)
            self.assertEqual(item["bar_count"], 2)
            self.assertEqual(item["gap_segment_count"], 1)
            self.assertEqual(item["missing_hour_slot_count"], 1)

    def test_crossed_open_bad_geometry_and_forbidden_time_fail(self):
        rows = [
            ["01/01/2017 00:00:00.000", "1", "1.2", "0.9", "1.1", "0.99", "1.21", "0.91", "1.11"],
            ["01/01/2017 00:00:00.000", "1", "0.8", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
            ["12/31/2018 00:00:00.000", "1", "1.2", "0.9", "1.1", "1.01", "1.21", "0.91", "1.11"],
        ]
        for row in rows:
            with self.subTest(row=row), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); gz = root / "bad.csv.gz"; source(gz, [row])
                (root / "prices").mkdir(); (root / "observed").mkdir()
                with self.assertRaises(module.FxcmError):
                    module.process_symbol("EURUSD", [gz], root / "prices", root / "observed")

    def test_outcome_fields_rejected(self):
        module.reject_outcomes({"bar_count": 1})
        with self.assertRaises(module.FxcmError):
            module.reject_outcomes({"edge": 0})

    def test_workflow_is_manual_only(self):
        workflow = (ROOT.parents[1] / ".github/workflows/phase9-exploratory-fxcm-qc.yml").read_text()
        self.assertNotIn("  push:", workflow)
        self.assertIn(module.CONFIRMATION, workflow)
        self.assertIn(module.USAGE_CONFIRMATION, workflow)


if __name__ == "__main__":
    unittest.main()
