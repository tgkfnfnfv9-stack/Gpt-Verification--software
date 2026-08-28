import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("blind_discovery", ROOT / "runner" / "blind_discovery.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_bars(count=400, start=datetime(2019, 7, 1), step=timedelta(hours=1)):
    bars = []
    price = 100.0
    for i in range(count):
        dt = start + i * step
        close = price + (0.03 if i % 2 else -0.01)
        bars.append(MODULE.Bar(dt, price, max(price, close) + 0.05, min(price, close) - 0.05, close,
                               price + 0.02, max(price, close) + 0.07, min(price, close) - 0.03,
                               close + 0.02, 100 + i % 20))
        price = close
    return bars


class BlindDiscoveryTests(unittest.TestCase):
    def test_registry_has_five_independent_candidates_per_family(self):
        registry = json.loads((ROOT / "spec" / "candidate_registry.json").read_text(encoding="utf-8"))
        counts = {}
        for candidate in registry["candidates"]:
            counts[candidate["family"]] = counts.get(candidate["family"], 0) + 1
            self.assertNotIn(candidate["strategy_id"], {"STRAT-PA-002"})
        self.assertEqual(counts, {
            "PRICE_ACTION": 5,
            "VOLUME_VOLATILITY": 5,
            "MARKET_REGIME_CROSS_MARKET": 5,
        })

    def test_h4_aggregation_keeps_bid_and_ask_separate(self):
        source = make_bars(8)
        result = MODULE.aggregate(source, 4)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].bo, source[0].bo)
        self.assertEqual(result[0].ao, source[0].ao)
        self.assertEqual(result[0].bc, source[3].bc)
        self.assertEqual(result[0].ac, source[3].ac)

    def test_buy_outcome_uses_ask_entry_and_bid_exit(self):
        series = MODULE.build_series("TEST", "H1", make_bars())
        i = 300
        signal = MODULE.Signal("STRAT-PA-101", "TEST", "H1", i, "BUY")
        result = MODULE.outcome(series, signal)
        expected = (series.bars[i + 2].bo - series.bars[i + 1].ao) / series.atr[i]
        self.assertAlmostEqual(result["bar_1"]["return"], expected)

    def test_sell_outcome_uses_bid_entry_and_ask_exit(self):
        series = MODULE.build_series("TEST", "H1", make_bars())
        i = 300
        signal = MODULE.Signal("STRAT-PA-101", "TEST", "H1", i, "SELL")
        result = MODULE.outcome(series, signal)
        expected = (series.bars[i + 1].bo - series.bars[i + 2].ao) / series.atr[i]
        self.assertAlmostEqual(result["bar_1"]["return"], expected)

    def test_split_end_censors_outcome(self):
        start = MODULE.DISCOVERY_END - timedelta(hours=350)
        series = MODULE.build_series("TEST", "H1", make_bars(start=start))
        signal_i = max(i for i, bar in enumerate(series.bars) if bar.dt < MODULE.DISCOVERY_END)
        signal = MODULE.Signal("STRAT-PA-101", "TEST", "H1", signal_i, "BUY")
        self.assertIsNone(MODULE.outcome(series, signal))

    def test_lagged_quantile_does_not_use_recent_gap(self):
        values = [1.0] * 260
        values[251:259] = [999.0] * 8
        result = MODULE.lagged_quantile(values, history=240, gap=8, quantile=0.2)
        self.assertEqual(result[259], 1.0)


if __name__ == "__main__":
    unittest.main()
