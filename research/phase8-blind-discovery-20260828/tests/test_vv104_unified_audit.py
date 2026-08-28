import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runner"
sys.path.insert(0, str(RUNNER))
SPEC = importlib.util.spec_from_file_location("vv104_unified_audit", RUNNER / "vv104_unified_audit.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class UnifiedAuditTests(unittest.TestCase):
    def test_nested_timeframes_share_one_episode_weight(self):
        rows = [
            {"dt": datetime(2020, 1, 1, 1), "side": "BUY", "edge_primary": 1.0, "timeframe": "M15"},
            {"dt": datetime(2020, 1, 1, 8), "side": "BUY", "edge_primary": 3.0, "timeframe": "H1"},
            {"dt": datetime(2020, 1, 2, 4), "side": "BUY", "edge_primary": -2.0, "timeframe": "H4"},
        ]
        episodes = MODULE.episode_map(rows)
        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes[("2020-01-01", "BUY")], 2.0)
        self.assertEqual(sum(episodes.values()) / len(episodes), 0.0)

    def test_buy_and_sell_are_separate_direction_clusters(self):
        rows = [
            {"dt": datetime(2020, 1, 1, 1), "side": "BUY", "edge_primary": 1.0},
            {"dt": datetime(2020, 1, 1, 2), "side": "SELL", "edge_primary": -1.0},
        ]
        self.assertEqual(len(MODULE.episode_map(rows)), 2)

    def test_final_audit_resolves_any_failed_gate_to_reject(self):
        self.assertEqual(MODULE.final_decision({"a": True, "b": False}), "REJECT_FOR_DEVELOPMENT")
        self.assertEqual(MODULE.final_decision({"a": True, "b": True}), "DEVELOPMENT")


if __name__ == "__main__":
    unittest.main()
