import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strategy  # noqa: E402


class TestStandaloneStrategy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.px = strategy.load_prices().loc[: "2026-10-30"]
        cls.cfg = strategy.load_config()
        cls.sig = strategy.make_signal(cls.px, cls.cfg["signal"])
        cls.pnl, cls.pos = strategy.backtest(cls.px, cls.sig)

    def test_long_only(self):
        self.assertTrue(self.pos.between(0, 1).all())

    def test_next_open_execution(self):
        dates = pd.date_range("2026-01-01", periods=4)
        px = pd.DataFrame({"open": [1.0, 2.0, 3.0, 4.0],
                           "high": [1.1, 2.2, 3.3, 4.4],
                           "low": [0.9, 1.8, 2.8, 3.8],
                           "close": [1.1, 2.2, 3.3, 4.4],
                           "volume": 1.0, "amount": 1.0}, index=dates)
        target = pd.Series([1.0, 1.0, 0.0, 0.0], index=dates)
        pnl, pos = strategy.backtest(px, target, fee=0.0003)
        self.assertAlmostEqual(pos.iloc[0], 0.0)
        self.assertAlmostEqual(pos.iloc[1], 1.0)
        self.assertAlmostEqual(pnl.iloc[1], 2.2 / 2.0 - 1 - 0.0003)
        self.assertAlmostEqual(pnl.iloc[2], 3.3 / 2.2 - 1)

    def test_no_future_prefix_change(self):
        cutoff = "2024-12-31"
        partial = self.px.loc[:cutoff]
        sig = strategy.make_signal(partial, self.cfg["signal"])
        pnl, pos = strategy.backtest(partial, sig)
        self.assertTrue(np.allclose(pos, self.pos.loc[:cutoff]))
        self.assertTrue(np.allclose(pnl, self.pnl.loc[:cutoff]))

    def test_saved_metrics_reproduce(self):
        saved = json.loads((ROOT / "output" / "metrics.json").read_text())
        oos = strategy.metrics(self.pnl, self.pos, self.cfg["oos_start"], self.cfg["oos_end"])
        for key in ("total", "cagr", "sharpe", "calmar", "mdd"):
            self.assertAlmostEqual(oos[key], saved["oos"][key], places=12)


if __name__ == "__main__":
    unittest.main()
